# APC Key 25 mk2 — FL Studio Device Script

FL Studio MIDI scripting reference: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm

This is an FL Studio hardware device script for the Akai APC Key 25 mk2. It lives in FL Studio's `Settings/Hardware/APCKey25mk2` folder and is loaded automatically by FL Studio when the device is assigned as a MIDI controller.

Author: Matt Deren. Inspired by the original script by Martijn Tromp: https://forum.image-line.com/viewtopic.php?f=1994&t=225886

Forum thread: https://forum.image-line.com/viewtopic.php?t=323673

Github: https://github.com/derenma/APCKey25_FL

## Files

- **`device_APCKey25mk2.py`** — the active script. This is what FL Studio loads.
- **`mapping.py`** — all MIDI note/CC lookup tables (buttons, pad LED behavior codes, pad position tables, performance-mode grid mapping). Plain data, no FL Studio API dependency, imported by the main script.
- **`akai_apc_key_25.yaml`** — protocol reference data (pad layout, LED velocity palette, SysEx frame formats). Not loaded by the script itself; kept as documentation and cross-referenced from `docs/LED_COLOR_SCHEME.md`.
- **`docs/`** — protocol reference material:
  - `docs/APC Key 25 mk2 - Communication Protocol - v1.1.pdf` — the manufacturer's protocol document.
  - `docs/LED_COLOR_SCHEME.md` — writeup of how pad/button LED color and brightness are controlled via the Note On velocity palette, cross-referencing `akai_apc_key_25.yaml`.

## How FL Studio loads this script

FL Studio calls a fixed set of module-level functions as callbacks (`OnInit`, `OnMidiIn`, `OnMidiMsg`, `OnDeInit`, etc. — see the MIDI scripting reference above). `device_APCKey25mk2.py` builds its object graph (state, lighting, event handling) once at import time, then those callbacks forward into it. There's no separate "install" step — FL Studio just needs this file present in its `Hardware/APCKey25mk2` settings folder with the device assigned to it in MIDI Settings.

The device exposes two physical MIDI ports, but FL Studio unifies them before this script ever sees an event. Routing between the two entry-point callbacks is driven by mode instead: `OnMidiMsg` only dispatches into `DeviceHandler.eventHandler` while performance mode is active; `OnMidiIn` only dispatches while it isn't. Both refresh `SessionState` from FL first, so the mode check is always current.

## Core building blocks

- **`SessionState`** — mirrors FL's own transport/playlist state (`isPlaying`, `isRecording`, `isPerformance`). Refreshed once per incoming MIDI event; not physical controller state.
- **`ControlStateStore`** — the single source of truth for every physical control's state: whether it's currently pressed (`active`), a knob's current value, and — for pads/function buttons — the last LED color/mode sent. Keyed by `(ControlKind, note_id)`. LED-writing methods diff against this before sending, so redundant MIDI (e.g. redrawing the whole live-clip grid every playlist update) gets skipped when nothing actually changed.
- **`DeviceHandler`** — owns incoming-event handling. `eventHandler` does a small amount of shared work (performance-mode remap, active-state tracking) and then dispatches to one `_handle_*` method per control via a lookup table built in `__init__`.
- **`PadLighting`** — all outgoing LED control, for both the 5x8 pad grid and the track/scene function buttons.
- **`PerformanceMode`** — mirrors FL's live-clip launch grid onto the pad LEDs.
- **`TransportHandler`** — play/record/loop/fast-forward/rewind wrappers around FL's `transport` module.

