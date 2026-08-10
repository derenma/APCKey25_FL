# APC Key 25 mk2 — LED Color Scheme

Reference notes on how pad/button LED color and brightness are controlled, and how the
128-entry `velocity_to_hex_rgb` palette in [`akai_apc_key_25.yaml`](../akai_apc_key_25.yaml) is
structured. Source: `docs/APC Key 25 mk2 - Communication Protocol - v1.1.pdf`.

## Two ways to set pad color

### 1. Note On/Off with a fixed 128-color velocity palette

```
9X PP VV
```
- `9X` — Note On, channel `X` (0x0-0xF) selects LED **behavior** (see below)
- `PP` — pad note number (`0x00`-`0x27` for the 5x8 RGB matrix)
- `VV` — velocity `0`-`127`, indexes into a **fixed, device-firmware color palette**
  (`rgb_palette.velocity_to_hex_rgb` in the yaml). This palette cannot be changed — it's ROM,
  not RGB math. Velocity is a lookup index, not a color component.

> **Hardware quirk, confirmed, undocumented in the protocol PDF:** palette indices `1`
> (`#1E1E1E`) and `2` (`#7F7F7F`) cause the pad to flicker/flash periodically (roughly every
> 5-6 seconds) on real hardware, regardless of which brightness/pulse channel (`9X`) they're
> sent with — this is a static, one-time Note On with no polling or resend involved, so it's the
> device itself animating those specific indices, not a script bug. Index `3` (`#FFFFFF`) is
> confirmed safe. Other indices haven't been systematically tested — avoid `1`/`2` for any pad
> color choice until more of the palette is verified. See DEV_NOTES.md "ROOT CAUSE CONFIRMED:
> low RGB-palette color indices" for the investigation.

MIDI channel (the `X` in `9X`) doubles as the **behavior** selector for RGB pads:

| Channel | Status byte | Behavior |
|---|---|---|
| 0 | `90` | Solid, 10% brightness |
| 1 | `91` | Solid, 25% brightness |
| 2 | `92` | Solid, 50% brightness |
| 3 | `93` | Solid, 65% brightness |
| 4 | `94` | Solid, 75% brightness |
| 5 | `95` | Solid, 90% brightness |
| 6 | `96` | Solid, 100% brightness |
| 7 | `97` | Pulsing 1/16 |
| 8 | `98` | Pulsing 1/8 |
| 9 | `99` | Pulsing 1/4 |
| 10 | `9A` | Pulsing 1/2 |
| 11 | `9B` | Blinking 1/24 |
| 12 | `9C` | Blinking 1/16 |
| 13 | `9D` | Blinking 1/8 |
| 14 | `9E` | Blinking 1/4 |
| 15 | `9F` | Blinking 1/2 |

Single-color (non-RGB) buttons (track/scene/stop/play/record) always use status `0x90` and
velocity only toggles on/off/blink (`0x00` off, `0x02` blink, anything else on) — brightness/
pulse-rate channel selection does not apply to them.

### 2. SysEx RGB Color Lighting — arbitrary 24-bit color

For a truly arbitrary hex color (not limited to the 128-entry palette), use the SysEx message
documented as `sysex.rgb_color_lighting` in the yaml (message id `0x24`):

```
F0 47 7F 4E 24 <len_msb> <len_lsb> <start_pad> <end_pad> <R_msb> <R_lsb> <G_msb> <G_lsb> <B_msb> <B_lsb> [...more 8-byte records...] F7
```

- `start_pad`/`end_pad` — inclusive pad range (`0x00`-`0x27` physically; one record can target
  a contiguous block of pads, e.g. `0x00`..`0x27` to paint the whole grid one color)
- Each 8-bit RGB component (`0-255`) is split across two 7-bit MIDI bytes:
  `msb = (value >> 7) & 0x01`, `lsb = value & 0x7F`
