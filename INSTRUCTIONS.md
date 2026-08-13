# Instructions

How to set this script up in FL Studio, and what to expect once it's
running. This script is mostly autonomous — once MIDI Settings are
configured, there's nothing else to install or trigger; the reference
list below is here so you can tell "working as intended" apart from "not
working" without reading the code.

---

## MIDI configuration

The APC Key 25 mk2 shows up as **two ports per direction** in FL Studio's
MIDI Settings. This script must be assigned to the **second** port only —
the first is left alone so the keybed/generic controller keeps working
normally.

| Direction | Port | Setting |
|---|---|---|
| Output | `APC Key 25 mk2` | Leave unassigned — shows as the default "MIDI hardware port". |
| Output | `MIDIOUT2 (APC Key 25 mk2)` | Enable the port, set this script as the handler. |
| Input | `APC Key 25 mk2` | Leave unassigned — shows as "(generic controller)". |
| Input | `MIDIIN2 (APC Key 25 mk2)` | Enable the port, set this script as the handler. |

Also set **Performance Mode MIDI Channel: 1**.

Recommended: disable **"Link note on velocity to: Velocity"** — the APC
Key 25 mk2's key velocity sensing is poor, and linking it makes normal
keybed playing feel inconsistent.

Once the second port has this script assigned, everything below happens
automatically — no further setup, no menu to open, no button to press to
"activate" it.

---

## Expected behavior reference

### On script load

- Pads briefly clear to black, then settle to a dim idle color.
- Track/scene function button LEDs turn on.
- The 4 arrow buttons (up/down/left/right) light up **only if** the
  project is already in Performance Mode at load; otherwise they stay off.
- If the project is already in Performance Mode, the live-clip grid
  appears on the pads immediately and the visible tracks get selected in
  FL's playlist.

### Normal Mode (Performance Mode off)

- **Keybed keys** play notes normally — the script doesn't touch them.
- **Pads** pass through as plain notes (e.g. trigger a sampler pad) — no
  special coloring beyond the idle dim state.
- **Knobs** (8 above the pads) send smooth relative changes in both
  directions; each full turn accumulates into an absolute 1-127 value.
- **SHIFT** is a toggle: press once to engage (dims the 4 knob-control
  button LEDs, switches track/scene buttons to their alternate names),
  press again to release. It does not need to be held.
- **PLAY/Pause** and **REC** control FL's transport directly.
- **Track buttons** and **scene buttons** are currently stubs — pressing
  one is logged but does nothing audible or visible yet.
- **Stop/All Clips** and **SUSTAIN** are also currently stubs — SUSTAIN in
  particular is intentionally left alone, since FL already recognizes it
  natively as a damper pedal on the unscripted port; see `README.md` if
  curious why nothing needs to happen for it here.
- **Arrow buttons are off** in this mode.

### Entering Performance Mode

- The 4 arrow-button LEDs turn on.
- The visible 5 pad rows immediately redraw to match FL's live-clip grid.
- The corresponding 5 playlist tracks get selected in FL.

### Performance Mode — pad grid

- **Empty clip slot** → pad off/dim.
- **Filled, not yet playing** → pad lit dim, in that row's color (see
  "Pad row colors" below).
- **Filled and scheduled to start next** (queued) → pad **flashes**, same
  row color.
- **Currently playing** → pad **solid bright green**, regardless of that
  row's color — the active clip is always unambiguous.
- Pressing a pad whose clip is **already playing** stops it.
- Pressing a pad whose clip is **filled but not playing, while the song is
  playing** starts it normally.
- Pressing a pad whose clip is **filled, while the song is stopped**
  stages it (flashes) instead of sounding it directly — press PLAY
  afterward to actually start it. Press a different pad in the same row
  to stage that one instead.
- A track set to FL's **"One shot"** loop mode automatically clears itself
  once its clip finishes playing, so it won't unexpectedly replay the next
  time PLAY is pressed.

### Performance Mode — track scroll

- **up / down** (the same 2 of the 4 arrow buttons) scroll the visible
  5-row window up/down the playlist — no SHIFT needed.
