# Features and Fixes

A full comparison of `device_APCKey25mk2.py` (current) against the original
`dev/device_APCKey25mk2V2.py` — the last "hand-rolled" version before the
V2.1 rewrite and everything since. Organized as **New Features** (things V2
never did at all) and **Bug Fixes** (things V2 did, but wrong — split by
whether the bug was inherited from V2 or introduced during the rewrite
itself). See `DEV_NOTES.md` for the full investigation/reasoning behind
any individual item; this file is the index, not the detail.

---

## New Features

### Performance Mode

- **Track scroll (up/down)** — the pad grid can now show any 5 consecutive
  playlist tracks, not just tracks 1-5. V2 used a single hardcoded
  `self.map` dict wiring 40 fixed pad IDs to 40 fixed notes (tracks 1-5
  only, no way to reach track 6+). Replaced with
  `mapping.performance_note_for(track, col)`, a formula computed fresh per
  press using `track_offset`, so scrolling to any track works without a
  bigger lookup table.
- **Performance-mode pad stop** — pressing a pad whose clip is already
  playing now stops it (`playlist.triggerLiveClip(track, -1, midi.TLC_Fill)`)
  instead of retriggering it. V2 had no stop logic at all — every pad
  press just remapped the note and let FL's raw note-on handle it
  (restart-only behavior).
- **Clip staging while stopped** — pressing a pad while the transport is
  stopped now stages/queues that clip (`midi.TLC_Queue`) instead of
  sounding it like a keybed note, so it's armed and flashing, ready for
  the next Play press. Entirely new; V2 had no stopped-state handling —
  pads in V2 always just played the remapped note regardless of transport
  state.
- **One-shot clip auto-clear** — a track set to FL's "One shot" loop mode
  is automatically cleared (`triggerLiveClip(track, -1, TLC_Fill)`) once
  its clip finishes playing on its own, so it doesn't unexpectedly replay
  on the next Play press. No equivalent existed in V2.
- **Track-color pad rows** (`ATTEMPT_COLOR_GUESS`, default `False`) — each
  visible row can approximate its FL Studio track's actual color, using a
  new 128-entry palette table (`mapping.COLOR_MAP`) and a nearest-match
  search (`mapping.closest_color_index_for_fl_color`), tuned with a
  saturation-mismatch penalty after real-hardware testing. V2's pad colors
  were always the two hardcoded values below, with no relationship to
  track color at all.
- **Dedicated "playing" indicator color** — the actively playing clip in a
  row is always a fixed bright green (`mapping.PLAYING_INDICATOR_COLOR`),
  independent of that row's color, so it's unambiguous regardless of
  track hue. V2 used a flat hardcoded `color=6` for this with no
  track-color concept to disambiguate from in the first place.
- **Arrow-button mode indicator** — the 4 arrow track buttons
  (up/down/left/right) now light up while Performance Mode is active and
  turn off in Normal Mode. V2's function buttons were always either all-on
  or all-off/all-flashing as a group; there was no per-mode indicator.
- **Reactive track auto-selection** — FL's playlist track selection now
  follows the visible pad rows automatically whenever Performance Mode is
  entered (and re-syncs correctly every time it's re-entered). V2 never
  touched playlist track selection at all.

### Script lifecycle

- **`OnProjectLoad` handling** — loading a different project now resets
  all tracked performance-mode state and forces a full pad reset, so a
  previous project's live-clip grid state (e.g. a pad left flashing
  "scheduled") doesn't persist indefinitely into an unrelated project.
  V2 had no `OnProjectLoad` callback at all.
- **`OnDeInit` pad reset** — unloading the script now sets every pad to a
  visible `bright_1` "unloaded" indicator instead of leaving them in
  whatever state they were last in. V2's `OnDeInit` called
  `animate_pads_off()`, a leftover startup-animation reverse-sweep, not a
  deliberate reset state.

### Standard Mode / buttons

- **Stop/All Clips button** — now has a real stub handler
  (`DeviceHandler._handle_stop`) that logs and marks the event handled. In
  V2, `"stop"` was mapped in the button dict but never wired to any
  dispatch logic anywhere — pressing it did nothing and wasn't even
  acknowledged.
- **SUSTAIN button disambiguation** — the dedicated SUSTAIN button (CC 64)
  numerically collides with the `track_1` note button (both use data byte
  `0x40`). V2's code has a comment flagging this exact collision
  (`"!! 0x40 = "sustain" pressed/unpressed is value == 176"`) but never
  addressed it. V2.1 adds a real status-byte check
  (`event.status & 0xF0 == midi.MIDI_CONTROLCHANGE`) before any note-keyed
  dispatch runs, confirmed correct against real hardware MIDI logs.

### Developer experience

- **Leveled debug logging** — `DebugLevel.OFF`/`STATUS`/`VERBOSE` with
  `log_status()`/`log_verbose()` helpers, the latter auto-prefixing the
  calling method's name. V2 had one flat `DEBUG` boolean and bare
  `print()` calls scattered everywhere.
- **State-diffed LED writes** — `ControlStateStore` tracks every control's
  last-sent LED state so redundant MIDI (e.g. redrawing the live-clip grid
  every playlist update) gets skipped when nothing changed. V2 had no
  state tracking at all — every redraw unconditionally resent to every
  pad.
- **`mapping.py` extraction** — all note/CC/color lookup tables moved out
  of the main script into a standalone data module, with a `BiMap` helper
  class replacing V2's repeated manual
  `revX = {value: key for key, value in x.items()}` pattern (six separate
  times in V2, one reusable class in V2.1).
