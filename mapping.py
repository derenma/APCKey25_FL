# mapping.py
# All MIDI note/CC/SysEx mapping data for the APC Key 25 mk2, kept separate from
# device_APCKey25mk2V3.py so the main script stays focused on behavior, not tables.
#
# Plain data only: no FL Studio API imports, no side effects. Safe to import and
# inspect on its own.


class BiMap:
	"""Bidirectional lookup over a fixed {id: name} table.

	mapping[id] / mapping.by_id[id] -> name
	mapping.id_for(name) -> id
	"""

	def __init__(self, id_to_name):
		self.by_id = dict(id_to_name)
		self.by_name = {name: id_ for id_, name in id_to_name.items()}

	def __getitem__(self, id_):
		return self.by_id[id_]

	def __contains__(self, id_):
		return id_ in self.by_id

	def id_for(self, name):
		return self.by_name[name]


# --- SysEx / device identity constants -------------------------------------
# Not currently used (no SysEx handshake is implemented), kept as protocol
# reference. See docs/apc_key_protocol/APC Key 25 mk2 - Communication Protocol - v1.1.pdf.
MANUFACTURER_ID = 0x47
DEVICE_ID_BROADCAST = 0x7F
PRODUCT_ID = 0x4E
MSG_ID_SET_RGB_PAD_LED_STATE = 0x65

# --- Pad / color / button ID ranges -----------------------------------------
PAD_ID_START = 0x00
PAD_ID_END = 0x28

COLOR_START = 0x00
COLOR_END = 0x7F

TRACK_ID_START = 0x40
TRACK_ID_END = 0x47

MIDI_KEY_START = 0x00
MIDI_KEY_END = 0x78

# --- Song/function buttons ---------------------------------------------------
SOUND_BUTTONS = BiMap({
	0x51: "stop",
	0x5B: "play",
	0x5D: "record",
	0x62: "shift",
})

# Track-select buttons (the 8 buttons below the pad grid), default meaning.
TRACK_BUTTONS = BiMap({
	0x40: "track_1",
	0x41: "track_2",
	0x42: "track_3",
	0x43: "track_4",
	0x44: "track_5",
	0x45: "track_6",
	0x46: "track_7",
	0x47: "track_8",
})

# Dedicated physical SUSTAIN button (the device has no separate TS pedal
# jack), sent as standard MIDI Sustain (Control Change 64), i.e. status byte
# 0xB0-0xBF. Numerically collides with TRACK_BUTTONS' 0x40 ("track_1"),
# which is a Note On/Off (status 0x90-0x9F) — the two can only be told apart
# by status byte, not data1 alone. See DeviceHandler.eventHandler's sustain
# check in device_APCKey25mk2.py.
SUSTAIN_CC = 0x40

# Same 8 physical buttons, meaning while SHIFT is held.
TRACK_BUTTONS_SHIFT = BiMap({
	0x40: "up",
	0x41: "down",
	0x42: "left",
	0x43: "right",
	0x44: "knob_vol",
	0x45: "knob_pan",
	0x46: "knob_send",
	0x47: "knob_device",
})

KNOB_CTRL = BiMap({
	0x44: "knob_vol",
	0x45: "knob_pan",
	0x46: "knob_send",
	0x47: "knob_device",
})

# The other 4 of the 8 track buttons — their SHIFT-held (arrow) meaning.
# Lit while Performance Mode is active; see PadLighting.set_arrow_buttons.
ARROW_BUTTONS = BiMap({
	0x40: "up",
	0x41: "down",
	0x42: "left",
	0x43: "right",
})

# Scene-launch buttons, default meaning.
SCENE_BUTTONS = BiMap({
	0x52: "scene_1",
	0x53: "scene_2",
	0x54: "scene_3",
	0x55: "scene_4",
	0x56: "scene_5",
})

