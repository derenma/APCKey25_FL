# APC Key 25 mk2 — FL Studio Device Script

FL Studio MIDI scripting reference: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm

This is an FL Studio hardware device script for the Akai APC Key 25 mk2. It lives in FL Studio's `Settings/Hardware/APCKey25mk2` folder and is loaded automatically by FL Studio when the device is assigned as a MIDI controller.

Author: Matt Deren. Inspired by the original script by Martijn Tromp: https://forum.image-line.com/viewtopic.php?f=1994&t=225886

Forum thread: https://forum.image-line.com/viewtopic.php?t=323673

Github: https://github.com/derenma/APCKey25_FL

## Features and functions

- Keybed and pad passthrough in Standard Mode — plain MIDI note input, untouched by the script.
- Relative-encoder support for the 8 knobs, decoded into an absolute 1-127 value each.
- Transport control: Play/Pause and Record buttons stay in sync with FL Studio's actual transport state.
- SHIFT toggle for Standard Mode: switches the 8 track buttons and 5 scene buttons to their alternate (shift) functions, and dims/brightens the 4 knob-control button LEDs.
- Performance Mode: mirrors FL Studio's live-clip launch grid onto the 5x8 pad grid, and starts/stops clips directly from the pads.
- Clip staging while stopped: pressing a pad while playback is stopped selects (queues) that clip instead of sounding it, so it's ready to start on the next Play press without triggering immediately.
- Automatic one-shot clip cleanup: a one-shot clip is cleared once it finishes playing, so it doesn't unexpectedly restart the next time Play is pressed.
- Track scrolling: the up/down buttons move the visible 5-row pad window across playlists with more than 5 tracks, no SHIFT needed while in Performance Mode.
- Arrow-button LEDs (up/down/left/right) light up while Performance Mode is active, off in Normal Mode, as a visual mode indicator.
- Automatic playlist track selection that follows the visible pad rows whenever Performance Mode is active.
- Optional pad row coloring that approximates each track's FL Studio color, so a row's pads visually match their track (toggleable — see `ATTEMPT_COLOR_GUESS` in Debug logging below).
- A dedicated bright-green indicator for whichever clip is currently playing in a row, independent of that row's color.
- Adjustable debug logging levels for troubleshooting on real hardware.

## MIDI Settings setup

The APC Key 25 mk2 shows up as **two** MIDI ports per direction in FL Studio's
MIDI Settings — a generic control-surface port and a second `MIDIIN2`/`MIDIOUT2`
port. This script must be assigned to the **second** port only:

| Direction | Port | Setting |
|---|---|---|
| Output | `APC Key 25 mk2` | Leave unassigned — should show as the default "MIDI hardware port", no script selected. |
| Output | `MIDIOUT2 (APC Key 25 mk2)` | Enable the port and set this script as the handler. |
| Input | `APC Key 25 mk2` | Leave unassigned — should show as "(generic controller)", no port or script selected. |
| Input | `MIDIIN2 (APC Key 25 mk2)` | Enable the port and set this script as the handler. |

Also set **Performance Mode MIDI Channel: 1**.

Disabling **"Link note on velocity to: Velocity"** is recommended — the APC
Key 25 mk2's key velocity sensitivity is poor, and linking it makes normal
keybed playing feel inconsistent.

## Files