- Row 1 can never scroll above track 1.
- Scrolling immediately redraws the pad grid and re-selects the 5 newly
  visible tracks in FL.
- **left / right** are currently unused (reserved).

### Pad row colors

- If `ATTEMPT_COLOR_GUESS` (near the top of `device_APCKey25mk2.py`) is
  `True`: each row approximates its actual FL Studio track color, picked
  from the device's fixed 128-color palette (not an exact match — closest
  available).
- If `False` (**the current default**): rows use a fixed legacy scheme
  instead — white for idle/scheduled pads, dark red for playing pads (the
  playing pad is still overridden to bright green either way).

### Leaving Performance Mode

- The 4 arrow-button LEDs turn off.
- Pad LEDs are left as they were (they're not actively managed outside
  Performance Mode) until the next event that touches them.

### Loading a different project

- Pads automatically clear/reset — a previous project's live-clip grid
  state (e.g. a pad left flashing) does not carry over.
- If the newly-loaded project is already in Performance Mode, its actual
  live-clip grid appears immediately and the arrow-button LEDs turn on to
  match.
- If it isn't, arrow-button LEDs and pads settle to their normal
  Normal-Mode state.

### On script unload / reassignment

- Track/scene function button LEDs turn off.
- All pads are set to a dim `bright_1` "unloaded" indicator, rather than
  being left however they last looked.

---

## Debug logging

Not required for normal use, but useful if something above doesn't match
what you're seeing. `DEBUG_LEVEL` near the top of `device_APCKey25mk2.py`:

| Level | Shows |
|---|---|
| `OFF` | Nothing. |
| `STATUS` | Init sequence, mode/transport changes, stub-button notices — safe to leave on. |
| `VERBOSE` (current default) | Everything above, plus per-event tracing and live-clip grid internals. Noisy — best for active troubleshooting only. |

Output appears in FL Studio's script output console (right-click the
script in MIDI Settings → "Show console" or similar, depending on your FL
Studio version).

---

## `ATTEMPT_COLOR_GUESS`

A toggle near `DEBUG_LEVEL`, at the top of `device_APCKey25mk2.py`,
controlling the pad-row coloring scheme described above under "Pad row
colors":

| Value | Behavior |
|---|---|
| `True` | Each Performance Mode row approximates its actual FL Studio track color, picked from the device's fixed 128-color palette (nearest available match, not exact). Costs one extra `playlist.getTrackColor()` lookup and palette search per visible row, per redraw. |
| `False` (**current default**) | Skips the per-track lookup entirely. Rows use a fixed legacy scheme instead — white for idle/scheduled pads, dark red for playing pads. |

The currently-playing pad is always overridden to solid bright green
either way — this toggle only affects the *row's base* color, not the
playing indicator.

This defaults to `False` because the track-color-matching feature is
newer and has gone through several rounds of real-hardware bug fixes (see
`docs/DEV_NOTES.md` and `TESTING_CHECKLIST.md` for the history); flip it to
`True` to try it, and back to `False` any time as an instant, no-side-effects
fallback if the color matching looks wrong for your project's track colors.

---

## Pad animation capability

`PadLighting` includes two animation methods — `animate_pads_on()` and
`animate_pads_off()` — that light pads one at a time in the order defined
by `mapping.START_PATTERN`, rather than all at once. They exist and work,
but are **not called anywhere by default** (their only call sites, in
startup and `OnDeInit`, are commented out) — the plain, instant `cycle_pads`
sweep is what actually runs today.

This is intentional, not an oversight: the animation is being kept as a
simple, low-stakes, self-contained piece of code for experimenting with —
a good starting point if you want to customize the startup/shutdown visual
without touching anything else in the script. To try it, in
`device_APCKey25mk2.py`:

- Startup: uncomment `#self.animate_pads_on(speed=0.05)` in
  `PadLighting.__init__`.
- Shutdown: uncomment `#lighting.animate_pads_off()` in `OnDeInit`.

`mapping.START_PATTERN` controls the order pads light up in — it's a
plain list of pad-ID rows and can be edited freely without touching any
other logic in the script.