# Same 5 physical buttons, meaning while SHIFT is held.
SCENE_BUTTONS_SHIFT = BiMap({
	0x52: "clip_stop",
	0x53: "solo",
	0x54: "mute",
	0x55: "rec_arm",
	0x56: "select",
})

# --- Pad LED behavior (status byte -> behavior name) -------------------------
# Channel nibble of the Note On status byte selects LED behavior; see
# docs/apc_key_protocol/LED_COLOR_SCHEME.md for the full velocity-palette writeup.
PAD_LED_FUNCTION = BiMap({
	0x90: "bright_0",
	0x91: "bright_1",
	0x92: "bright_2",
	0x93: "bright_3",
	0x94: "bright_4",
	0x95: "bright_5",
	0x96: "bright_6",
	0x97: "pulse_1_16",
	0x98: "pulse_1_8",
	0x99: "pulse_1_4",
	0x9A: "pulse_1_2",
	0x9B: "blink_1_24",
	0x9C: "blink_1_16",
	0x9D: "blink_1_8",
	0x9E: "blink_1_4",
	0x9F: "blink_1_2",
})

# --- Startup animation --------------------------------------------------------
# Order in which pads light up during the power-on animation. Change freely.
START_PATTERN = [
	[0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07],
	[0x0F, 0x17, 0x1F, 0x27],
	[0x26, 0x25, 0x24, 0x23, 0x22, 0x21, 0x20],
	[0x18, 0x10, 0x08],
	[0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E],
	[0x16, 0x1E],
	[0x1D, 0x1C, 0x1B, 0x1A, 0x19],
	[0x11, 0x12, 0x13, 0x14, 0x15],
]

# --- Performance-mode pad remap (INPUT) --------------------------------------
# While the device is in FL's performance/live mode, incoming pad note IDs
# (physical grid numbering, 0-39) are remapped before
# DeviceHandler.eventHandler lets the note pass through to FL, which then
# triggers live-clip playback itself based on the note value (the script
# never calls an explicit "start" API — see README's Performance mode
# section for why, and for the triggerLiveClip-based start attempt that
# didn't work).
#
# performance_note_for(track, col) computes that note: track N, column C
# (both 1-based/0-based matching playlist.getLiveBlockStatus's own
# indexing) -> note 12*(N-1)+C. This was reverse-engineered from the
# original hardcoded table (row R, unscrolled, always had track==R):
# row1/track1 col0 -> note 0, row2/track2 col0 -> note 12, ... row5/track5
# col0 -> note 48 — i.e. exactly 12 semitones (one octave) per track,
# confirmed against real hardware for tracks 1-5. Not verified beyond
# track 5; if FL's own note-to-track association isn't actually a
# universal formula (e.g. it's per-project configuration that only
# happened to match this pattern for tracks 1-5), this will need revisiting.
def performance_note_for(track, col):
	return 12 * (track - 1) + col

# --- Live-clip grid pad positions (OUTPUT) -----------------------------------
# Maps FL's live-clip grid coordinates [row][block] to the physical pad note ID,
# so PerformanceMode can light the correct pad for each clip slot.
# Index 0 is an unused placeholder to keep row indices aligned with FL's
# 1-based playlist.getLiveBlockStatus(row, ...) row numbering.
LIVE_GRID_PAD_POSITIONS = [
	[0],
	[32, 33, 34, 35, 36, 37, 38, 39],
	[24, 25, 26, 27, 28, 29, 30, 31],
	[16, 17, 18, 19, 20, 21, 22, 23],
	[8, 9, 10, 11, 12, 13, 14, 15],
	[0, 1, 2, 3, 4, 5, 6, 7],
]

# Inverse of the above: physical pad note ID -> (row, col) in the live-clip
# grid. Built from rows 1-5 only — row 0 is the unused placeholder above, and
# including it would collide with the real pad 0 in row 5.
PAD_TO_GRID_POSITION = {
	pad_id: (row, col)
	for row in range(1, len(LIVE_GRID_PAD_POSITIONS))
	for col, pad_id in enumerate(LIVE_GRID_PAD_POSITIONS[row])
}