- **`device_APCKey25mk2.py`** — the active script. This is what FL Studio loads.
- **`mapping.py`** — all MIDI note/CC lookup tables (buttons, pad LED behavior codes, pad position tables, performance-mode grid mapping). Plain data, no FL Studio API dependency, imported by the main script.
- **`docs/`** — documentation and protocol reference material:
  - `docs/DEV_NOTES.md` — indexed developer notes for code sections that needed more context than a docstring or short comment can hold: hardware quirks, bug histories, and design decisions, cross-referenced from comments throughout `device_APCKey25mk2.py`.
  - `docs/FEATURES_AND_FIXES.md` — full changelog of features and fixes vs. the original script.
  - `docs/apc_key_protocol/` — the hardware protocol reference material:
    - `docs/apc_key_protocol/APC Key 25 mk2 - Communication Protocol - v1.1.pdf` — the manufacturer's protocol document.
    - `docs/apc_key_protocol/LED_COLOR_SCHEME.md` — writeup of how pad/button LED color and brightness are controlled via the Note On velocity palette, cross-referencing `akai_apc_key_25.yaml`.
    - `docs/apc_key_protocol/akai_apc_key_25.yaml` — protocol reference data (pad layout, LED velocity palette, SysEx frame formats). Not loaded by the script itself; kept as documentation and cross-referenced from `docs/apc_key_protocol/LED_COLOR_SCHEME.md`.
  - `docs/forum_posts/` — Image-Line forum post material:
    - `docs/forum_posts/ORIGINAL_FORUM_POST.md` — the original Image-Line forum post this script's thread is based on.
    - `docs/forum_posts/FORUM_POST_BBCODE.txt` — BBCode-formatted changelog post for the forum thread.

## How FL Studio loads this script

FL Studio calls a fixed set of module-level functions as callbacks (`OnInit`, `OnMidiIn`, `OnMidiMsg`, `OnDeInit`, etc. — see the MIDI scripting reference above). `device_APCKey25mk2.py` builds its object graph (state, lighting, event handling) once at import time, then those callbacks forward into it. There's no separate "install" step — FL Studio just needs this file present in its `Hardware/APCKey25mk2` settings folder with the device assigned to it in MIDI Settings.

The device exposes two physical MIDI ports, but FL Studio unifies them before this script ever sees an event. Routing between the two entry-point callbacks is driven by mode instead: `OnMidiMsg` only dispatches into `DeviceHandler.eventHandler` while performance mode is active; `OnMidiIn` only dispatches while it isn't. Both refresh `SessionState` from FL first, so the mode check is always current.

Loading a **different project** (not just reloading the script) doesn't inherently touch pad LEDs on its own — only performance mode being active does, via `OnUpdateLiveMode`'s gate (see Performance mode below). Without something noticing the project change, a previous project's live-clip grid state (e.g. a pad left flashing "scheduled") would otherwise persist on the pads indefinitely after switching to a project that isn't immediately in performance mode. `OnProjectLoad` (an FL callback that fires as a project loads) handles this: on a successful load, it resets `PerformanceMode`'s tracked state and forces a full pad reset, redrawing the new project's actual live-clip grid immediately if it happens to already be in performance mode. Unverified on real hardware — see docs/DEV_NOTES.md `OnProjectLoad` — stale pad state across project loads.

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
- **Knobs** (CC `0x30`–`0x37`, the 8 knobs above the pads) send relative encoder values. `DeviceHandler.knobAdjust` decodes the relative delta into an absolute 1–127 value per knob (clamped to stay within a valid 7-bit MIDI data byte) and writes it to `ControlStateStore`.
- **SHIFT** (`0x62`) is a **toggle**, not a hold: press once to engage (flashes the track/scene function-button LEDs), press again to release. The physical release (note-off) is ignored by design — this matches the original behavior and was an intentional decision, not a bug. Shift state is tracked in `ControlStateStore` via `DeviceHandler._shift_active()`.
- **PLAY/Pause** (`0x5B`) and **REC** (`0x5D`) call into `TransportHandler.togglePlay()` / `toggleRecord()` on every full press (velocity 127), which call FL's `transport.start/stop/record()` and resync `SessionState` from FL's actual transport state afterward. Note: this is the transport **Play/Pause** button — physically and functionally distinct from the **Stop/All Clips** button below, even though the APC Key 25 mk2's Play/Pause button behaves more like a Play/Stop toggle here (the device was originally designed for a different DAW's transport model).
- **Track buttons** (`0x40`–`0x47`, below the pad grid) and **scene buttons** (`0x52`–`0x56`) are recognized but **stubbed** in Normal Mode — pressing one logs `[stub] track button 'X' not implemented` and marks the event handled, but no action fires. Their SHIFT-held names (`up`/`down`/`left`/`right`/`knob_vol`/`knob_pan`/`knob_send`/`knob_device` for track buttons; `clip_stop`/`solo`/`mute`/`rec_arm`/`select` for scene buttons) are already mapped in `mapping.py` for whenever the rest of these get implemented, and SHIFT still toggles between the default/shift name sets here in Normal Mode. **In Performance Mode these buttons behave differently and don't need SHIFT at all** — see Performance mode below.
- **Stop/All Clips** (`0x51`) — a separate physical button from Play/Pause — is recognized and **stubbed** (`DeviceHandler._handle_stop`), matching the track/scene button pattern: logs `[stub] stop button ... not implemented` and marks the event handled, no action fires yet.
- **SUSTAIN** (dedicated physical button — the device has no separate TS pedal jack; the button itself sends standard MIDI Sustain, CC 64, status `0xB0`-`0xBF`) numerically collides with track button `0x40` (`track_1`, a Note On/Off) since both use data byte `0x40`. `DeviceHandler.eventHandler` disambiguates by status byte before any note-keyed dispatch runs (see `mapping.SUSTAIN_CC`) and routes it to `_handle_sustain`, which — like the track/scene/stop buttons — is currently a **stub**: it's correctly recognized and kept from being misrouted as a `track_1` press, but isn't yet passed through to FL as real sustain input in either mode.

