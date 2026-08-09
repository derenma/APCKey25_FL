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
- [`_handle_pad_performance_trigger` — why starting a clip isn't triggered explicitly](#_handle_pad_performance_trigger--why-starting-a-clip-isnt-triggered-explicitly)
- [`_handle_shift` — the provisional `event.handled` blanket](#_handle_shift--the-provisional-eventhandled-blanket)
- [`_handle_record` — why `toggleRecord` is called on every press](#_handle_record--why-togglerecord-is-called-on-every-press)
- [`PerformanceMode.__init__` — "Operation unsafe at current time" crash](#performancemode__init__--operation-unsafe-at-current-time-crash)
- [`OnMidiMsg` / `OnMidiIn` — dual-port dispatch via the performance-mode gate](#onmidimsg--onmidiin--dual-port-dispatch-via-the-performance-mode-gate)

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

## `_handle_pad_performance_trigger` — why starting a clip isn't triggered explicitly

**Location:** `DeviceHandler._handle_pad_performance_trigger`, ~line 387.

This method only ever **stops** an already-playing live-clip block
(`playlist.triggerLiveClip(track, -1, midi.TLC_Fill)`). **Starting** a clip
is deliberately left to FL's own note-triggered playback — the script just
lets the remapped note (from `eventHandler`) pass through untouched, and FL
starts the clip itself based on that note value.

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

## `PerformanceMode.__init__` — "Operation unsafe at current time" crash

**Location:** `PerformanceMode.__init__`, ~line 931.

`select_tracks()` (which calls `playlist.selectTrack()` / `deselectAll()`)
is deliberately **not** called from `__init__`. Calling either of those
during module-level construction (i.e. while the script is still importing)
raises `RuntimeError: Operation unsafe at current time` — confirmed the hard
way on real hardware. Read-only playlist calls (`getLiveBlockStatus`, etc.,
used by the initial `OnUpdateLiveMode(0)` call in `__init__`) are fine at
import time; only *mutating* playlist calls need to wait. The initial track
selection is deferred to the module-level `OnInit()` callback instead, which
FL only calls once the script has actually finished loading.

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

**GOOD** — the mutating call is deferred to `OnInit()`, which FL only invokes
once the script has actually finished loading; only the read-only redraw
stays in `__init__`:

```python
class PerformanceMode:
    def __init__(self, lighting, state):
        self.lighting = lighting
        self.state = state
        self.pos = mapping.LIVE_GRID_PAD_POSITIONS
        self.track_offset = 0

        # select_tracks() is NOT called here — see OnInit() below.
        self.OnUpdateLiveMode(0)   # read-only (getLiveBlockStatus etc.) — safe at import time

# Module-level construction — no mutating playlist calls yet, so this is safe:
live = PerformanceMode(lighting, state)

def OnInit():
    # FL calls this once the script has actually finished loading — mutating
    # playlist calls (selectTrack/deselectAll) are safe here.
    live.select_tracks()
```

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