# --- RGB velocity palette (Note On velocity -> pad color) --------------------
# Source: docs/apc_key_protocol/akai_apc_key_25.yaml `rgb_palette.velocity_to_hex_rgb`. This is the
# device's fixed, firmware-ROM 128-color palette (see docs/apc_key_protocol/LED_COLOR_SCHEME.md)
# — velocity is a lookup index into this table, not a color component. Used
# to find the closest palette match for an arbitrary FL Studio color (e.g. a
# track color) since the device can't render arbitrary RGB via this message
# type (only via the SysEx RGB Color Lighting message, which doesn't work on
# this hardware — see docs/DEV_NOTES.md's script header entry).
COLOR_MAP = {
	0: (0x00, 0x00, 0x00), 1: (0x1E, 0x1E, 0x1E), 2: (0x7F, 0x7F, 0x7F), 3: (0xFF, 0xFF, 0xFF),
	4: (0xFF, 0x4C, 0x4C), 5: (0xFF, 0x00, 0x00), 6: (0x59, 0x00, 0x00), 7: (0x19, 0x00, 0x00),
	8: (0xFF, 0xBD, 0x6C), 9: (0xFF, 0x54, 0x00), 10: (0x59, 0x1D, 0x00), 11: (0x27, 0x1B, 0x00),
	12: (0xFF, 0xFF, 0x4C), 13: (0xFF, 0xFF, 0x00), 14: (0x59, 0x59, 0x00), 15: (0x19, 0x19, 0x00),
	16: (0x88, 0xFF, 0x4C), 17: (0x54, 0xFF, 0x00), 18: (0x1D, 0x59, 0x00), 19: (0x14, 0x2B, 0x00),
	20: (0x4C, 0xFF, 0x4C), 21: (0x00, 0xFF, 0x00), 22: (0x00, 0x59, 0x00), 23: (0x00, 0x19, 0x00),
	24: (0x4C, 0xFF, 0x5E), 25: (0x00, 0xFF, 0x19), 26: (0x00, 0x59, 0x0D), 27: (0x00, 0x19, 0x02),
	28: (0x4C, 0xFF, 0x88), 29: (0x00, 0xFF, 0x55), 30: (0x00, 0x59, 0x1D), 31: (0x00, 0x1F, 0x12),
	32: (0x4C, 0xFF, 0xB7), 33: (0x00, 0xFF, 0x99), 34: (0x00, 0x59, 0x35), 35: (0x00, 0x19, 0x12),
	36: (0x4C, 0xC3, 0xFF), 37: (0x00, 0xA9, 0xFF), 38: (0x00, 0x41, 0x52), 39: (0x00, 0x10, 0x19),
	40: (0x4C, 0x88, 0xFF), 41: (0x00, 0x55, 0xFF), 42: (0x00, 0x1D, 0x59), 43: (0x00, 0x08, 0x19),
	44: (0x4C, 0x4C, 0xFF), 45: (0x00, 0x00, 0xFF), 46: (0x00, 0x00, 0x59), 47: (0x00, 0x00, 0x19),
	48: (0x87, 0x4C, 0xFF), 49: (0x54, 0x00, 0xFF), 50: (0x19, 0x00, 0x64), 51: (0x0F, 0x00, 0x30),
	52: (0xFF, 0x4C, 0xFF), 53: (0xFF, 0x00, 0xFF), 54: (0x59, 0x00, 0x59), 55: (0x19, 0x00, 0x19),
	56: (0xFF, 0x4C, 0x87), 57: (0xFF, 0x00, 0x54), 58: (0x59, 0x00, 0x1D), 59: (0x22, 0x00, 0x13),
	60: (0xFF, 0x15, 0x00), 61: (0x99, 0x35, 0x00), 62: (0x79, 0x51, 0x00), 63: (0x43, 0x64, 0x00),
	64: (0x03, 0x39, 0x00), 65: (0x00, 0x57, 0x35), 66: (0x00, 0x54, 0x7F), 67: (0x00, 0x00, 0xFF),
	68: (0x00, 0x45, 0x4F), 69: (0x25, 0x00, 0xCC), 70: (0x7F, 0x7F, 0x7F), 71: (0x20, 0x20, 0x20),
	72: (0xFF, 0x00, 0x00), 73: (0xBD, 0xFF, 0x2D), 74: (0xAF, 0xED, 0x06), 75: (0x64, 0xFF, 0x09),
	76: (0x10, 0x8B, 0x00), 77: (0x00, 0xFF, 0x87), 78: (0x00, 0xA9, 0xFF), 79: (0x00, 0x2A, 0xFF),
	80: (0x3F, 0x00, 0xFF), 81: (0x7A, 0x00, 0xFF), 82: (0xB2, 0x1A, 0x7D), 83: (0x40, 0x21, 0x00),
	84: (0xFF, 0x4A, 0x00), 85: (0x88, 0xE1, 0x06), 86: (0x72, 0xFF, 0x15), 87: (0x00, 0xFF, 0x00),
	88: (0x3B, 0xFF, 0x26), 89: (0x59, 0xFF, 0x71), 90: (0x38, 0xFF, 0xCC), 91: (0x5B, 0x8A, 0xFF),
	92: (0x31, 0x51, 0xC6), 93: (0x87, 0x7F, 0xE9), 94: (0xD3, 0x1D, 0xFF), 95: (0xFF, 0x00, 0x5D),
	96: (0xFF, 0x7F, 0x00), 97: (0xB9, 0xB0, 0x00), 98: (0x90, 0xFF, 0x00), 99: (0x83, 0x5D, 0x07),
	100: (0x39, 0x2B, 0x00), 101: (0x14, 0x4C, 0x10), 102: (0x0D, 0x50, 0x38), 103: (0x15, 0x15, 0x2A),
	104: (0x16, 0x20, 0x5A), 105: (0x69, 0x3C, 0x1C), 106: (0xA8, 0x00, 0x0A), 107: (0xDE, 0x51, 0x3D),
	108: (0xD8, 0x6A, 0x1C), 109: (0xFF, 0xE1, 0x26), 110: (0x9E, 0xE1, 0x2F), 111: (0x67, 0xB5, 0x0F),
	112: (0x1E, 0x1E, 0x30), 113: (0xDC, 0xFF, 0x6B), 114: (0x80, 0xFF, 0xBD), 115: (0x9A, 0x99, 0xFF),
	116: (0x8E, 0x66, 0xFF), 117: (0x40, 0x40, 0x40), 118: (0x75, 0x75, 0x75), 119: (0xE0, 0xFF, 0xFF),
	120: (0xA0, 0x00, 0x00), 121: (0x35, 0x00, 0x00), 122: (0x1A, 0xD0, 0x00), 123: (0x07, 0x42, 0x00),
	124: (0xB9, 0xB0, 0x00), 125: (0x3F, 0x31, 0x00), 126: (0xB3, 0x5F, 0x00), 127: (0x4B, 0x15, 0x02),
}