## Performance mode

Entered when FL's playlist Performance Mode is active (`state.isPerformance()` true). This changes two things, in two different directions:

### Input: pad remap, explicit stop, and clip staging while stopped

While in performance mode, incoming pad note IDs (`0x00`–`0x27`, the physical grid numbering used for the live-clip launch grid) are remapped **before** `eventHandler`'s dispatch logic runs, via `mapping.performance_note_for(track, col)` — `12*(track-1)+col`. **While the song is playing**, starting a clip is driven entirely by this raw-note passthrough reaching FL, which then triggers playback itself based on the note value — the script doesn't call any explicit "start" API (see the row-5 bug history below for why). A note that went through this remap returns immediately after remapping and is **never** passed into the button/knob dispatch table below, even if its remapped value happens to numerically collide with a knob/button ID.

`performance_note_for`'s formula was reverse-engineered from the original hardcoded remap table: at `track_offset=0`, grid row 1 (=track 1) always produced notes 0-7, row 2 (=track 2) 12-19, ... row 5 (=track 5) 48-55 — exactly `12*(track-1)+col`. Since `eventHandler` already fully controls which note value gets sent (it's a substitution, not a passthrough of the raw pad ID), this same formula can compute the note for *any* track, not just the row's own fixed track number — which is what makes track-scroll-aware starting possible without any FL API call: `track = row + track_offset` is passed straight into the formula. Confirmed against real hardware for tracks 1-5 (unscrolled); the formula's validity beyond track 5 is inferred, not independently confirmed.

Before that remap happens, `DeviceHandler._handle_pad_performance_trigger` branches on whether the song is currently playing:
- **Playing:** checks whether the pressed pad's live-clip block is **already playing** (via `playlist.getLiveBlockStatus(track, col, 0)`, using `mapping.PAD_TO_GRID_POSITION` to go from the physical pad ID to grid coordinates, then adding `track_offset`). If it is, the script calls `playlist.triggerLiveClip(track, -1, midi.TLC_Fill)` to stop it and marks the event handled, instead of letting FL's own note-triggered retrigger just restart the same clip. A press on a pad that's empty or filled-but-not-yet-playing is left completely untouched (not marked handled) so it starts normally through the note passthrough above.
- **Stopped:** pressing a filled pad **stages** that clip instead of sounding it as a raw note — `playlist.triggerLiveClip(track, col, midi.TLC_Queue)`, marking the event handled so nothing plays directly. This is what makes the pad flash (the same "scheduled" LED state `OnUpdateLiveMode` already shows) so you can see what will start on the next PLAY press, and lets you stage a different clip in the same row before pressing PLAY. **Unverified on real hardware** — `midi.TLC_Queue`'s behavior is inferred from its name and FL's own (very sparse) flag documentation, not confirmed by testing; see docs/DEV_NOTES.md `_handle_pad_performance_trigger` clip staging while stopped for the full caveats. Pressing an empty pad while stopped is left untouched, same as while playing.

