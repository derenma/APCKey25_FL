# Developer Notes — device_APCKey25mk2.py

Indexed notes for code sections that needed more context than a docstring or
short comment can reasonably hold: hardware quirks, bug histories, and
design decisions. The script points here (via a short comment) instead of
carrying the full explanation inline. Line numbers are current as of this
writing and will drift as the script changes — search for the function/class
name if a reference is stale.

## Index

- [Script header — compatibility notes & SysEx RGB status](#script-header--compatibility-notes--sysex-rgb-status)
- [`eventHandler` — performance-mode pad remap & the row-5/knob collision bug](#eventhandler--performance-mode-pad-remap--the-row-5knob-collision-bug)
- [`_handle_pad_performance_trigger` — why starting a clip isn't triggered explicitly (while playing)](#_handle_pad_performance_trigger--why-starting-a-clip-isnt-triggered-explicitly-while-playing)
- [`_handle_pad_performance_trigger` — clip staging while stopped](#clip-staging-while-stopped)
- [`_handle_shift` — the provisional `event.handled` blanket](#_handle_shift--the-provisional-eventhandled-blanket)
- [`_handle_shift` — engage/release visuals were inverted](#_handle_shift--engagerelease-visuals-were-inverted)
- [`_handle_record` — why `toggleRecord` is called on every press](#_handle_record--why-togglerecord-is-called-on-every-press)
- [`PerformanceMode.__init__` — "Operation unsafe at current time" crash, and selecting tracks only on real performance-mode entry](#performancemode__init__--operation-unsafe-at-current-time-crash-and-selecting-tracks-only-on-real-performance-mode-entry)
- [`OnMidiMsg` / `OnMidiIn` — dual-port dispatch via the performance-mode gate](#onmidimsg--onmidiin--dual-port-dispatch-via-the-performance-mode-gate)
- [`_handle_sustain` — why SUSTAIN is a stub, and when that might need to change](#_handle_sustain--why-sustain-is-a-stub-and-when-that-might-need-to-change)
- [`OnUpdateLiveMode` — clip-transition LED behavior (flashing vs. solid)](#onupdatelivemode--clip-transition-led-behavior-flashing-vs-solid)
- [`OnUpdateLiveMode` — one-shot auto-clear](#onupdatelivemode--one-shot-auto-clear)
- [`_handle_track_button` / `_handle_scene_button` — mode-based naming, not SHIFT-gated](#_handle_track_button--_handle_scene_button--mode-based-naming-not-shift-gated)
- [`OnUpdateLiveMode` — performance-mode gate (periodic LED flash investigation)](#onupdatelivemode--performance-mode-gate-periodic-led-flash-investigation)
- [ROOT CAUSE CONFIRMED: low RGB-palette color indices (1, 2) flicker on real hardware](#root-cause-confirmed-low-rgb-palette-color-indices-1-2-flicker-on-real-hardware)
- [`OnUpdateLiveMode` — track-color rows](#onupdatelivemode--track-color-rows)
- [`knobAdjust` — two real bugs found on real hardware](#knobadjust--two-real-bugs-found-on-real-hardware)

---

## Script header — compatibility notes & SysEx RGB status

**Location:** top of `device_APCKey25mk2.py`, header comment block.

- Tested with FL Studio 2026 v26.1.3 (build 5570).
- Developed in VS Code with Pylance; the `# pyright: ignore[reportMissingImports]`
  comments on the FL-provided modules (`transport`, `device`, `playlist`,
  `patterns`, `midi`, etc.) are there because those modules only exist inside
  FL Studio's script runtime — there's no package for Pylance to resolve
  locally, so without the ignore comments every one of those imports is
  flagged as an error.
- **SysEx custom RGB pad colors do not work on this hardware.** The device
  doesn't respond to the required "Introduction" SysEx message
  (`F0 47 7F 4E 60 00 04 00 <ver> <ver> <ver> F7`), which per the protocol
  must be sent and acknowledged before any other device-specific SysEx
  (including the RGB Color Lighting message, `0x24`) will be honored. The
  suspicion is that a specific, currently-undocumented version number needs
  to be sent in that Introduction message — brute-forcing the version bytes
  might work, but hasn't been tried, and could be a dead end. This is why
  the script drives LEDs entirely through the built-in Note On velocity
  palette instead (see `PadLighting`) rather than SysEx RGB.
- Debug snippets, if anyone wants to pick this up:

  ```python
  # TEST: RGB Color Lighting SysEx (pads 0x00-0x27, R=255 G=255 B=0)
  #self.buttons.all_pads_off(speed=0.00)
  #time.sleep(1)
  #self.buttons.all_pads_on(speed=0.00)
  #time.sleep(1)
  # TEST: MMC Device Enquiry (F0 7E 00 06 01 F7)
  #device.midiOutSysex(bytes([0xF0, 0x7E, 0x00, 0x06, 0x01, 0xF7]))
  #time.sleep(1)
  #device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x60, 0x00, 0x04, 0x00, 0x01, 0x00, 0x00, 0xF7]))  # Introduction Message
  #time.sleep(1)
  #print('sending color change')
  #device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x24, 0x00, 0x08, 0x00, 0x00, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0xF7]))
  #device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x24, 0x00, 0x08, 0x00, 0x00, 0x01, 0x7F, 0x00, 0x00, 0x01, 0x7F, 0xF7]))
  ```

---

## `eventHandler` — performance-mode pad remap & the row-5/knob collision bug

**Location:** `DeviceHandler.eventHandler`, ~line 468.

When performance mode is active, a pad press is remapped to the note FL
expects for live-clip triggering (`mapping.performance_note_for`) and the
method returns immediately — that remapped note must **never** reach the
`_dispatch` lookup below, even if it numerically collides with a knob/button
ID.

That collision isn't hypothetical: at `track_offset=0`, row 5 (the bottom
row, physical pads 0-7) computes to notes 48-55, which is exactly `0x30`-
`0x37` — the same CC range the dispatch table uses for the 8 physical knobs.
Before this early-return existed, a remapped row-5 pad note fell into
`_dispatch` and got intercepted by `_handle_knob`, which mangled
`event.data2` and marked the event handled — silently eating the note before
it ever reached FL. This is why row 5 alone never started playback, and it
was confirmed via verbose logging on real hardware (other rows' computed
notes don't collide with any dispatch entry). The fix — returning immediately
after the remap, before dispatch ever runs — is what's in place today.

### Why knobs and SHIFT are excluded from generic press/release tracking

```python
# Knobs/SHIFT excluded — see DEV_NOTES.md: eventHandler.
control_kind = self._classify_control(event.data1)
if control_kind != ControlKind.KNOB and event.data1 != mapping.SOUND_BUTTONS.id_for("shift"):
    self.controlStates.set_active(control_kind, event.data1, event.data2 != 0)
```

Every other control's `active` flag is set generically right here, straight
from `event.data2 != 0`. Knobs and SHIFT can't use that same generic path:

- **Knobs** don't have a meaningful pressed/released state at all — they're
  relative encoders, and their value is recorded separately, post-decode, in
  `_handle_knob` (see `knobAdjust`). Running them through `set_active` here
  would just store a meaningless boolean derived from a relative-delta byte.
- **SHIFT** is a toggle (press to engage, press again to release — see
  `_handle_shift`), not a hold. Its `active` state is managed explicitly in
  `_handle_shift` via `_shift_active()`; letting the generic press/release
  logic here also write to it would clobber that toggle state on every
  physical release, which SHIFT is specifically designed to ignore.

---

## `_handle_pad_performance_trigger` — why starting a clip isn't triggered explicitly (while playing)

**Location:** `DeviceHandler._handle_pad_performance_trigger`, ~line 413.

While the song is **playing**, this method only ever **stops** an
already-playing live-clip block (`playlist.triggerLiveClip(track, -1,
midi.TLC_Fill)`). **Starting** a clip is deliberately left to FL's own
note-triggered playback — the script just lets the remapped note (from
`eventHandler`) pass through untouched, and FL starts the clip itself
based on that note value. (While **stopped**, this method does something
different — see "clip staging while stopped" below.)

An earlier version tried calling `triggerLiveClip(row, col, 0)` explicitly
for starting too, mirroring the stop path. That broke starting for **every**
row on real hardware — `flags=0` doesn't reproduce whatever raw-note
triggering actually does internally — and was reverted. Because
`mapping.performance_note_for(track, col)` computes the note dynamically
(using the same `track_offset` as this method), passthrough-based starting
is scroll-aware for free, without needing any explicit start API call.

The stop call itself:

```python
status = playlist.getLiveBlockStatus(track, col, 0)
if status & 4:
    # blockNum=-1 + TLC_Fill stops whatever's currently playing on this
    # track/row (only one block per row can play at a time, so this is
    # equivalent to stopping this specific block).
    playlist.triggerLiveClip(track, -1, midi.TLC_Fill)
```

`blockNum=-1` isn't "no block" — combined with `midi.TLC_Fill`, it targets
whatever's currently playing on `track`, regardless of which column. Since
only one block per row/track can play at a time, that's equivalent to
targeting this specific `col` — but written as `-1` because FL doesn't
require (or necessarily want) the exact column for a stop.

### Clip staging while stopped

Reported: while the song is **stopped**, pad presses in performance mode
were doing nothing but sounding the pressed note directly like a keybed
key — none of the "select a clip so it starts on the next PLAY" behavior
the flashing (scheduled) LED state already implies is possible (a clip can
already end up flashing/scheduled some other way — e.g. selecting it in
FL's own UI — and `OnUpdateLiveMode`'s existing scheduled-bit check already
visualizes that correctly). The ask: let a pad press **while stopped**
stage/select a clip the same way, instead of just sounding a note.

```python
if not self.state.isPlaying():
    status = playlist.getLiveBlockStatus(track, col, 0)
    if status & 1:  # only for a filled block
        playlist.triggerLiveClip(track, col, midi.TLC_Queue)
        event.handled = True
    return
```

`midi.TLC_Queue` (`1 << 2`, from `midi.__tlc_flags`) is the flag used. This
is the **least-documented part of this feature** — the community API stub
repo itself only says `"""Queue mode."""` for it, no further detail (most
of the other `TLC_*` flags are literally marked `TODO` in the same file).
The working theory, based on the flag's name and this being the obvious
gap in the existing stop/start pair, is that it selects/arms a block
without starting it — which would set the same "scheduled" bit
`OnUpdateLiveMode` already reads and flashes for.

Guarded on `status & 1` (filled) so pressing an empty pad still falls
through unhandled (passes through as a note, same as before) rather than
calling `triggerLiveClip` on nothing. `event.handled = True` on a
successful stage prevents the raw note from also sounding — same
mechanism the stop path already relies on (see `eventHandler`: nothing
resets `event.handled` after this method runs, regardless of what happens
to `event.data1` afterward).

**Entirely unverified on real hardware — this is the most speculative
change in the script right now.** Specifically unconfirmed: (1) does
`TLC_Queue` actually select/arm the block without sounding it or starting
playback, (2) does it show up as the existing "scheduled" flash, (3) does
staging a *different* block on the same track/row automatically supersede
a previously-staged one on that row (assumed, based on the established
"only one block per row can play/be scheduled at a time" pattern used
elsewhere, but not confirmed for this specific flag), (4) does pressing
PLAY afterward actually start the staged clip. If `TLC_Queue` turns out not
to do what its name suggests, this whole block needs revisiting — it was
implemented on the strength of the flag's name and being the one clear gap
in the API, not on confirmed documentation or a real test.

---

## `_handle_shift` — the provisional `event.handled` blanket

**Location:** `DeviceHandler._handle_shift`, ~line 512.

`event.handled = True` is set unconditionally here (and in the other
`_handle_*` methods for play/record/knobs) so FL doesn't also pass those
events through as raw MIDI on top of the script's own handling. This is
provisional — it hasn't been validated on hardware that blanket-handling is
correct for every one of those event types; it may eventually need to be
decided per-event-type instead. Revisit if any of shift/play/record/knobs
end up needing to also reach FL as regular MIDI.

---

## `_handle_shift` — engage/release visuals were inverted

**Location:** `DeviceHandler._handle_shift`, ~line 550.

The two branches' *state tracking* (`self.controlStates.set_active(...)`)
were always correct — SHIFT's `active` bool toggled properly on each press.
But the print statement and knob-ctrl-LED call in each branch were swapped
relative to what they were tracking:

- Branch taken when SHIFT **was already active** (this press *releases*
  it) printed `"shift active"` and called `set_knob_ctrl_dim(True)`
  (dims the LEDs — per that method's own docstring, `dimmed=True` means
  "SHIFT engaged").
- Branch taken when SHIFT **was not active** (this press *engages* it)
  printed `"shift inactive"` and called `set_knob_ctrl_dim(False)`
  (brightens — "SHIFT released").

Reported symptom matched exactly: right after script load (SHIFT starts
released, per `ControlState.active`'s dataclass default of `False`), the
*first* press — which engages SHIFT — printed `"shift inactive"`; the
*second* press — which releases it — printed `"shift active"` and dimmed
the knob-ctrl LEDs. Purely a display-side bug, not state corruption: the
commented-out `set_func_buttons(..., flash=...)` lines in each branch were
already correctly aligned (flash-on-engage, stop-flash-on-release), which
is what confirmed the intended design and made this a low-risk fix — just
swap which branch does which visual, not the branch conditions themselves.

Fixed: engage branch (`else`, SHIFT was not active) now prints `"shift
engaged"` and dims (`set_knob_ctrl_dim(True)`); release branch (`if
self._shift_active()`) now prints `"shift released"` and brightens
(`set_knob_ctrl_dim(False)`).

**Unverified on real hardware** — logically self-evident from the code
(the state/visual mismatch was unambiguous), but needs a real SHIFT press
to confirm the LEDs now dim on engage and brighten on release, matching
`set_knob_ctrl_dim`'s own documented semantics.

---

## `_handle_record` — why `toggleRecord` is called on every press

**Location:** `DeviceHandler._handle_record`, ~line 554.

```python
if event.data2 == 127:
    # Called on every press — see DEV_NOTES.md: _handle_record.
    self.controls.toggleRecord()
```

`TransportHandler.toggleRecord()` is called unconditionally on every REC
press — not just when recording is being turned *on*. That's deliberate:
`toggleRecord()` calls `transport.record()` and then resyncs `SessionState`
from FL itself. If it were only called while turning recording on, there'd
be no way for this script to ever tell FL to *stop* recording via the same
codepath — a press while already recording needs to reach `transport.record()`
too, since that's what actually toggles FL's recording state off again.

---

## `PerformanceMode.__init__` — "Operation unsafe at current time" crash, and selecting tracks only on real performance-mode entry

**Location:** `PerformanceMode.__init__` and `on_script_ready`, ~line 925;
the reactive check lives in `OnUpdateLiveMode`; module-level `OnInit`
wires it up.

### The crash (original issue, still applies)

`select_tracks()` (which calls `playlist.selectTrack()` / `deselectAll()`)
is deliberately **not** called from `__init__`. Calling either of those
during module-level construction (i.e. while the script is still importing)
raises `RuntimeError: Operation unsafe at current time` — confirmed the hard
way on real hardware. Read-only playlist calls (`getLiveBlockStatus`, etc.,
used by the initial `OnUpdateLiveMode(0)` call in `__init__`) are fine at
import time; only *mutating* playlist calls need to wait.

**BAD** — calling a mutating playlist API from `__init__` crashes at script load:

```python
class PerformanceMode:
    def __init__(self, lighting, state):
        self.lighting = lighting
        self.state = state
        self.pos = mapping.LIVE_GRID_PAD_POSITIONS
        self.track_offset = 0

        self.select_tracks()       # <-- RuntimeError: Operation unsafe at current time
        self.OnUpdateLiveMode(0)

# Module-level construction, i.e. still importing:
live = PerformanceMode(lighting, state)   # crashes here, script never finishes loading
```

### The second bug (found later): selecting tracks regardless of mode

The original fix deferred the mutating call to `OnInit()` — safe from the
crash, but `OnInit()` called `live.select_tracks()` **unconditionally**,
every time the script loaded, whether or not FL was actually in performance
mode. In standard/normal mode this silently deselected whatever tracks the
user had selected and force-selected tracks 1-5 instead — and then, when
the user later switched into performance mode for real, the tracks
*weren't* re-selected to match (since that only ever happened once, at
load). Reported as: normal-mode track selection getting clobbered at
script load, and performance mode's own track highlighting not actually
working when entered later.

**Fix:** track selection now happens reactively, exactly when FL's
performance-mode state actually transitions from off to on — not
unconditionally at load. Two pieces:

1. `PerformanceMode.on_script_ready()` — called once from `OnInit()`, once
   mutating playlist calls are safe. Seeds `_performance_was_active` from
   `playlist.getPerformanceModeState()`; if performance mode is *already*
   active at load (e.g. reopening a project that was saved mid-performance-
   mode), selects tracks immediately — the one case where "select at load"
   is actually correct. Also flips `_can_select_tracks` on, arming the
   check below (this flag exists specifically so the reactive check can't
   accidentally fire during the constructor's own unsafe-to-mutate
   `OnUpdateLiveMode(0)` call).
2. `OnUpdateLiveMode` — on every call (which FL fires on live-grid changes,
   including performance-mode toggles), compares the current
   `playlist.getPerformanceModeState()` against the tracked previous value.
   On a false→true transition, calls `select_tracks()`. This also means
   toggling out of and back into performance mode later re-selects
   correctly each time, which the old one-shot-at-load behavior could
   never do.

**GOOD:**

```python
class PerformanceMode:
    def __init__(self, lighting, state):
        self.lighting = lighting
        self.state = state
        self.pos = mapping.LIVE_GRID_PAD_POSITIONS
        self.track_offset = 0
        self._can_select_tracks = False       # armed by on_script_ready()
        self._performance_was_active = False

        # select_tracks() is NOT called here — see on_script_ready() below.
        self.OnUpdateLiveMode(0)   # read-only (getLiveBlockStatus etc.) — safe at import time

    def on_script_ready(self):
        # Called from OnInit(), once mutating playlist calls are safe.
        self._can_select_tracks = True
        self._performance_was_active = playlist.getPerformanceModeState()
        if self._performance_was_active:
            self.select_tracks()   # already in performance mode at load — select now

    def OnUpdateLiveMode(self, value):
        if self._can_select_tracks:
            now_active = playlist.getPerformanceModeState()
            if now_active and not self._performance_was_active:
                self.select_tracks()   # just entered performance mode — select now
            self._performance_was_active = now_active
        # ... redraw pads ...

# Module-level construction — no mutating playlist calls yet, so this is safe:
live = PerformanceMode(lighting, state)

def OnInit():
    # FL calls this once the script has actually finished loading — mutating
    # playlist calls (selectTrack/deselectAll) are safe here.
    live.on_script_ready()
```

**Unverified on real hardware** — this is a behavior change to when track
selection happens, not just a refactor. Needs confirming: (1) normal-mode
track selection is no longer clobbered at script load, (2) entering
performance mode for the first time in a session now actually selects/
highlights tracks 1-5 (or the current scroll window), (3) leaving and
re-entering performance mode later re-selects correctly each time, (4) the
already-in-performance-mode-at-load case (`on_script_ready`'s immediate
select) still works.

---

## `OnMidiMsg` / `OnMidiIn` — dual-port dispatch via the performance-mode gate

**Location:** module-level `OnMidiMsg` (~line 1090) and `OnMidiIn` (~line 1106).

The APC Key 25 mk2 exposes two physical MIDI ports, but FL Studio unifies
both into these two callbacks itself — the script never needs to know which
physical port an event actually came from. Routing between the two callbacks
is driven by mode instead: `OnMidiMsg` only dispatches into
`DeviceHandler.eventHandler` while performance mode is active; `OnMidiIn`
only dispatches while it isn't. This `isPerformance()` gate is intentional
and is the single dispatch mechanism by design — it's been confirmed
sufficient in practice, not a known gap that still needs fixing.

---

## `_handle_sustain` — why SUSTAIN is a stub, and when that might need to change

**Location:** `DeviceHandler._handle_sustain`, ~line 613; the disambiguation
check that routes to it lives in `eventHandler`.

The device has a dedicated physical **SUSTAIN** button (not a TS pedal
jack). Its MIDI data byte (`0x40`) numerically collides with `track_1`
(`TRACK_BUTTONS`' `0x40`, a Note On/Off), so `eventHandler` disambiguates by
status byte (`event.status & 0xF0 == midi.MIDI_CONTROLCHANGE`) before any
note-keyed dispatch runs, and routes SUSTAIN to this stub.

**Confirmed via a real-hardware MIDI monitor log**, both the disambiguation
logic and the button's raw behavior:

```
90 40 5F  Note On : E5             <- a keybed note that happens to be 0x40
80 40 00  Note Off: E5
B0 40 7F  Control Change: Damper pedal (sustain)   <- SUSTAIN press
B0 40 00  Control Change: Damper pedal (sustain)   <- SUSTAIN release
```

Every one of those four lines was tagged `(generic controller)` by FL's
monitor — the role label for a port with **no script assigned**, i.e. the
main `APC Key 25 mk2` port this project's MIDI Settings guide (README.md)
explicitly says to leave unscripted, not `MIDIIN2` (the port this script is
actually bound to). In other words: SUSTAIN already reaches FL correctly,
entirely on its own, as a native Control Change on the unscripted port —
this script doesn't need to do anything for it to work, and currently
doesn't need to.

**That's why `_handle_sustain` stays a stub deliberately, not just as an
unfinished TODO**: there's nothing to implement right now. The
`eventHandler` disambiguation code is best understood as defensive
insurance — cheap, and correct per the confirmed status-byte split above —
for a collision that, per the hardware evidence, doesn't actually occur on
the port this script listens to today.

**When this would need real work:** if the main/generic port ever gets a
script assigned to it in the future (e.g. to remap SUSTAIN to something
else, or handle it more deliberately), that script would take over routing
for the port FL currently handles natively — at that point a real
pass-through handler would be needed so plain sustain-pedal behavior into
FL isn't lost. Not a current need; flagged here so the reason doesn't have
to be re-discovered from scratch later.

---

## `OnUpdateLiveMode` — clip-transition LED behavior (flashing vs. solid)

**Location:** `PerformanceMode.OnUpdateLiveMode`, ~line 1001.

`getLiveBlockStatus(row, col, 0)` returns a bitmask: filled=1, scheduled=2,
playing=4. Before this behavior existed, the code only special-cased the
combined value `active == 7` (filled+scheduled+playing, i.e. a block that's
actually playing) as the "solid, distinct color" state, and treated
*everything else* truthy — including a block that's filled+scheduled but
**not yet playing** (queued to launch next in that row on the next
bar/beat) — identically to a plain filled-but-idle block. That meant a
pending clip transition was invisible on the pads: the about-to-launch clip
looked exactly like every other filled-but-not-playing clip in the row
until the moment it actually started.

Fixed by checking the `playing` (4) and `scheduled` (2) bits independently
instead of only matching the combined `== 7` case:

```python
is_playing = bool(active & 4)
is_scheduled = bool(active & 2)
if is_playing:
    # solid, bright_4 mode, color 6
elif is_scheduled:
    # queued to start next, not playing yet — pulse_1_4 mode instead of bright_4
else:
    # merely filled, not scheduled — solid, bright_4 mode, color 1 (unchanged)
```

The queued-but-not-yet-playing case now uses `PAD_LED_FUNCTION`'s
`pulse_1_4` mode (a quarter-note-rate flash, one of the previously-unused
`pulse_*`/`blink_*` LED behaviors already defined in `mapping.py`) instead
of `bright_4`, so it visibly flashes on the device until FL actually starts
it — at which point `active` becomes `7` again and it's redrawn solid.
`pulse_1_4` was picked as a reasonable default flash rate, not derived from
any specific requirement; if it reads as too fast/slow on real hardware,
swapping to a different `pulse_*`/`blink_*` id is a one-line change.

**Unverified on real hardware:** whether FL's `getLiveBlockStatus` actually
reports `2` (scheduled, not yet playing) in practice for a queued clip on
this device/FL version — the original `== 7` check implies it does (some
transitional state must exist for a queue to be visible at all), but the
flashing behavior itself hasn't been confirmed against real playback yet.

---

## `OnUpdateLiveMode` — one-shot auto-clear

**Location:** `PerformanceMode.OnUpdateLiveMode`, ~line 1007;
`_was_playing` is initialized in `PerformanceMode.__init__`.

Reported behavior: if a track's loop mode is "One shot" and its clip is
selected/playing when the song is stopped and then restarted with PLAY,
the one-shot clip plays again on restart — it needs to be fully
"deselected"/cleared after it naturally finishes, not just left alone,
or FL treats it as still armed.

**"One shot" is a track-level setting, not per-block.** Confirmed straight
from FL's own API stub source
(`IL-Group/FL-Studio-API-Stubs`, `playlist/__performance.py`):
`playlist.getLiveLoopMode(index) -> int`, where `1` = `LiveLoop_OneShot`.
There's no separate per-clip one-shot flag — every block on a one-shot
track shares the track's loop mode.

Fix: `OnUpdateLiveMode` already loops every block on every visible track
each redraw to draw LEDs; that same loop now also accumulates whether
*any* block on the track is currently playing (`track_now_playing`). This
is compared against `self._was_playing[track]` (set at the end of the
previous redraw). When a track transitions from playing to not-playing
(`was_playing and not track_now_playing`) **and** its loop mode is
one-shot, the script calls `playlist.triggerLiveClip(track, -1,
midi.TLC_Fill)` — the same "stop whatever's playing on this track" call
`_handle_pad_performance_trigger` already uses for a manual pad-press stop
— to explicitly drop FL's armed/queued state for that track:

```python
was_playing = self._was_playing.get(track, False)
if was_playing and not track_now_playing and playlist.getLiveLoopMode(track) == 1:
    playlist.triggerLiveClip(track, -1, midi.TLC_Fill)
self._was_playing[track] = track_now_playing
```

This only fires on a *natural* finish (playing → not playing with no
manual stop in between) — a manual pad-press stop already clears the track
itself via the existing stop-trigger path, so this wouldn't double-fire
for that case; it would just observe `track_now_playing` already `False`
on the next redraw with no `was_playing → now stopped` transition left to
catch.

**Entirely unverified on real hardware — this is the speculative part.**
Confirmed facts: the one-shot detection API (`getLiveLoopMode(track) == 1`)
is real, and the `triggerLiveClip(track, -1, TLC_Fill)` clear call is the
same one already confirmed working for manual stops. **Not confirmed:**
whether this actually stops the reported auto-replay-on-restart behavior,
whether `OnUpdateLiveMode` fires reliably at the exact moment a one-shot
clip finishes (vs. only on the next unrelated grid change), and whether
calling `triggerLiveClip` from inside `OnUpdateLiveMode` itself causes any
re-entrancy/timing issues (FL may re-invoke `OnUpdateLiveMode` as a result
of the clear call — believed harmless since `_was_playing[track]` is
already updated to `False` by the time that would happen, so it shouldn't
re-trigger a second clear, but this hasn't been observed in practice).

---

## `_handle_track_button` / `_handle_scene_button` — mode-based naming, not SHIFT-gated

**Location:** `DeviceHandler._handle_track_button`, ~line 629;
`_handle_scene_button`, ~line 665.

Track scroll (SHIFT+up/down) originally required holding SHIFT *while
already in Performance Mode* to work: `if self.state.isPerformance() and
self._shift_active():`. Reported as awkward — Performance Mode and Normal
Mode are meant to be two distinct controller states, and requiring an
extra SHIFT press/hold on top of already being in Performance Mode (rather
than performance mode itself acting as the "shifted" context) didn't match
that model. The earlier proposed fix was to auto-engage the internal SHIFT
flag when FL enters performance mode; the design actually chosen instead
removes SHIFT from the equation entirely for these buttons.

**New design:** Performance Mode and Normal Mode each unconditionally pick
one name set for the 8 track buttons / 5 scene buttons — SHIFT is no
longer part of the decision in Performance Mode at all:

- **Performance Mode:** always `TRACK_BUTTONS_SHIFT`/`SCENE_BUTTONS_SHIFT`
  (up/down/left/right/knob_vol/pan/send/device; clip_stop/solo/mute/
  rec_arm/select). Up/down scroll immediately, no SHIFT needed. Everything
  else in that name set is still an unimplemented stub, same as before —
  only the naming/no-SHIFT-needed part changed for those.
- **Normal Mode:** unchanged — SHIFT still toggles between
  `TRACK_BUTTONS`/`SCENE_BUTTONS` (default) and the `_SHIFT` name sets,
  exactly as it always did.

```python
def _handle_track_button(self, event):
    if self.state.isPerformance():
        name = mapping.TRACK_BUTTONS_SHIFT[event.data1]
        if name in ("up", "down"):
            ...scroll...
            return
        log_status(f"[stub] track button '{name}' ...")
        return
    # Normal Mode only, from here down: SHIFT still picks the name set.
    name = mapping.TRACK_BUTTONS_SHIFT[event.data1] if self._shift_active() else mapping.TRACK_BUTTONS[event.data1]
    ...
```

Low functional risk: every name in the shift-name sets besides up/down was
already an inert stub before this change (regardless of mode or SHIFT
state), so the only real behavior change is that scroll no longer needs
SHIFT in Performance Mode. `_shift_active()` itself, and everything it
still gates (`knob_ctrl` dim/bright), is untouched.

**Unverified on real hardware:** confirm up/down scrolls immediately in
Performance Mode without SHIFT held, and confirm Normal-Mode SHIFT-toggled
naming for track/scene buttons still works exactly as before (regression
check — the Normal-Mode branch is functionally identical to the old code,
but got restructured alongside the Performance-Mode branch).

---

## `OnUpdateLiveMode` — performance-mode gate (periodic LED flash investigation)

**Location:** `PerformanceMode.OnUpdateLiveMode`, ~line 1045; module-level
`OnUpdateLiveMode`, ~line 1145.

Reported symptom (BUG_NOTES.md): pad LEDs set to max brightness briefly
flash every ~5-6 seconds, no discernible pattern even in slow-motion video.

### Audit

Every pad-LED write path was traced:

- `PadLighting.cycle_pads()` (the startup on/dim sweep) — one-shot only,
  called once from `PadLighting.__init__`. Not a candidate for a recurring
  flash.
- `_handle_pad_performance_trigger`, `eventHandler`'s pad remap — both
  explicitly gated on `self.state.isPerformance()` already, and only fire
  in response to an actual pad press, not periodically.
- `ControlStateStore.set_led`'s diffing (skip sending if `(mode, color)`
  unchanged) — checked carefully, logic is correct. Repeated calls with
  identical `(mode, color)` reliably return `changed=False` after the
  first time; this is not a redundant-resend bug.
- **`OnUpdateLiveMode` — the one thing that repaints pad LEDs on an
  ongoing basis — had no performance-mode check at all**, at either the
  module-level callback or inside `PerformanceMode.OnUpdateLiveMode`
  itself. Every other pad-lighting write path is either one-shot or
  explicitly mode-gated; this was the only exception.

### Why that's a plausible cause

FL calls `OnUpdateLiveMode` whenever live-block status changes — and live
blocks track filled/scheduled/playing state during **ordinary linear
playback too**, not just while Performance Mode is visually active. A
playlist loop, or simply playback crossing a block boundary repeatedly,
can fire this callback periodically even in Normal Mode. Without a gate,
the script would still repaint the entire grid with live-clip colors on
every such call — including briefly painting the "playing" state (bright,
color `6` — the max-brightness case in the report) on pads that should
just be sitting at the idle dim color, since nothing in Normal Mode ever
repaints them back afterward except the *next* stray call. If the
recurrence interval happens to line up with something like a playlist
loop length, that would produce exactly an irregular-looking periodic
flash matching the report.

**This has not been confirmed as *the* root cause on real hardware** — it's
the strongest lead the code audit turned up (the one asymmetry in an
otherwise-consistent set of mode-gated write paths), not a proven
diagnosis. A second, unconfirmed possibility that this fix does **not**
address: a genuinely playing clip's status bitmask could still transiently
report something other than the full "playing" bitmask for a single frame
at its own loop-restart boundary, which would cause a real (correctly
diffed, not buggy) brief flash purely *within* Performance Mode, once per
loop cycle. That would need debounce/hysteresis logic to fix, and hasn't
been investigated further since the missing gate was the more clear-cut
finding.

### Fix

`OnUpdateLiveMode` now checks `playlist.getPerformanceModeState()` — read
fresh on every call, not the cached `state.isPerformance()`, since this
callback can fire from a live-block change with no accompanying MIDI event
to have refreshed that cache — and returns before touching any pad LEDs if
performance mode isn't actually active:

```python
def OnUpdateLiveMode(self, value):
    now_active = playlist.getPerformanceModeState()
    if self._can_select_tracks:
        if now_active and not self._performance_was_active:
            self.select_tracks()
        self._performance_was_active = now_active

    if not now_active:
        return   # not performance mode's callback to act on right now

    # ... existing grid redraw, unchanged ...
```

The performance-mode-entry track-selection check (see the
`PerformanceMode.__init__` entry above) deliberately stays **outside** the
gate and runs on every call regardless — it needs to observe the
off→on transition itself, so it can't be skipped just because the mode
isn't (yet) active.

**Safety check already covered by existing guards:** the one-shot
auto-clear logic (which calls the mutating `playlist.triggerLiveClip`) is
inside the now-gated redraw loop. This doesn't reintroduce the "Operation
unsafe at current time" crash risk during `PerformanceMode.__init__`'s own
`self.OnUpdateLiveMode(0)` call, even if a project happens to already be
in performance mode at load (`now_active=True` that early): `_was_playing`
starts as an empty dict, so `was_playing` is always `False` on that very
first call, and the one-shot-clear condition (`was_playing and not
track_now_playing and ...`) can never be satisfied there regardless of
`now_active`.

**Status when written:** unverified, this gate was the strongest lead the
code audit turned up. See the update immediately below — real hardware
testing found the actual cause, and it's unrelated to this gate.

---

## ROOT CAUSE CONFIRMED: low RGB-palette color indices (1, 2) flicker on real hardware

**Location:** `PadLighting.__init__`'s `self.initialColor` (~line 803);
`PerformanceMode.OnUpdateLiveMode`'s two `color=` args for the
"filled-but-not-playing" and "scheduled" pad states (~line 1117-1122).

The `OnUpdateLiveMode` performance-mode gate above was a reasonable lead
but **was not the actual cause**. Confirmed by direct hardware testing:
setting `self.initialColor = 0x03` (white) eliminates the flash; `0x01`
(`#1E1E1E`) or `0x02` (`#7F7F7F`) both reproduce it. This is a pad-LED
write with a completely static `(mode, color)` value sent once and never
touched again by anything else — there's no polling, no redraw loop, no
repeated send involved for that specific pad in that state. The flicker is
therefore **not caused by anything in this script's control flow** — it's
the device itself periodically re-rendering/animating specific low
velocity-palette indices, independent of which LED mode/channel byte they
were set with.

This lines up with (but goes beyond) what `docs/LED_COLOR_SCHEME.md`
already documents for the *other* LED subsystem: single-color track/
scene/stop/play/record buttons treat velocity `0x02` specifically as
"blink" (`0x00`=off, `0x02`=blink, anything else=on) — a hardcoded
firmware behavior for specific low velocity values, unrelated to the
`9X`-channel brightness/pulse-rate selection documented for the RGB pad
grid. The RGB pad palette (`velocity_to_hex_rgb` in
`akai_apc_key_25.yaml`) was assumed to be a plain ROM color lookup table
with no special-cased indices, per the doc's own description ("This
palette cannot be changed — it's ROM, not RGB math") — but real-hardware
behavior says otherwise: indices `1`/`2` cause periodic flicker on the pad
grid too, undocumented in the protocol PDF this project's docs are sourced
from.

**Fix:** every pad-LED color value in the script was audited for `1`/`2`
and moved to `3`+ (all changed to `3`, white, matching the confirmed-safe
value):

- `PadLighting.__init__`: `self.initialColor` (the idle/default color used
  everywhere a pad is turned off via `set_pad(pad, False)`) — `0x02` → `0x03`.
- `OnUpdateLiveMode`'s "filled but not playing" state (`bright_4`) —
  `color=1` → `color=3`.
- `OnUpdateLiveMode`'s "scheduled, not yet playing" state (`pulse_1_4`) —
  `color=1` → `color=3`.

The `OnUpdateLiveMode` performance-mode gate documented above is **still
correct to keep** — repainting pad LEDs while not in performance mode was
a real (if different) bug regardless of whether it caused this particular
flash — but it should not be credited as the fix for the reported symptom.

**Still worth doing, not yet done:** a systematic check of which other
palette indices (beyond confirmed-bad `1`/`2` and confirmed-safe `3`) are
safe, so future color choices (e.g. wanting something other than white for
the idle/scheduled states) don't accidentally reintroduce this. Nothing in
`akai_apc_key_25.yaml` currently documents this quirk — worth adding once
more indices are tested, so it doesn't have to be rediscovered by hardware
trial-and-error again.

**Confirmed on real hardware** for `self.initialColor` specifically (`0x01`/
`0x02` flicker, `0x03` doesn't). The two `OnUpdateLiveMode` color=1→3
changes apply the same fix by inference (same palette, same underlying
mechanism) but have **not** been independently re-tested after the change.

---

## `OnUpdateLiveMode` — track-color rows

**Location:** `mapping.COLOR_MAP` / `closest_color_index` /
`closest_color_index_for_fl_color` in `mapping.py`; consumed in
`PerformanceMode.OnUpdateLiveMode`, ~line 1108.

FL Studio lets the user set an arbitrary RGB color per playlist track.
This device can only render one of 128 fixed, ROM palette colors per pad
(see `docs/LED_COLOR_SCHEME.md`) — arbitrary RGB is only possible via the
SysEx RGB Color Lighting message, which doesn't work on this hardware
(script header entry, above). So "match the row color to the track color"
necessarily means finding the *closest available* palette color, not an
exact match.

`mapping.COLOR_MAP` is the same 128-entry `velocity_to_hex_rgb` table
from `akai_apc_key_25.yaml`, as a `{index: (r, g, b)}` dict.
`closest_color_index(r, g, b)` does a brute-force nearest-neighbor search
over it (squared Euclidean distance in RGB space — no need for the actual
Euclidean distance since we only care about relative ordering, and this
avoids a `sqrt` call for no benefit). `closest_color_index_for_fl_color`
wraps that for FL's own color int format (`0x--BBGGRR` — confirmed from
the FL API stub source, `playlist.getTrackColor`'s docstring; **note the
byte order is red-green-blue from low byte to high byte, not RGB-in-that-
order** — easy to get backwards).

**`COLOR_MAP_UNSAFE_INDICES = {1, 2}`** — the two flickering indices from
the section above — are excluded from the search entirely, so track-color
matching can never accidentally land on a flickering index (e.g. a very
dark or very grey track color, which would otherwise be the nearest match
to exactly those two entries).

### Why brightness/pulse channel carries state instead of color

Before this change, each row used a *fixed* set of colors regardless of
which track occupied it — `color=6` (playing), `color=3` (idle/scheduled).
Once color is repurposed to mean "which track," it can no longer also mean
"what state is this block in" — so state (playing / scheduled / idle) is
now conveyed by the LED brightness/pulse channel instead, with the track's
color held constant across all three:

```python
track_color = mapping.closest_color_index_for_fl_color(playlist.getTrackColor(track))
...
if is_playing:
    set_pad(pad, True, mode=PAD_LED_FUNCTION.id_for("bright_6"), color=track_color)   # solid, 100%
elif is_scheduled:
    set_pad(pad, True, mode=PAD_LED_FUNCTION.id_for("pulse_1_4"), color=track_color)  # flashing
else:
    set_pad(pad, True, mode=PAD_LED_FUNCTION.id_for("bright_2"), color=track_color)   # solid, 50% (dimmer)
```

`bright_6`/`bright_2` (100%/50%) were picked to keep a clear visual gap
between "playing" and "filled but idle" now that hue can't do that job —
arbitrary choice, easy to retune if it doesn't read clearly on hardware.

**Superseded, per user request:** the playing state no longer uses
`track_color` at all — it now uses a fixed `mapping.PLAYING_INDICATOR_COLOR`
(bright green, palette index 21, `#00FF00`) instead, so the active clip in
a row is unambiguous regardless of that track's hue, rather than just
"the same color but brighter." Scheduled/idle still use `track_color`.
Reverting when a different pad becomes the playing one needed no extra
code — the whole grid is redrawn from current `getLiveBlockStatus` every
call, so a block that stops playing simply falls into the scheduled/idle
branch (track color) on the very next redraw.

### Scrolling

No special handling needed — `track = idx + self.track_offset` was already
recomputed every redraw before this change, and `track_color` is looked up
from that same `track` value inside the per-row loop, so scrolling
naturally picks up the newly-visible track's color on the very next
redraw, same as everything else that's `track_offset`-aware.

### Performance cost

`getTrackColor` + a 128-entry (minus 2 excluded) linear scan runs once per
visible row per `OnUpdateLiveMode` call — 5 extra lookups per redraw, not
per pad. Only matters if `OnUpdateLiveMode` turns out to fire very
frequently in practice; not optimized preemptively (no caching) since
there's no evidence yet that it needs to be. If it does become a problem,
the natural fix is caching `track -> track_color` and invalidating only
when `getTrackColor(track)` actually changes.

**Entirely unverified on real hardware.** Needs testing: (1) do rows
actually take on a visually reasonable approximation of their track's FL
color, (2) is the playing/idle brightness distinction (100% vs 50%) clear
enough at a glance, (3) does the color update correctly when scrolling to
a different track, (4) does a newly-changed track color (edited live in FL
while performance mode is running) get picked up on the next redraw.

### Bug found on first hardware test: R and B were swapped

First real-hardware photo showed every row as some shade of blue/white —
no reds, greens, purples, or tans, despite the FL Studio playlist tracks
in the same screenshot clearly having a red track, a green track, a purple
track, an olive/tan track, etc. That ruled out a simple "imperfect nearest
match" (which would still produce a *variety* of hues, just approximate
ones) and pointed at the color extraction itself.

`closest_color_index_for_fl_color` had followed `playlist.getTrackColor`'s
own docstring literally: `0x--BBGGRR` (red = low byte, blue = high byte).
But FL's own **canonical** conversion utilities —
`utils.ColorToRGB`, `utils.RGBToColor`, and `utils.RGBToHSVColor`, three
independent functions in the same stub repo — all agree on the opposite:
`R = (Color >> 16) & 0xFF` (high byte), `B = Color & 0xFF` (low byte), i.e.
`0xRRGGBB`. The single `0x--BBGGRR` mention on `getTrackColor` appears to
just be a documentation error in that community-maintained repo,
contradicted by every other authoritative source of the same convention.

Fixed by swapping the extraction to match the canonical utilities:

```python
# Before (wrong — matched getTrackColor's docstring, not the canonical utils):
r = fl_color & 0xFF
g = (fl_color >> 8) & 0xFF
b = (fl_color >> 16) & 0xFF

# After (correct — matches utils.ColorToRGB/RGBToColor/RGBToHSVColor):
r = (fl_color >> 16) & 0xFF
g = (fl_color >> 8) & 0xFF
b = fl_color & 0xFF
```

A red track was being read as if it were blue (R and B fully swapped),
which explains the photo exactly. Sanity-checked post-fix: a dark red
input now matches palette index `61` (`#993500`, a plausible reddish-
brown) instead of a blue index.

**Still needs real-hardware re-verification** — the swap is logically
confirmed and the arithmetic checks out, but the actual on-device visual
result with this fix hasn't been photographed yet.

### Second hardware test: R/B fix confirmed, but other rows still off — redmean tried and reverted

With the R/B fix in place, two specific FL track colors were confirmed to
produce good matches: `#2B642C` (green) and `#544F2B` (olive). But most
other rows in the same photo still looked blue/white — though the user
also noted the photo's camera may be shifting perceived color toward blue
(actual on-device color could be closer to white/grey than the photo
shows), so the photo evidence alone is not fully reliable here.

Working theory at the time: plain per-channel Euclidean distance is a
known-poor perceptual metric, and this palette has an unusually large
blue cluster (~19 of 126 usable entries) that could be dominating matches
for moderately desaturated colors. Tried switching to "redmean," a
well-known cheap perceptually-weighted distance formula
(https://www.compuphase.com/cmetric.htm), as a fix.

**This was reverted after checking it against the two already-confirmed-
good colors** — always verify a "fix" against existing known-good cases
before assuming it's an improvement, not just against the new failing
case:

| Input | Plain Euclidean (confirmed good) | redmean |
|---|---|---|
| `#2B642C` green | index 102 `(13,80,56)` | index 102 `(13,80,56)` — same |
| `#544F2B` olive | index 105 `(105,60,28)` — **confirmed good on hardware** | index 117 `(64,64,64)`, plain grey — **worse** |

redmean regressed a case that was already known to work, so it was
reverted back to plain Euclidean distance rather than kept. Separately,
purely as data (not yet hardware-confirmed either way): a few plausible
muted track colors (dark teal `#2C4A5E`, purple `#4B3A6B`) landed on
index 117 (plain grey) under **both** distance formulas — same result
either way, meaning this specific outcome isn't something the distance
metric changed at all. That raises a real possibility worth checking
before trying another distance-formula change: grey may simply be the
closest *available* match for those particular muted hues in this
126-color palette (a palette limitation, not a bug) — especially
plausible given the user's own note that the photo's camera may be
over-representing blue/grey tones that look closer to correct in person.

**Next step, not yet done:** get the *exact* FL Studio hex color for each
row in a test photo (not just "it looked wrong") and manually trace
`closest_color_index_for_fl_color` against those specific values — this
is the only way to tell a genuine remaining bug apart from "the palette
doesn't have anything better for this hue" or "the camera made it look
worse than it is." Don't guess at another distance-formula swap without
that data; the redmean attempt shows guessing costs a real regression.

### Third hardware test: saturation-aware matching

Got the exact per-row FL hex colors this time:

| Row | Hex | HSV (hue/sat/val) |
|---|---|---|
| 1 | `#264259` | 207°, sat 0.57, val 0.35 |
| 2 | `#4B424D` | 289°, sat **0.14**, val 0.30 |
| 3 | `#592826` | 2°, sat 0.57, val 0.35 |
| 4 | `#676558` | 52°, sat **0.15**, val 0.40 |
| 5 | `#453172` | 258°, sat 0.57, val 0.45 |

Rows 2 and 4 are genuinely low-saturation (0.14-0.15) — near-neutral colors
where matching to grey is *correct*, not a bug. Rows 1, 3, 5 all have
sat=0.57 — the **same** saturation as the already-confirmed-good green
(`#2B642C`, sat 0.57) and close to olive (`#544F2B`, sat 0.49). Row 3 (red)
already matched fine (index 105). Rows 1 (blue) and 5 (purple) were the
real problem: both matched grey (index 117) under plain distance, despite
having a clear hue and the same saturation level that worked fine for
green.

Checked *why*, not just *that*: for Row 1 `(38,66,89)`, the top candidates
by plain RGB distance were grey (dist² 1305), then index 38 `(0,65,82)`
dark teal (dist² 1494) — only ~14% farther, and a much more sensible
match. Same pattern for Row 5: grey (2750) barely beat index 104
`(22,32,90)` dark indigo (3074, ~12% farther) and index 54 `(89,0,89)`
purple (3426, ~25% farther). Plain distance wasn't *wrong* exactly — grey
genuinely is numerically closest for these specific inputs — but it was
winning by a small enough margin that a modest nudge could fix it without
resorting to a full metric overhaul (which redmean already showed can
easily do more harm than good).

**Fix:** added a saturation-mismatch penalty on top of (not instead of)
plain RGB distance — `_saturation_penalty_weight * 255² * (input_sat -
candidate_sat)²`. Grey candidates always have saturation 0, so this
penalizes them specifically when the input has real saturation to lose,
while leaving already-low-saturation inputs (rows 2/4) essentially
unaffected (their penalty term is small regardless, since `input_sat` is
already close to 0). Weight calibrated by testing 0.025/0.05/0.1 against
all 7 known data points (5 rows + 2 previously-confirmed-good colors) —
identical results across that whole range, so 0.05 was picked as a stable
middle value, not a fragile threshold:

| Input | Before (plain distance) | After (+ saturation penalty) |
|---|---|---|
| Row 1 blue `#264259` | index 117, grey | **index 104, dark indigo** |
| Row 2 near-grey `#4B424D` | index 117, grey | index 117, grey — unchanged |
| Row 3 red `#592826` | index 105 | index 105 — unchanged |
| Row 4 near-grey `#676558` | index 118, grey | index 118, grey — unchanged |
| Row 5 purple `#453172` | index 117, grey | **index 104, dark indigo** |
| green `#2B642C` (confirmed good) | index 102 | index 102 — unchanged |
| olive `#544F2B` (confirmed good) | index 105 | index 105 — unchanged |

Both previously-broken cases now match a colorful, hue-appropriate entry;
every previously-correct case (including the two already confirmed on
real hardware) is untouched. This is the key difference from the redmean
attempt — that was checked against zero known-good cases before being
applied; this one was checked against all seven before being kept.

**Still needs actual real-hardware confirmation** — the math and the
calibration are solid, but nobody has looked at the device with this
specific fix applied yet. Also note Row 1 and Row 5 now match the *same*
palette index (104, dark indigo) despite being visually distinguishable
hues (blue vs. purple) to a human — an inherent consequence of only 126
usable palette entries; worth knowing going in so it isn't mistaken for a
new bug if two differently-colored tracks end up on visually similar rows.

---

## `knobAdjust` — two real bugs found on real hardware

**Location:** `DeviceHandler.knobAdjust`, ~line 469.

The 8 knobs send a relative-encoder byte: values `101`-`127` mean "turned
down" (encoded as `127` minus the delta), values `1`-`27` mean "turned up"
(the delta more directly). Both branches decode that into a per-knob
absolute value accumulated in `self.knobs`.

### Bug 1: invalid MIDI value (fixed earlier)

The up-branch clamp allowed the accumulator to reach `128` — an invalid
7-bit MIDI data byte, genuinely sent to FL as `event.data2` at the top of
a fast knob turn. Clamped to `127`. (This one predates this section; see
TESTING_CHECKLIST.md §3 for the original log evidence.)

### Bug 2: asymmetric minimum delta between directions

Reported: turning a knob up slowly from a low value produces a minimum
delta of `+2`, never `+1`; turning down slowly correctly bottoms out at
`-1`. The two branches used different formulas for `vel`:

```python
# Down branch: vel = 127 - value. At the slowest possible down turn
# (value=127), vel=0, so delta = vel+1 = 1.
vel = (value - 127) * -1

# Up branch, before the fix: vel = value directly. At the slowest possible
# up turn (value=1), vel=1, so delta = vel+1 = 2 — delta=1 is unreachable.
vel = value
```

Fixed by using `vel = value - 1` in the up branch, so it reaches `vel=0`
at `value=1` the same way the down branch reaches `vel=0` at `value=127`:

```python
vel = value - 1
```

Verified by simulation across the full range: down produces delta `1`-`27`
for `value=127`-`101`; up now produces delta `1`-`27` for `value=1`-`27` —
identical ranges, symmetric in both directions.

**Confirmed on real hardware** (the asymmetry itself, via user testing);
**the fix is logically verified by simulation, not yet re-tested on
hardware** — confirm a slow upward turn now bottoms out at `+1`, and that
nothing about the fast-turn/large-delta behavior changed (the fix only
shifts `vel` by 1, it doesn't change the branch conditions or the `+27`
maximum).