# Indices confirmed on real hardware to cause periodic flicker regardless of
# LED mode/channel — see docs/DEV_NOTES.md "ROOT CAUSE CONFIRMED: low RGB-palette
# color indices". Excluded from closest_color_index() so track-color
# matching can never land on a flickering index.
COLOR_MAP_UNSAFE_INDICES = frozenset({1, 2})

# Fixed indicator color for "this pad's clip is currently playing" — bright
# green (#00FF00), overriding the row's track color so the active clip in a
# row is unambiguous at a glance regardless of that track's hue. See
# PerformanceMode.OnUpdateLiveMode in device_APCKey25mk2.py.
PLAYING_INDICATOR_COLOR = 21


def _saturation(r, g, b):
	"""HSV saturation (0.0-1.0) for an (r, g, b) triple, 0-255 each."""
	mx = max(r, g, b)
	if mx == 0:
		return 0.0
	return (mx - min(r, g, b)) / mx


# Weight for the saturation-mismatch penalty in closest_color_index below.
# Calibrated against real-hardware test data (5 muted FL track colors, 2
# already confirmed as good matches) — see docs/DEV_NOTES.md "Third hardware
# test: saturation-aware matching" for the full calibration. Stable across
# 0.025-0.1 for that data (same results throughout); 0.05 picked as a safe
# middle value, not a fragile threshold.
_SATURATION_PENALTY_WEIGHT = 0.05