**Bug history — row 5 not starting clips:** row 5 (bottom row, physical pads 0-7) computed to notes 48-55 (at `track_offset=0`), which is exactly `0x30`-`0x37` — the same numeric range the dispatch table uses for the 8 physical knob CCs. Before the fix, a remapped row-5 pad note would fall into the dispatch lookup and get intercepted by `_handle_knob`, which mangled `event.data2` and marked the event handled — silently eating the note before it ever reached FL, which is why row 5 alone never started playback (confirmed via verbose logging on real hardware; other rows' computed notes don't collide with any dispatch entry). An earlier attempted fix — explicitly starting clips via `playlist.triggerLiveClip(row, col, 0)` instead of relying on note passthrough — was based on an incorrect diagnosis (assumed a per-project FL trigger-note config mismatch) and was tried on real hardware; it broke starting for **every** row and was reverted. The actual fix was to stop remapped pad notes from ever reaching dispatch at all (still in place today — see the code comment where `PAD_TO_GRID_POSITION` is checked in `eventHandler`), independent of the note-formula change described above.

### Track scroll (up/down)

The pad grid always shows 5 rows, but the playlist can have far more tracks than that. `PerformanceMode.track_offset` (default `0`) tracks how far the visible 5-row window has been scrolled: grid row `idx` (1-5, fixed — this is the physical row on the controller) always displays playlist track `idx + track_offset`.

Performance Mode and Normal Mode are two distinct states for the track/scene buttons, not something SHIFT switches between. In Performance Mode, `DeviceHandler._handle_track_button`/`_handle_scene_button` always use the `TRACK_BUTTONS_SHIFT`/`SCENE_BUTTONS_SHIFT` name sets — **no SHIFT needed**. In Normal Mode, SHIFT still toggles between the default and shift-name sets, same as before — SHIFT's role there is unchanged. This used to require holding SHIFT to scroll even while already in Performance Mode; see docs/DEV_NOTES.md `_handle_track_button` / `_handle_scene_button` for the history.