Debug output uses two levels — see [Debug logging](#debug-logging) below.

## Standard mode

This is the default mode: FL's playlist is **not** in Performance Mode (`playlist.getPerformanceModeState()` is false). In this mode:

- **Keybed keys** pass through to FL untouched (normal MIDI note input) — the script doesn't intercept them.
- **Pads** (note IDs `0x00`–`0x27`, the 5x8 grid) are **not** remapped or specially handled in standard mode; presses pass through as regular notes, same as the keybed. There is currently no standard-mode pad→action behavior implemented.
- **Knobs** (CC `0x30`–`0x37`, the 8 knobs above the pads) send relative encoder values. `DeviceHandler.knobAdjust` decodes the relative delta into an absolute 1–128 value per knob and writes it to `ControlStateStore`.
- **SHIFT** (`0x62`) is a **toggle**, not a hold: press once to engage (flashes the track/scene function-button LEDs), press again to release. The physical release (note-off) is ignored by design — this matches the original behavior and was an intentional decision, not a bug. Shift state is tracked in `ControlStateStore` via `DeviceHandler._shift_active()`.
- **PLAY** (`0x5B`) and **REC** (`0x5D`) call into `TransportHandler.togglePlay()` / `toggleRecord()` on every full press (velocity 127), which call FL's `transport.start/stop/record()` and resync `SessionState` from FL's actual transport state afterward.
- **Track buttons** (`0x40`–`0x47`, below the pad grid) and **scene buttons** (`0x52`–`0x56`) are recognized but **stubbed** — pressing one logs `[stub] track button 'X' not implemented` and marks the event handled, but no action fires. Their SHIFT-held names (`up`/`down`/`left`/`right`/`knob_vol`/`knob_pan`/`knob_send`/`knob_device` for track buttons; `clip_stop`/`solo`/`mute`/`rec_arm`/`select` for scene buttons) are already mapped in `mapping.py` for whenever this gets implemented — **except** SHIFT+up/down, which is implemented but only takes effect in performance mode (see below); pressed outside performance mode, up/down still fall through to the stub.
- **STOP** (`0x51`) is defined in `mapping.py` but has no handler wired up at all — currently a no-op pass-through.

## Performance mode

Entered when FL's playlist Performance Mode is active (`state.isPerformance()` true). This changes two things, in two different directions:

### Input: pad remap, and explicit stop

While in performance mode, incoming pad note IDs (`0x00`–`0x27`, the physical grid numbering used for the live-clip launch grid) are remapped **before** `eventHandler`'s dispatch logic runs, via `mapping.performance_note_for(track, col)` — `12*(track-1)+col`. **Starting** a clip is driven entirely by this raw-note passthrough reaching FL, which then triggers playback itself based on the note value — the script doesn't call any explicit "start" API (see the row-5 bug history below for why). A note that went through this remap returns immediately after remapping and is **never** passed into the button/knob dispatch table below, even if its remapped value happens to numerically collide with a knob/button ID.

`performance_note_for`'s formula was reverse-engineered from the original hardcoded remap table: at `track_offset=0`, grid row 1 (=track 1) always produced notes 0-7, row 2 (=track 2) 12-19, ... row 5 (=track 5) 48-55 — exactly `12*(track-1)+col`. Since `eventHandler` already fully controls which note value gets sent (it's a substitution, not a passthrough of the raw pad ID), this same formula can compute the note for *any* track, not just the row's own fixed track number — which is what makes track-scroll-aware starting possible without any FL API call: `track = row + track_offset` is passed straight into the formula. Confirmed against real hardware for tracks 1-5 (unscrolled); the formula's validity beyond track 5 is inferred, not independently confirmed.

Before that remap happens, `DeviceHandler._handle_pad_performance_trigger` checks whether the pressed pad's live-clip block is **already playing** (via `playlist.getLiveBlockStatus(track, col, 0)`, using `mapping.PAD_TO_GRID_POSITION` to go from the physical pad ID to grid coordinates, then adding `track_offset`). If it is, the script calls `playlist.triggerLiveClip(track, -1, midi.TLC_Fill)` to stop it and marks the event handled, instead of letting FL's own note-triggered retrigger just restart the same clip. A press on a pad that's empty or filled-but-not-yet-playing is left completely untouched (not marked handled) so it starts normally through the note passthrough above.