def closest_color_index(r, g, b):
	"""Find the `COLOR_MAP` index whose color is the closest visual match to
	`(r, g, b)`: Euclidean distance in RGB space, plus a penalty for
	saturation mismatch between the input and each candidate.

	The saturation penalty exists because plain RGB distance alone
	frequently picked one of this palette's few grey entries over a
	clearly more appropriate hued candidate, by a small margin (~12-14% on
	real test data) — this palette's greys sit numerically close to many
	moderately-saturated dark/muted colors even when the input has an
	obvious hue, because the palette itself is mostly either fully
	saturated neon colors or near-black/grey, with few in-between options.
	Penalizing saturation mismatch breaks those near-ties in favor of
	preserving the input's actual saturation, without overhauling the
	whole metric (a full perceptual "redmean" swap was tried first and
	reverted — see the note below — because it regressed an
	already-confirmed-good case; this fix is deliberately smaller and
	verified not to touch any previously-confirmed-good match).

	A "redmean" perceptually-weighted distance variant was tried and
	reverted — it regressed a case already confirmed correct on real
	hardware (an olive `#544F2B` track color matched index 105, a
	reasonable brownish-olive, under plain distance; redmean matched it to
	117, plain grey, instead). See docs/DEV_NOTES.md `OnUpdateLiveMode`
	track-color rows for that comparison data.

	Args:
		r: Red component, 0-255.
		g: Green component, 0-255.
		b: Blue component, 0-255.

	Returns:
		int: The closest-matching palette index. Never one of
		`COLOR_MAP_UNSAFE_INDICES`.
	"""
	input_saturation = _saturation(r, g, b)
	best_index = None
	best_distance = None
	for index, (pr, pg, pb) in COLOR_MAP.items():
		if index in COLOR_MAP_UNSAFE_INDICES:
			continue
		rgb_distance = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
		saturation_penalty = _SATURATION_PENALTY_WEIGHT * 65025 * (input_saturation - _saturation(pr, pg, pb)) ** 2
		distance = rgb_distance + saturation_penalty
		if best_distance is None or distance < best_distance:
			best_distance = distance
			best_index = index
	return best_index


def closest_color_index_for_fl_color(fl_color):
	"""Convert an FL Studio color int (e.g. from `playlist.getTrackColor()`
	or `playlist.getLiveBlockColor()`) to the closest `COLOR_MAP` index.

	Args:
		fl_color: FL color, `0xRRGGBB` format — red is the high byte, blue
			is the low byte. This matches FL's own canonical
			`utils.ColorToRGB`/`utils.RGBToColor`/`utils.RGBToHSVColor`
			(all three agree: `R = (Color >> 16) & 0xFF`, ..., `B = Color
			& 0xFF`). NOTE: `playlist.getTrackColor()`'s own docstring
			claims `0x--BBGGRR` (red as the *low* byte) — that appears to
			be a documentation error in the community-maintained API
			stubs, contradicted by three separate canonical utility
			functions; confirmed wrong empirically too (see docs/DEV_NOTES.md
			`OnUpdateLiveMode` track-color rows).

	Returns:
		int: The closest-matching palette index.
	"""
	r = (fl_color >> 16) & 0xFF
	g = (fl_color >> 8) & 0xFF
	b = fl_color & 0xFF
	return closest_color_index(r, g, b)