- **up** (`DeviceHandler._handle_track_button`, track button `0x40`) → `PerformanceMode.scroll(-1)`, while in Performance Mode.
- **down** (track button `0x41`) → `PerformanceMode.scroll(+1)`, while in Performance Mode.
- Outside Performance Mode, track button `0x40`/`0x41` fall through to the Normal-Mode track-button stub (SHIFT-toggled name, see Standard mode above) — pressing them there does not scroll.
- `scroll()` clamps `track_offset` to `>= 0`, so grid row 1 can never display a track below track 1.
- On an actual offset change, `scroll()` calls `select_tracks()` (deselects all playlist tracks, then selects exactly the 5 now-visible ones — `playlist.selectTrack()` only *toggles*, so a full deselect first is what makes this deterministic regardless of the track selection the user had before scrolling) and redraws the grid (`OnUpdateLiveMode`) so the pad LEDs immediately reflect the new window. If the offset doesn't actually change (e.g. pressing up while already at the top), nothing is reselected or redrawn.
- `track_offset` is applied everywhere a physical pad is translated into an FL-facing value — the live-clip grid draw (`OnUpdateLiveMode`), the pad stop-trigger (`_handle_pad_performance_trigger`), **and** the note substituted for starting a clip (`mapping.performance_note_for`) — so once scrolled, pressing a pad starts, stops, and reflects the *currently displayed* track, not the one that was there before scrolling. (Starting wasn't scroll-aware in an earlier version of this feature — see the Input section above for why that was a harder problem than it looked.)
- `select_tracks()` also runs automatically whenever FL's performance mode actually transitions from off to on — detected in `OnUpdateLiveMode` by comparing `playlist.getPerformanceModeState()` against its previous value — not unconditionally at script load. An earlier version called it unconditionally from module-level `OnInit()` on every load regardless of mode, which clobbered the user's normal-mode track selection at startup and never re-selected on a later real entry into performance mode; see docs/DEV_NOTES.md `PerformanceMode.__init__` for the full history. `OnInit()` still exists as the point where this tracking gets armed (`PerformanceMode.on_script_ready()`) — calling `playlist.selectTrack()`/`deselectAll()` during `__init__` (script import time) raises `RuntimeError: Operation unsafe at current time` on real hardware — confirmed the hard way — so mutating calls still can't happen any earlier than `OnInit()`. Read-only playlist calls (`getLiveBlockStatus` etc., used by `OnUpdateLiveMode` for the initial LED draw) are fine at import time.
- The 4 arrow-button LEDs (`PadLighting.set_arrow_buttons`, `mapping.ARROW_BUTTONS`) light up to indicate Performance Mode is active, and turn off in Normal Mode — tracked at the same off↔on transition as `select_tracks()` above (both directions this time, not just entering), plus set correctly at script load and on a new project load. Unverified on real hardware — see docs/DEV_NOTES.md `OnUpdateLiveMode` arrow-button LEDs.

### Output: live-clip grid → pad LEDs

`PerformanceMode.OnUpdateLiveMode` is called by FL (via the module-level `OnUpdateLiveMode` callback) whenever the live-clip grid changes — but only actually redraws pad LEDs while FL is genuinely in performance mode (checked fresh via `playlist.getPerformanceModeState()` every call, not a cached value); see docs/DEV_NOTES.md `OnUpdateLiveMode` performance-mode gate. When active, it walks a 5-row × 8-column grid (`playlist.getLiveBlockStatus(row, col, 0)`) and lights the corresponding physical pad via `mapping.LIVE_GRID_PAD_POSITIONS` — a lookup table mapping `[row][col]` grid coordinates to the physical pad note ID. This table is unrelated to the input remap above; they solve two different problems (input note translation vs. output LED addressing) that happen to both be tied to the performance-mode concept.

`getLiveBlockStatus(row, col, 0)` (mode 0, the default) returns a bitmask: `filled=1`, `scheduled=2`, `playing=4` (per FL's MIDI scripting docs). If `ATTEMPT_COLOR_GUESS` (top of `device_APCKey25mk2.py`, next to `DEBUG_LEVEL`) is `True`, each **row's color** is the closest available palette match to that row's FL Studio track color (`playlist.getTrackColor()`, matched via `mapping.closest_color_index_for_fl_color()` — the device can only render one of a fixed 128-color ROM palette, so this finds the nearest visual match, not an exact one — see `docs/LED_COLOR_SCHEME.md` and docs/DEV_NOTES.md `OnUpdateLiveMode` track-color rows), recomputed every redraw so it follows scrolling automatically. If `ATTEMPT_COLOR_GUESS` is `False` (the current default), rows skip the per-track lookup and use a fixed legacy scheme instead: white for idle/scheduled pads, dark red for playing pads. Either way, since color doesn't (or, with the flag off, never did) carry per-block state on its own, **state is conveyed by brightness/pulse channel**:
- **Playing** (`status & 4`) → a fixed bright-green indicator (`mapping.PLAYING_INDICATOR_COLOR`) when `ATTEMPT_COLOR_GUESS` is on, or dark red when it's off — either way solid, full brightness (`bright_6`), and not the row's track color, so the active clip is unambiguous regardless of track hue. Reverts automatically when a different block starts playing or this one stops, since the whole grid is redrawn from current status every call.
- **Scheduled but not yet playing** (`status & 2`, queued to launch next in this row) → the row's color, flashing (`pulse_1_4`).
- **Filled but idle** (any other truthy status) → the row's color, solid, dimmer (`bright_2`).
- **Empty** (`status == 0`) → pad turned off (dimmed to the default off state).

Color indices `1`/`2` are deliberately never used for pad colors anywhere in the script — confirmed on real hardware to cause periodic flicker regardless of LED mode/channel; see docs/DEV_NOTES.md "ROOT CAUSE CONFIRMED: low RGB-palette color indices."

`OnUpdateLiveMode` also logs a one-time `"Performance Mode Init!"` status message on its first call after script load/restart while performance mode is active.

**One-shot clip auto-clear:** each redraw, `OnUpdateLiveMode` also tracks whether each visible track was playing on the previous redraw. If a track's loop mode is "One shot" (`playlist.getLiveLoopMode(track) == 1`) and it just transitioned from playing to stopped **on its own** (not via a manual pad-press stop, which already clears it), the script calls `playlist.triggerLiveClip(track, -1, midi.TLC_Fill)` to explicitly clear FL's armed/queued state for it — otherwise a finished one-shot clip would replay on the next Play press instead of staying stopped. Unverified on real hardware — see docs/DEV_NOTES.md `OnUpdateLiveMode` one-shot auto-clear.

### What doesn't change between modes

SHIFT itself (the toggle/LED state), PLAY/REC, and the knobs behave identically in both modes. What *does* differ, beyond pad note routing (input) and pad LED content (output): track/scene buttons no longer need SHIFT held in Performance Mode — see Performance mode above.

## LED color model

Pad and function-button LEDs are driven entirely through the **built-in Note On velocity palette** (`9X PP VV` — channel `X` selects brightness/pulse/blink behavior, velocity `VV` indexes a fixed 128-entry firmware color table). See `docs/apc_key_protocol/LED_COLOR_SCHEME.md` for the full palette breakdown, cross-referenced against `akai_apc_key_25.yaml`. This script does **not** use the SysEx RGB Color Lighting message — that was evaluated during development and deliberately left out of scope.

## Debug logging

`DEBUG_LEVEL` (top of `device_APCKey25mk2.py`) controls output verbosity:

| Level | Shows |
|---|---|
| `DebugLevel.OFF` | Nothing. |
| `DebugLevel.STATUS` | Init sequence, transport/mode changes, stub-button notices, SysEx arrival — safe to leave on. |
| `DebugLevel.VERBOSE` | Everything above, plus per-event tracing, knob decode steps, the raw device-ID byte dump, and live-clip grid internals. Noisy — only for active debugging. |

`log_status()` and `log_verbose()` are the only logging entry points; there should be no bare `print()` calls elsewhere in the script. `log_verbose()` automatically prefixes each message with the calling method's `ClassName.method` (or bare function name at module scope), so verbose messages don't need to restate where they came from.

`ATTEMPT_COLOR_GUESS` (also top of `device_APCKey25mk2.py`, next to `DEBUG_LEVEL`) is a separate toggle, not a logging setting: `True` enables the track-color-matching pad rows described in Performance mode above; `False` (the current default) falls back to the legacy fixed white/dark-red pad scheme, skipping the per-track color lookup entirely.

## Known limitations / unverified on real hardware

These are called out in code comments where relevant; collected here for visibility:

- **Pad vs. keybed note ID collision:** pad note IDs (`0x00`–`0x27`) and low keybed key note numbers can numerically overlap. The device has two physical MIDI ports (keys vs. control surface), but FL Studio unifies them before this script ever sees an event — there's no reliable way to tell them apart from the note number alone. `DeviceHandler._classify_control` treats anything in the pad ID range as a pad, matching existing behavior, but this is unverified for genuine low keybed notes.
- **`event.handled = True`** is set for every event the script fully handles (shift, play, record, track/scene stubs, knobs). This is provisional — it stops FL from also treating those as passthrough MIDI, but hasn't been validated on hardware that this is the desired behavior for every one of those event types.
- **Track/scene buttons and Stop/All Clips** are unimplemented (see Standard mode above), except up/down in Performance Mode (track scroll — see above; no SHIFT needed there anymore).
- **SUSTAIN / track_1 (`0x40`) disambiguation** — the status-byte check (`event.status & 0xF0 == midi.MIDI_CONTROLCHANGE`) matches real hardware logs (`90 40 xx` = Note On for a note that happens to be `0x40`; `B0 40 xx` = the SUSTAIN button's Control Change), confirming the two really are told apart correctly by status byte. What's still unconfirmed: whether SUSTAIN and this Note-0x40 collision are even reachable by this script at all — the confirming log was captured on the port FL labels `(generic controller)`, i.e. the **unscripted** main port per this README's MIDI Settings table, not `MIDIIN2` (the port this script is actually assigned to). If SUSTAIN and keybed notes never arrive on `MIDIIN2`, this disambiguation code may never actually run in practice — harmless either way, but its real-world relevance needs confirming. Sustain itself is currently a stub (see Standard mode above) — passthrough behavior is a follow-up, not yet implemented.
- **Performance-mode pad stop** (`_handle_pad_performance_trigger`, `playlist.triggerLiveClip(row, -1, midi.TLC_Fill)`) is confirmed working on real hardware. Row 5 (bottom row) not starting clips was root-caused to a dispatch-table collision (see Performance mode section above) and fixed — pending re-verification on real hardware that row 5 now starts correctly and that rows 1-4 are unaffected.
- **Track scroll (up/down)** is new — originally required holding SHIFT even while already in Performance Mode; SHIFT was later removed from the requirement entirely (see docs/DEV_NOTES.md `_handle_track_button` / `_handle_scene_button`). An import-time crash (`RuntimeError: Operation unsafe at current time` from calling `playlist.selectTrack`/`deselectAll` in `PerformanceMode.__init__`) was caught and fixed by deferring the initial selection to `OnInit()`. Confirmed on real hardware: pad LEDs scroll correctly, and stopping a clip on a scrolled row targets the right track. **Not yet confirmed on real hardware:** starting a clip on a scrolled row via the new `mapping.performance_note_for(track, col)` formula — this replaced the old fixed remap table and is what makes starting scroll-aware, but its validity for tracks beyond 5 (i.e. after actually scrolling) is inferred from the pattern in tracks 1-5, not independently verified.
- **Clip staging while stopped** — `midi.TLC_Queue`'s behavior is inferred from its name and FL's own sparse flag documentation, not confirmed by testing. See docs/DEV_NOTES.md `_handle_pad_performance_trigger` clip staging while stopped.
- **One-shot clip auto-clear** — entirely unverified on real hardware; the detection API (`playlist.getLiveLoopMode(track) == 1`) is confirmed real, but whether the clear call actually prevents replay-on-restart hasn't been tested. See docs/DEV_NOTES.md `OnUpdateLiveMode` one-shot auto-clear.
- **Track-color rows (`ATTEMPT_COLOR_GUESS`)** — the closest-palette-match color scheme has gone through several rounds of real-hardware bug fixes (an R/B channel swap, then a saturation-mismatch tuning pass) and is off by default pending further verification. See docs/DEV_NOTES.md `OnUpdateLiveMode` track-color rows for the full history.
- **Performance-mode-entry auto-select** — track selection now only happens when FL's performance mode actually turns on (detected reactively in `OnUpdateLiveMode`), replacing an earlier unconditional-at-load version that clobbered normal-mode track selection at every script load. This is a real behavior change, not just a refactor, and is unverified on real hardware — see docs/DEV_NOTES.md `PerformanceMode.__init__` for exactly what needs re-checking.
- **Stale pad state across project loads** — new `OnProjectLoad` handler resets tracked state and forces a full pad reset when a different project loads, so a previous project's live-clip grid state (e.g. a flashing "scheduled" pad) doesn't persist indefinitely. Implemented from FL's documented callback behavior (`midi.PL_LoadOk`/`PL_LoadError`/`PL_Start`), not yet confirmed against an actual project-load sequence on real hardware — see docs/DEV_NOTES.md `OnProjectLoad` — stale pad state across project loads.
- **Arrow-button LEDs** — new, unverified on real hardware. Lights the 4 arrow track buttons while Performance Mode is active, off in Normal Mode; see docs/DEV_NOTES.md `OnUpdateLiveMode` arrow-button LEDs.
