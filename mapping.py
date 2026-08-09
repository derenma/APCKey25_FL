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
# reference. See dev/docs/APC Key 25 mk2 - Communication Protocol - v1.1.pdf.
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

# Same 8 physical buttons, meaning while SHIFT is held.
# !! 0x40 = "up" pressed/unpressed is value == 144/128
# !! 0x40 = "sustain" pressed/unpressed is value == 176
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
# dev/docs/LED_COLOR_SCHEME.md for the full velocity-palette writeup.
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