- Multiple 8-byte records can be chained in one message for different ranges/colors
- `len_msb`/`len_lsb` = total data byte count = `8 * number_of_records`, split the same way as
  above but over the whole 14-bit length field

This message bypasses the velocity palette entirely — it drives true RGB brightness per
channel, so any hex color (e.g. `#3AF0C7`) can be rendered directly, at the cost of not being
able to select blink/pulse behavior (that's still controlled separately via Note On channel,
see above).

> **Gotcha 1:** the device ignores this (and any other device-specific SysEx) until it has
> received the **Introduction message** (`0x60`) at least once per connection — see
> `sysex.introduction` in the yaml (`required_before_device_specific_messages: true`). Without
> it, RGB Color Lighting messages are silently dropped: they transmit fine but nothing changes
> on the pads. `standalone_apckey25.py`'s `send_rgb_color_lighting()` sends the Introduction
> message automatically before every RGB Color Lighting call.
>
> **Gotcha 2 (unconfirmed):** the protocol doc splits the device into two MIDI ports — Port 0
> ("keys", used for keybed notes/sustain) and Port 1 ("control surface", used for
> knobs/buttons/pad LED note messages) — but it never states which port accepts *generic*
> device-specific SysEx (Device Enquiry, Introduction, RGB Color Lighting). If sending
> Introduction + RGB Color Lighting on the same port that already handles pad LED note
> messages has no visible effect, the SysEx may need the *other* APC port. Rather than guess,
> `set_all_pads_custom_rgb_broadcast()` sends both messages to every APC output port in turn
> and listens briefly afterward for any inbound response, so you can see which port (if any)
> the device actually reacts to.

## `velocity_to_hex_rgb` structure

The palette is **not** a formula — it's a hardcoded lookup table in firmware — but it has clear
internal structure in two segments.

### Velocities 0-3: base colors

| Velocity | Hex | Meaning |
|---|---|---|
| 0 | `#000000` | off |
| 1 | `#1E1E1E` | dark gray |
| 2 | `#7F7F7F` | gray |
| 3 | `#FFFFFF` | white |

### Velocities 4-59: a 14-hue color wheel x 4 brightness tiers

Repeats in blocks of 4 (`4n .. 4n+3`, `n = 0..13`, one block per hue):

| Offset | Meaning | Example (n=0, red) |
|---|---|---|
| +0 | tinted/pastel, full brightness | `#FF4C4C` |
| +1 | fully saturated | `#FF0000` |
| +2 | dim (~35%) | `#590000` |
| +3 | very dim (~10%) | `#190000` |

So velocity `4n+1` walks a clean hue wheel as `n` goes `0..13`:
red -> orange -> yellow -> yellow-green -> green -> spring-green -> turquoise -> cyan-blue ->
blue -> indigo -> purple -> magenta -> pink -> rose, wrapping back toward red. That's 14 hues x
4 brightness levels = velocities `4..59`. Hue spacing is hand-picked, not evenly-spaced HSV
degrees — good enough for a visually smooth cycle, not mathematically exact.

### Velocities 60-127: fixed miscellaneous swatches

No hue/brightness pattern — this range mirrors Ableton Live's default clip-color swatches (for
matching pad LEDs to clip colors in the DAW). Treat as an arbitrary lookup, not a generated
ramp.

## Gradient-cycling recipe (velocity-palette approach)

- Hue index: `velocity = 4*n + offset`, `n = 0..13` selects hue, `offset in {0,1,2,3}` selects
  brightness tier
- Rainbow cycle at full saturation: step through velocities
  `5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49, 53, 57`, then wrap to `5`
- Breathing effect on one hue: hold `n` fixed, animate `offset` `0 -> 1 -> 2 -> 3`
- Combine both for a rotating, breathing rainbow

For a mathematically exact/smooth gradient (not just "visually smooth"), use the SysEx RGB
Color Lighting message instead and interpolate RGB or HSV directly — it isn't constrained to
the 128-entry palette.