**Bug history — row 5 not starting clips:** row 5 (bottom row, physical pads 0-7) computed to notes 48-55 (at `track_offset=0`), which is exactly `0x30`-`0x37` — the same numeric range the dispatch table uses for the 8 physical knob CCs. Before the fix, a remapped row-5 pad note would fall into the dispatch lookup and get intercepted by `_handle_knob`, which mangled `event.data2` and marked the event handled — silently eating the note before it ever reached FL, which is why row 5 alone never started playback (confirmed via verbose logging on real hardware; other rows' computed notes don't collide with any dispatch entry). An earlier attempted fix — explicitly starting clips via `playlist.triggerLiveClip(row, col, 0)` instead of relying on note passthrough — was based on an incorrect diagnosis (assumed a per-project FL trigger-note config mismatch) and was tried on real hardware; it broke starting for **every** row and was reverted. The actual fix was to stop remapped pad notes from ever reaching dispatch at all (still in place today — see the code comment where `PAD_TO_GRID_POSITION` is checked in `eventHandler`), independent of the note-formula change described above.

### Track scroll (SHIFT + up/down)

The pad grid always shows 5 rows, but the playlist can have far more tracks than that. `PerformanceMode.track_offset` (default `0`) tracks how far the visible 5-row window has been scrolled: grid row `idx` (1-5, fixed — this is the physical row on the controller) always displays playlist track `idx + track_offset`.