- **Header metadata** — `# supportedDevices=`/`# supportedHardwareIds=`
  (commented, pending real captured values) and a `# receiveFrom=`
  explanatory note, for FL's auto-linking mechanism. V2 only had
  `# name=`/`# url=`.
- **`__version__` constant** (currently `2.0.0`), logged on init.
- **DEV_NOTES.md, LIGHTING_FUNCTION_PLAN.md,
  README.md** — a full documentation set covering design decisions, bug
  histories, and hardware test tracking. V2 had no separate documentation
  of any kind.
- **Consolidated `PadLighting` API** — `set_pad`, `set_func_buttons`,
  `set_knob_ctrl_dim`, `set_arrow_buttons` replaced roughly a dozen
  narrower V2 methods (`pad_color`, `pad_pressed`, `pad_unpressed`,
  `pad_led_on`, `pad_led_off`, `all_funcs_on/off/flash/stop_flash`, etc.),
  several of which were dead code in V2 (never called from anywhere).

---

## Bug Fixes

### Present in V2 from the start, found and fixed during this project

- **Row 5 never started clips in Performance Mode.** V2's `eventHandler`
  remaps a pad's note and then keeps falling through the same
  `if`-chain — including the knob-CC check (`0x30`-`0x37`) — with no early
  return. Row 5's remapped notes land in exactly that range, so V2 would
  have hit the exact same bug (a remapped pad note silently eaten by the
  knob-handling branch) had it been noticed; it wasn't. Fixed by returning
  immediately after a performance-mode pad remap, before any dispatch
  logic runs.
- **Knob turns could send an invalid MIDI value (128).** V2's up-branch
  clamp (`if self.knobs[knob] > 128: self.knobs[knob] = 128`) allows the
  accumulator to reach 128 — not a valid 7-bit MIDI data byte. Present
  verbatim in V2; clamped to 127.
- **Knob "turn up" minimum delta was +2, not +1.** V2's up-branch formula
  (`vel = value`) starts at `vel=1` for the smallest possible turn, so the
  minimum reachable delta is `vel+1=2` — asymmetric with the down branch,
  which correctly reaches `delta=1`. Present verbatim in V2; fixed to
  `vel = value - 1` so both directions match.
- **`OnUpdateLiveMode` repainted pads regardless of Performance Mode.**
  V2's version has no mode check at all — it walks the live-clip grid and
  writes pad colors unconditionally every time FL calls it, including
  while in Normal Mode. Fixed by gating the whole redraw on a freshly-read
  `playlist.getPerformanceModeState()`.
- **Periodic pad LED flicker** — root-caused to specific RGB palette
  indices (`1`, `2`) which the device itself animates/flickers regardless
  of LED mode or channel, confirmed on real hardware. V2's
  `self.initialColor = 0x02` used exactly one of the two bad indices for
  every idle pad — this bug has been present since V2, just never
  diagnosed. Fixed by moving every pad color in the script to index `3`
  (white) or higher.
- **`dIdMap` string-into-list-slice bug.** V2's device-ID debug map does
  `self.dIdMap[5:7] = "xxx"` — assigning a 3-character string to a
  2-element slice, which Python happily iterates character-by-character,
  silently growing the list and shifting every later label out of
  alignment with the real byte positions. Present verbatim in V2; fixed to
  use properly-sized list literals.

### Introduced during the V2.1 rewrite, found and fixed since

- **SHIFT engage/release visuals were inverted.** The print statement and
  knob-ctrl LED dim/bright call in `_handle_shift`'s two branches were
  swapped relative to what they were actually doing — engaging SHIFT
  printed "inactive" and brightened; releasing it printed "active" and
  dimmed. State tracking itself was always correct; only the visual
  feedback was backwards. (Not a V2 bug — V2's SHIFT handling used flash/
  stop-flash on the function buttons, a different visual scheme entirely.)
- **`OnInit()` unconditionally selected tracks 1-5 on every script load,**
  regardless of mode — clobbering the user's Normal Mode track selection
  at every load, and never re-selecting on a later real entry into
  Performance Mode. (New behavior introduced when track auto-selection was
  first added — V2 never selected tracks at all, so it couldn't have had
  this bug.) Fixed by making selection reactive to the actual off→on
  performance-mode transition instead of a one-shot action at load.
- **Track-color matching had red and blue swapped.** The first
  implementation followed `playlist.getTrackColor()`'s own docstring
  (`0x--BBGGRR`), which turned out to contradict FL's canonical
  `utils.ColorToRGB`/`RGBToColor`/`RGBToHSVColor` functions (all three
  agree on `0xRRGGBB`). A red track was being read as blue. Fixed to match
  the canonical byte order.
- **A "redmean" perceptual color-distance formula regressed an
  already-confirmed-good match** during tuning of the track-color feature.
  Caught by checking the new formula against previously-verified test
  cases before keeping it, and reverted in favor of a smaller, calibrated
  saturation-mismatch penalty on top of plain distance instead.
- **Stop/All Clips and SUSTAIN were silently unhandled.** Not strictly
  "bugs" since V2 never attempted to handle them either, but worth noting
  as gaps closed alongside the disambiguation/stub work above.

---

## Notes on scope

This list favors *behavioral* changes — things a user would notice on
real hardware, or a real MIDI-safety issue (like the invalid-128 knob
value). It doesn't attempt to enumerate every docstring, comment, or
internal refactor between V2 and the current script; see `DEV_NOTES.md`
for that level of detail.