- **SHIFT + up** (`DeviceHandler._handle_track_button`, track button `0x40`) → `PerformanceMode.scroll(-1)`.
- **SHIFT + down** (track button `0x41`) → `PerformanceMode.scroll(+1)`.
- Both only take effect while `state.isPerformance()` is true; outside performance mode SHIFT+up/down still falls through to the track-button stub (see Standard mode above).
- `scroll()` clamps `track_offset` to `>= 0`, so grid row 1 can never display a track below track 1.
- On an actual offset change, `scroll()` calls `select_tracks()` (deselects all playlist tracks, then selects exactly the 5 now-visible ones — `playlist.selectTrack()` only *toggles*, so a full deselect first is what makes this deterministic regardless of the track selection the user had before scrolling) and redraws the grid (`OnUpdateLiveMode`) so the pad LEDs immediately reflect the new window. If the offset doesn't actually change (e.g. pressing up while already at the top), nothing is reselected or redrawn.
- `track_offset` is applied everywhere a physical pad is translated into an FL-facing value — the live-clip grid draw (`OnUpdateLiveMode`), the pad stop-trigger (`_handle_pad_performance_trigger`), **and** the note substituted for starting a clip (`mapping.performance_note_for`) — so once scrolled, pressing a pad starts, stops, and reflects the *currently displayed* track, not the one that was there before scrolling. (Starting wasn't scroll-aware in an earlier version of this feature — see the Input section above for why that was a harder problem than it looked.)
- `select_tracks()` also runs once at startup, establishing the default tracks 1-5 selection — but from module-level `OnInit()`, not `PerformanceMode.__init__`. Calling `playlist.selectTrack()`/`deselectAll()` during `__init__` (script import time) raises `RuntimeError: Operation unsafe at current time` on real hardware — confirmed the hard way. Read-only playlist calls (`getLiveBlockStatus` etc., used by `OnUpdateLiveMode` for the initial LED draw) are fine at import time; only mutating calls need to wait for `OnInit()`.

### Output: live-clip grid → pad LEDs

`PerformanceMode.OnUpdateLiveMode` is called by FL (via the module-level `OnUpdateLiveMode` callback) whenever the live-clip grid changes. It walks a 5-row × 8-column grid (`playlist.getLiveBlockStatus(row, col, 0)`) and lights the corresponding physical pad via `mapping.LIVE_GRID_PAD_POSITIONS` — a lookup table mapping `[row][col]` grid coordinates to the physical pad note ID. This table is unrelated to the input remap above; they solve two different problems (input note translation vs. output LED addressing) that happen to both be tied to the performance-mode concept.

`getLiveBlockStatus(row, col, 0)` (mode 0, the default) returns a bitmask: `filled=1`, `scheduled=2`, `playing=4` (per FL's MIDI scripting docs). Grid cell color logic:
- `status == 7` (filled + scheduled + playing) → pad lit with color index `6` — the block is the one currently playing.
- any other truthy status (filled, or filled+scheduled but not yet playing) → pad lit with color index `1`.
- `status == 0` (empty) → pad turned off (dimmed to the default off state).

`OnUpdateLiveMode` also logs a one-time `"Performance Mode Init!"` status message on its first call after script load/restart.

### What doesn't change between modes

SHIFT/PLAY/REC and the knobs behave identically in both modes — only pad note routing (input) and pad LED content (output, driven independently by the live-clip grid) differ.

## LED color model

Pad and function-button LEDs are driven entirely through the **built-in Note On velocity palette** (`9X PP VV` — channel `X` selects brightness/pulse/blink behavior, velocity `VV` indexes a fixed 128-entry firmware color table). See `docs/LED_COLOR_SCHEME.md` for the full palette breakdown, cross-referenced against `akai_apc_key_25.yaml`. This script does **not** use the SysEx RGB Color Lighting message — that was evaluated during development and deliberately left out of scope.

## Debug logging

`DEBUG_LEVEL` (top of `device_APCKey25mk2.py`) controls output verbosity:

| Level | Shows |
|---|---|
| `DebugLevel.OFF` | Nothing. |
| `DebugLevel.STATUS` | Init sequence, transport/mode changes, stub-button notices, SysEx arrival — safe to leave on. |
| `DebugLevel.VERBOSE` | Everything above, plus per-event tracing, knob decode steps, the raw device-ID byte dump, and live-clip grid internals. Noisy — only for active debugging. |

`log_status()` and `log_verbose()` are the only logging entry points; there should be no bare `print()` calls elsewhere in the script. `log_verbose()` automatically prefixes each message with the calling method's `ClassName.method` (or bare function name at module scope), so verbose messages don't need to restate where they came from.

## Known limitations / unverified on real hardware

These are called out in code comments where relevant; collected here for visibility:

- **Pad vs. keybed note ID collision:** pad note IDs (`0x00`–`0x27`) and low keybed key note numbers can numerically overlap. The device has two physical MIDI ports (keys vs. control surface), but FL Studio unifies them before this script ever sees an event — there's no reliable way to tell them apart from the note number alone. `DeviceHandler._classify_control` treats anything in the pad ID range as a pad, matching existing behavior, but this is unverified for genuine low keybed notes.
- **`event.handled = True`** is set for every event the script fully handles (shift, play, record, track/scene stubs, knobs). This is provisional — it stops FL from also treating those as passthrough MIDI, but hasn't been validated on hardware that this is the desired behavior for every one of those event types.
- **Track/scene buttons and STOP** are unimplemented (see Standard mode above), except SHIFT+up/down in performance mode (track scroll — see above).
- **Performance-mode pad stop** (`_handle_pad_performance_trigger`, `playlist.triggerLiveClip(row, -1, midi.TLC_Fill)`) is confirmed working on real hardware. Row 5 (bottom row) not starting clips was root-caused to a dispatch-table collision (see Performance mode section above) and fixed — pending re-verification on real hardware that row 5 now starts correctly and that rows 1-4 are unaffected.
- **Track scroll (SHIFT + up/down)** is new. An import-time crash (`RuntimeError: Operation unsafe at current time` from calling `playlist.selectTrack`/`deselectAll` in `PerformanceMode.__init__`) was caught and fixed by deferring the initial selection to `OnInit()`. Confirmed on real hardware: pad LEDs scroll correctly, and stopping a clip on a scrolled row targets the right track. **Not yet confirmed on real hardware:** starting a clip on a scrolled row via the new `mapping.performance_note_for(track, col)` formula — this replaced the old fixed remap table and is what makes starting scroll-aware, but its validity for tracks beyond 5 (i.e. after actually scrolling) is inferred from the pattern in tracks 1-5, not independently verified.
