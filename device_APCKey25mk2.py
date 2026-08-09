# name=APCKey25mk2V3
# url=https://forum.image-line.com/viewtopic.php?t=323673
# Author: Matt Deren
# Inspired by original script by Martijn Tromp: https://forum.image-line.com/viewtopic.php?f=1994&t=225886
# Notes:
# - This script as very little in common with the original and has morphed into its own beast.
# - Tested with FL Studio 2026 v26.1.3 [build 5570]
# - Built in VS Code. Hence, there are playright ignore messages to clean up linting warnings
# - sysex for creating custom RGB pad colors simply doesn't work and my particular device does not respond to
# 	the the required "Introduction Message". I suspect there is a specific version number that needs to be sent
#	that is currently not documented. (Bruteforcing this may work, but also could be a massive waste of time)
#	Snippets of my debug code, if anyone wants to give this a go:
#	# Sysex Debug Bullshit ##############################################
#	# TEST: RGB Color Lighting SysEx (pads 0x00-0x27, R=255 G=255 B=0)
#	#self.buttons.all_pads_off(speed=0.00)
#	#time.sleep(1)
#	#self.buttons.all_pads_on(speed=0.00)
#	#time.sleep(1)
#	# TEST: MMC Device Enquiry (F0 7E 00 06 01 F7)
#	#device.midiOutSysex(bytes([0xF0, 0x7E, 0x00, 0x06, 0x01, 0xF7]))
#	#time.sleep(1)
#	#device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x60, 0x00, 0x04, 0x00, 0x01, 0x00, 0x00, 0xF7])) # Introduction Message
#	#time.sleep(1)
#	#print('sending color change')
#	#device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x24, 0x00, 0x08, 0x00, 0x00, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0x7E, 0xF7]))
#	#device.midiOutSysex(bytes([0xF0, 0x47, 0x7F, 0x4E, 0x24, 0x00, 0x08, 0x00, 0x00, 0x01, 0x7F, 0x00, 0x00, 0x01, 0x7F, 0xF7]))
#	#####################################################################
# Quick Start:
#	...
#########################################################################
import sys
import time
import transport  # pyright: ignore[reportMissingImports]
import device  # pyright: ignore[reportMissingImports]
import playlist  # pyright: ignore[reportMissingImports]
import patterns  # pyright: ignore[reportMissingImports]
import midi  # pyright: ignore[reportMissingImports]

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import mapping

# --- Debug logging -----------------------------------------------------------
# Two levels, checked cheaply so callers don't need their own "if debug" guards
# for the common case:
#   STATUS  - general script status: init sequence, mode/transport changes,
#             stub buttons firing. Readable at a glance, safe to leave on.
#   VERBOSE - everything else: per-event tracing, raw device ID dumps, live-clip
#             grid internals. Noisy — turn on only when actively debugging.
class DebugLevel(Enum):
	OFF = 0
	STATUS = 1
	VERBOSE = 2

DEBUG_LEVEL = DebugLevel.STATUS

def log_status(msg):
	if DEBUG_LEVEL.value >= DebugLevel.STATUS.value:
		print(f"[APCKey25] {msg}")

def _caller_label():
	"""'ClassName.method' for the caller of the caller of this function (i.e.
	whoever called log_verbose), or just 'function' at module scope."""
	frame = sys._getframe(2)
	func_name = frame.f_code.co_name
	self_obj = frame.f_locals.get("self")
	if self_obj is not None:
		return f"{type(self_obj).__name__}.{func_name}"
	return func_name

def log_verbose(msg):
	if DEBUG_LEVEL.value >= DebugLevel.VERBOSE.value:
		print(f"[APCKey25:verbose] {_caller_label()}: {msg}")

class InitClass():
	def __init__(self):
		log_status("Init.")
		time.sleep(1)


class ControlKind(Enum):
	KEY = "key"
	KNOB = "knob"
	PAD = "pad"
	FUNCTION_BUTTON = "function_button"


@dataclass
class ControlState:
	"""Tracked state for one physical control (key, knob, pad, or function button)."""
	id: int
	kind: ControlKind
	active: bool = False   # pressed/held (keys, pads, function buttons); unused for knobs
	value: int = 0          # knob value (0-127); unused for everything else
	led_mode: Optional[int] = None  # pad LED status byte, i.e. mapping.PAD_LED_FUNCTION id (pads/function buttons only)
	color: int = 0           # velocity-palette index 0-127 (pads/function buttons only)


class ControlStateStore:
	"""Single source of truth for active/pressed + LED state of every control.

	Keyed by (kind, id) rather than id alone: pad note IDs (0x00-0x27) can
	numerically collide with low keybed key note numbers (the device has two
	physical MIDI ports; FL unifies them before this script sees events, so
	there's no reliable way to tell them apart from the note number alone —
	see the classification note in DeviceHandler._classify_control). Keying
	by kind keeps their tracked state from clobbering each other even though
	that classification itself is a best-effort guess, unverified on
	hardware for genuine low keybed notes.
	"""

	def __init__(self):
		self._controls = {}

	def register(self, kind, control_id, **kwargs):
		self._controls[(kind, control_id)] = ControlState(id=control_id, kind=kind, **kwargs)

	def get(self, kind, control_id):
		return self._controls.get((kind, control_id))

	def all(self, kind=None):
		if kind is None:
			return list(self._controls.values())
		return [c for c in self._controls.values() if c.kind == kind]

	def set_active(self, kind, control_id, active):
		control = self._controls.get((kind, control_id))
		if control is not None:
			control.active = active

	def set_value(self, kind, control_id, value):
		control = self._controls.get((kind, control_id))
		if control is not None:
			control.value = value

	def set_led(self, kind, control_id, led_mode, color):
		"""Record LED state for a pad/function button. Returns True if this
		is a change from what's already tracked — callers use this to skip
		sending redundant MIDI. Unregistered controls always report changed
		(nothing to compare against), so the message is sent either way."""
		control = self._controls.get((kind, control_id))
		if control is None:
			return True
		changed = control.led_mode != led_mode or control.color != color
		control.led_mode = led_mode
		control.color = color
		return changed


def build_control_state_store():
	store = ControlStateStore()

	for note_id in range(mapping.PAD_ID_START, mapping.PAD_ID_END):
		store.register(ControlKind.PAD, note_id)

	for note_id in mapping.SOUND_BUTTONS.by_id:
		store.register(ControlKind.FUNCTION_BUTTON, note_id)
	for note_id in mapping.TRACK_BUTTONS.by_id:
		store.register(ControlKind.FUNCTION_BUTTON, note_id)
	for note_id in mapping.SCENE_BUTTONS.by_id:
		store.register(ControlKind.FUNCTION_BUTTON, note_id)

	for cc in range(0x30, 0x38):
		store.register(ControlKind.KNOB, cc)

	# Keybed keys. See the ControlStateStore docstring re: numeric overlap
	# with pad note IDs in the 0x00-0x27 range.
	for note_id in range(mapping.MIDI_KEY_START, mapping.MIDI_KEY_END):
		store.register(ControlKind.KEY, note_id)

	return store

# Mirrors FL's own transport/playlist state (not physical controller state —
# see ControlStateStore for that). refresh() is called once per incoming
# event by OnMidiMsg/OnMidiIn; getters just return the cached values.
class SessionState():
	def __init__(self):
		self._isPlaying = 0
		self._isRecording = 0
		self._isPerformance = 0
		self.refresh()
		log_verbose(f"isPlaying={self._isPlaying} isRecording={self._isRecording} isPerformance={self._isPerformance}")

	def refresh(self):
		"""Explicit resync with FL transport/playlist state. Call once per incoming event, not from inside getters."""
		self._isPlaying = transport.isPlaying()
		self._isRecording = transport.isRecording()
		self._isPerformance = playlist.getPerformanceModeState()

	def isPlaying(self, set=None):
		if set is not None:
			self._isPlaying = set
		return(self._isPlaying)

	def isRecording(self, set=None):
		if set is not None:
			self._isRecording = set
		return(self._isRecording)

	def isPerformance(self, set=None):
		if set is not None:
			self._isPerformance = set
		return(self._isPerformance)

# This can be used to get all of your controller information
class DeviceHandler():
	def __init__(self, midiHandler, controls, buttons, state, controlStates, live):
		self.midiHandler = midiHandler
		self.buttons = buttons
		self.state = state
		self.controls = controls
		self.controlStates = controlStates
		self.live = live

		self.knobs = [0,0,0,0,0,0,0,0]

		# note/CC id -> bound handler. eventHandler is just this lookup;
		# each button/knob's actual logic lives in its own _handle_* method.
		self._dispatch = {}
		for note_id in mapping.TRACK_BUTTONS.by_id:
			self._dispatch[note_id] = self._handle_track_button
		for note_id in mapping.SCENE_BUTTONS.by_id:
			self._dispatch[note_id] = self._handle_scene_button
		for cc in range(0x30, 0x38):
			self._dispatch[cc] = self._handle_knob
		self._dispatch[mapping.SOUND_BUTTONS.id_for("shift")] = self._handle_shift
		self._dispatch[mapping.SOUND_BUTTONS.id_for("play")] = self._handle_play
		self._dispatch[mapping.SOUND_BUTTONS.id_for("record")] = self._handle_record

		self.deviceInfo()

	def _classify_control(self, note_id):
		"""Best-effort classification of an incoming note/CC id.

		Pad note IDs (0x00-0x27) can numerically collide with low keybed key
		numbers — see ControlStateStore's docstring. Anything in that range
		is classified PAD, matching how this script has always treated it;
		this hasn't been verified on hardware for genuine low keybed notes.
		"""
		if note_id in mapping.SOUND_BUTTONS or note_id in mapping.TRACK_BUTTONS or note_id in mapping.SCENE_BUTTONS:
			return ControlKind.FUNCTION_BUTTON
		if mapping.PAD_ID_START <= note_id < mapping.PAD_ID_END:
			return ControlKind.PAD
		if 0x30 <= note_id <= 0x37:
			return ControlKind.KNOB
		return ControlKind.KEY

	def _shift_active(self):
		"""SHIFT is a toggle (press to engage, press again to release — it
		ignores the physical release), so its ControlStateStore record is
		managed explicitly in the SHIFT branch below rather than by the
		generic press/release tracking at the top of eventHandler."""
		shift_id = mapping.SOUND_BUTTONS.id_for("shift")
		control = self.controlStates.get(ControlKind.FUNCTION_BUTTON, shift_id)
		return control.active if control is not None else False

	def _handle_pad_performance_trigger(self, event):
		"""If this pad's live-clip block is already playing, stop it via
		FL's playlist.triggerLiveClip API instead of leaving it to FL's own
		note-triggered retrigger (which just restarts the same clip on a
		second press). Must run on the pre-remap physical pad ID —
		event.data1 at this point, before eventHandler substitutes the
		computed performance note below — since mapping.PAD_TO_GRID_POSITION
		is keyed by physical pad IDs.

		Starting a clip is intentionally NOT done here via triggerLiveClip.
		An earlier version tried calling triggerLiveClip(row, col, 0)
		explicitly for starting too, but that broke starting for every row
		on real hardware — flags=0 doesn't reproduce whatever raw-note
		triggering actually does. Starting is left to FL's own note-based
		triggering, but the note sent is now computed dynamically
		(mapping.performance_note_for, in eventHandler) using the same
		track_offset as this method, so starting also follows scrolling
		instead of always targeting the original unscrolled track.

		getLiveBlockStatus(row, col, 0) returns a bitmask: filled=1,
		scheduled=2, playing=4 (FL Studio MIDI scripting docs). Only the
		playing bit matters here — a filled-but-not-yet-playing (scheduled)
		block shouldn't be stopped by a press, it should start.
		"""
		if event.data2 == 0:
			return  # only act on press, not release

		grid_pos = mapping.PAD_TO_GRID_POSITION.get(event.data1)
		if grid_pos is None:
			return

		row, col = grid_pos
		track = row + self.live.track_offset  # physical row -> currently-scrolled-to playlist track
		status = playlist.getLiveBlockStatus(track, col, 0)
		if status & 4:
			# blockNum=-1 + TLC_Fill stops whatever's currently playing on
			# this track/row (only one block per row can play at a time, so
			# this is equivalent to stopping this specific block).
			playlist.triggerLiveClip(track, -1, midi.TLC_Fill)
			log_status(f"Stopped live clip: row={row} track={track} col={col} pad={event.data1}")
			event.handled = True

	# knobAdjust normalizes velocity data that is "built-in" to knob turns.
	def knobAdjust(self, event):
		knob = event.data1 - 48
		value = event.data2

		if value > 100 and value < 128:
			vel = (value - 127) * -1
			if self.knobs[knob] > -1:
				self.knobs[knob] = self.knobs[knob] - (vel+1)
				if self.knobs[knob] < 1:
					self.knobs[knob] = 1
			log_verbose(f"knob={knob} dir=down delta=-{vel+1} value={self.knobs[knob]}")

		if value > 0 and value < 28:
			vel = value
			if self.knobs[knob] < 128:
				self.knobs[knob] = self.knobs[knob] + (vel+1)
				if self.knobs[knob] > 128:
					self.knobs[knob] = 128
			log_verbose(f"knob={knob} dir=up delta=+{vel+1} value={self.knobs[knob]}")

		event.data2 = self.knobs[knob]
		return(event)

	def eventHandler(self, event):
		# Map the pads if in performance mode
		if self.state.isPerformance():
			log_verbose(f"performance-mode remap: shift={self._shift_active()} data1={event.data1} data2={event.data2}")
			self._handle_pad_performance_trigger(event)
			grid_pos = mapping.PAD_TO_GRID_POSITION.get(event.data1)
			if grid_pos is not None:
				row, col = grid_pos
				track = row + self.live.track_offset
				event.data1 = mapping.performance_note_for(track, col)
				# This note originated from a performance-mode pad press and
				# must pass through to FL untouched as a plain note — it
				# must NEVER fall into the dispatch lookup below, even if
				# the computed note value numerically collides with a knob/
				# button ID (e.g. unscrolled row 5 computes to notes 48-55,
				# which is exactly the CC range 0x30-0x37 used by the 8
				# physical knobs). That collision used to hijack row-5 pad
				# presses into _handle_knob, mangling event.data2 and
				# marking the event handled, which silently ate the note
				# before it ever reached FL. Confirmed via verbose logs on
				# real hardware.
				return
			# Not marked handled: this only remaps event.data1 before
			# dispatch below decides what (if anything) to do with it.

		# Track press/release state for everything except knobs (their
		# value is recorded separately, post-decode, in _handle_knob —
		# "active" doesn't map cleanly onto a relative encoder) and SHIFT
		# (a toggle, managed explicitly in _handle_shift — see
		# _shift_active).
		control_kind = self._classify_control(event.data1)
		if control_kind != ControlKind.KNOB and event.data1 != mapping.SOUND_BUTTONS.id_for("shift"):
			self.controlStates.set_active(control_kind, event.data1, event.data2 != 0)

		handler = self._dispatch.get(event.data1)
		if handler is not None:
			handler(event)

	def _handle_shift(self, event):
		# SHIFT — toggle: press to engage, press again to release (the
		# physical release/note-off is ignored, matching the original
		# behavior). Tracked via ControlStateStore instead of a separate
		# flag so there's one place controller state lives.
		if event.data2 == 127:
			if self._shift_active():
				self.controlStates.set_active(ControlKind.FUNCTION_BUTTON, event.data1, False)
				print("shift active")
				self.buttons.knob_ctrl_dim()
				#self.buttons.all_funcs_stop_flash()
			else:
				self.controlStates.set_active(ControlKind.FUNCTION_BUTTON, event.data1, True)
				print("shift inactive")
				self.buttons.knob_ctrl_bright()
				#self.buttons.all_funcs_flash()

		# event.handled=True is provisional: set for now so FL doesn't also
		# pass shift/play/record/knobs through as raw MIDI on top of the
		# script's own handling. Revisit after testing on hardware — may
		# need to be per-event-type instead of blanket.
		event.handled = True

	def _handle_play(self, event):
		if event.data2 == 127:
			if self.state.isPlaying() == 1:
				self.controls.togglePlay()
				self.state.isPlaying(set=0)
			else:
				self.state.isPlaying(set=1)
				self.controls.togglePlay()
		event.handled = True

	def _handle_record(self, event):
		if event.data2 == 127:
			# toggleRecord() calls transport.record() and resyncs
			# self.state from FL itself — call it on every press instead
			# of only when turning recording on. Only calling it when
			# turning recording on would never tell FL to stop recording
			# when pressed while already recording.
			self.controls.toggleRecord()
		event.handled = True

	def _handle_track_button(self, event):
		# SHIFT + up/down, in performance mode: scroll the visible 5-row
		# pad window up/down the playlist track list. Everything else
		# about the track buttons is still a stub (see below).
		if self.state.isPerformance() and self._shift_active():
			name = mapping.TRACK_BUTTONS_SHIFT[event.data1]
			if name in ("up", "down"):
				if event.data2 != 0:  # only scroll on press, not release
					self.live.scroll(-1 if name == "up" else 1)
				event.handled = True
				return

		# Stubbed for now. Not wired to any action yet (undecided what
		# these should do); shift-mode names are already mapped in
		# mapping.py (TRACK_BUTTONS_SHIFT) for whenever this gets
		# implemented.
		name = mapping.TRACK_BUTTONS_SHIFT[event.data1] if self._shift_active() else mapping.TRACK_BUTTONS[event.data1]
		log_status(f"[stub] track button '{name}' ({hex(event.data1)}) not implemented")
		event.handled = True

	def _handle_scene_button(self, event):
		# Stubbed for now — see _handle_track_button.
		name = mapping.SCENE_BUTTONS_SHIFT[event.data1] if self._shift_active() else mapping.SCENE_BUTTONS[event.data1]
		log_status(f"[stub] scene button '{name}' ({hex(event.data1)}) not implemented")
		event.handled = True

	def _handle_knob(self, event):
		self.knobAdjust(event)
		self.controlStates.set_value(ControlKind.KNOB, event.data1, event.data2)
		event.handled = True

	def deviceInfo(self):
		log_status(f"Device Info: name={device.getName()!r} assigned={device.isAssigned()}")

		if DEBUG_LEVEL.value < DebugLevel.VERBOSE.value:
			#skip all the boring debug data
			return()

		# deviceID Data Map
		self.dIdMap: list[Optional[str]] = [None] * 29
		self.dIdMap[0] = "Manu. ID" # 0x47
		self.dIdMap[1] = "Prod. ID" # 0x4E
		self.dIdMap[2] = "Bytes Start" # 0x00
		self.dIdMap[3] = "Bytes End" # 0x19
		self.dIdMap[4] = "<Version>"
		self.dIdMap[5:7] = ["xxx", "xxx"]
		self.dIdMap[8] = "<DeviceID>"
		self.dIdMap[9] = "<Serial>"
		self.dIdMap[10:12] = ["xxx", "xxx"]
		self.dIdMap[13] = "<Manufacturing>"
		self.dIdMap[14:28] = ["xxxxxxxxxxxxxxx"] * 14

		self.parseDevID()

	def parseDevID(self):
		mmcOffset = 5
		for idx,c in enumerate(device.getDeviceID()):
			log_verbose(f"raw device ID byte {idx:02d}/{idx+1+mmcOffset:02d} ({self.dIdMap[idx]}): 0x{c:02X}")

# Our transport class
class TransportHandler():
	def __init__(self, state):
		self.state = state
		self.state.refresh()

	def toggleLoopMode(self):
		if (transport.isPlaying() == 0): #Only toggle loop mode if not already playing
			transport.setLoopMode()
			log_status("Song/Pattern Mode toggled")

	def pressFastForward(self):
		transport.fastForward(2)

	def pressRewind(self):
		transport.rewind(2)

	def togglePlay(self):
		if (transport.isPlaying() == 0):
			transport.start()
			self.state.isPlaying(set=1)
		elif (transport.isPlaying() == 1):
			transport.stop()
			self.state.isPlaying(set=0)
		log_verbose(f"isPlaying={transport.isPlaying()}")

	def toggleRecord(self):
		if (transport.isPlaying() == 0): # Only enable recording if not already playing
			transport.record()
			self.state.refresh()  # resync isRecording (and isPlaying/isPerformance) from FL after the toggle
			log_status(f"Toggled recording: {self.state.isRecording()}")
		else:
			self.state.isRecording(set=0)
			log_status("Currently Playing; Canceled Record Command")

class PadLighting():
	def __init__(self, midiHandler, state, controlStates):
		self.midiHandler = midiHandler
		self.state = state
		self.controlStates = controlStates

		self.initialDim = mapping.PAD_LED_FUNCTION.id_for("bright_2")
		self.initialColor = 0x02 # a bright white/grey or something
		time.sleep(1)

		log_status("Turning pads on...")
		time.sleep(3)
		self.all_pads_on(speed=0.01)
		#self.animate_pads_on(speed=0.05)
		self.all_pads_dim(self.initialColor, speed=0.05)

		log_status("Turning on function buttons...")
		self.all_funcs_on()

	def cycle_pads(self, command, value, speed=0.05):
		# Bulk pad sweep: always sends, doesn't diff against tracked state —
		# the point of this method is guaranteed uniform state across every
		# pad, not traffic reduction. It also keeps the store in sync so the
		# single-pad diffed methods below (pad_led_on/off etc.) have an
		# accurate baseline afterward.
		for a in range(mapping.PAD_ID_START, mapping.PAD_ID_END):
			device.midiOutMsg(command + (a << 8) + (value << 16))
			self.controlStates.set_led(ControlKind.PAD, a, command, value)
			time.sleep(speed)

	def _set_func_buttons(self, value):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_0")
		for key in mapping.TRACK_BUTTONS.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

		for key in mapping.SCENE_BUTTONS.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def _set_knob_ctrl_dim(self, value):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		for key in mapping.KNOB_CTRL.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def _set_knob_ctrl_bright(self, value):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_0")
		for key in mapping.KNOB_CTRL.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def all_funcs_on(self):
		self._set_func_buttons(0x01)

	def all_funcs_off(self):
		self._set_func_buttons(0x00)

	def all_funcs_flash(self):
		self._set_func_buttons(0x02)

	def all_funcs_stop_flash(self):
		self._set_func_buttons(0x01)

	def knob_ctrl_dim(self):
		self._set_knob_ctrl_dim(0x00)

	def knob_ctrl_bright(self):
		self._set_knob_ctrl_dim(0x01)

	def all_pads_on(self, speed=0.05):
		log_verbose(f"speed={speed}")
		# no bright, no color
		self.cycle_pads(mapping.PAD_LED_FUNCTION.id_for("bright_0"), 0x00, speed=speed)

	def animate_pads_on(self, speed=0.1):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_5")
		for row in mapping.START_PATTERN:
			for key in row:
				self.midiHandler.sendMessage(mode, key, 0x05)
				self.controlStates.set_led(ControlKind.PAD, key, mode, 0x05)
				time.sleep(0.02)

	def animate_pads_off(self, speed=0.1):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_5")
		for row in mapping.START_PATTERN:
			for key in row:
				self.midiHandler.sendMessage(mode, key, 0x22)
				self.controlStates.set_led(ControlKind.PAD, key, mode, 0x22)
				time.sleep(0.02)

	def all_pads_off(self, speed=0.05):
		# no bright, no color
		log_verbose(f"speed={speed}")
		self.cycle_pads(mapping.PAD_LED_FUNCTION.id_for("bright_0"), 0x00, speed=speed)

	def all_pads_dim(self, color, speed=0.05):
		log_verbose(f"color={color} speed={speed}")
		self.cycle_pads(self.initialDim, color, speed=speed)

	# The single-pad methods below diff against the tracked state and skip
	# sending when nothing would change — these are the natural call sites
	# for that (e.g. PerformanceMode redraws the whole live-clip grid on
	# every playlist update, one pad at a time).

	def pad_color(self, key, color):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		if self.controlStates.set_led(ControlKind.PAD, key, mode, color):
			self.midiHandler.sendMessage(mode, key, color)

	def pad_pressed(self, key):
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		if self.controlStates.set_led(ControlKind.PAD, key, mode, 10):
			self.midiHandler.sendMessage(mode, key, 10)

	def pad_unpressed(self, key):
		if self.controlStates.set_led(ControlKind.PAD, key, self.initialDim, self.initialColor):
			self.midiHandler.sendMessage(self.initialDim, key, self.initialColor)

	def pad_led_on(self, mode, key, color):
		if self.controlStates.set_led(ControlKind.PAD, key, mode, color):
			self.midiHandler.sendMessage(mode, key, color)

	def pad_led_off(self, key):
		if self.controlStates.set_led(ControlKind.PAD, key, self.initialDim, self.initialColor):
			self.midiHandler.sendMessage(self.initialDim, key, self.initialColor)


class PerformanceMode:
	def __init__(self, lighting, state):
		self.lighting = lighting
		self.state = state
		self.pos = mapping.LIVE_GRID_PAD_POSITIONS
		self._first_run = True

		# How many tracks the visible 5-row pad window is scrolled down by.
		# Pad grid row `idx` (1-5) always displays playlist track
		# `idx + track_offset`. 0 = default (rows 1-5 -> tracks 1-5).
		self.track_offset = 0

		# select_tracks() is NOT called here: playlist.selectTrack()/
		# deselectAll() raise "Operation unsafe at current time" when called
		# from module-level construction (script import time) — confirmed
		# on real hardware. Read-only playlist calls (getLiveBlockStatus
		# etc., used below) are fine at this point; only the initial track
		# selection needs to wait for OnInit(), which FL calls once the
		# script has actually finished loading. See module-level OnInit().

		# If script restart, this should update the LEDs
		self.OnUpdateLiveMode(0)

	def select_tracks(self):
		"""Select the 5 playlist tracks currently visible in the pad grid,
		matching the current scroll position. selectTrack() only toggles
		(no absolute "select" call exists), so deselect everything first to
		get a deterministic result regardless of prior selection."""
		playlist.deselectAll()
		for idx in range(1, 6):
			playlist.selectTrack(idx + self.track_offset)

	def scroll(self, delta):
		"""Shift the visible track window by `delta` rows (+1 = down, -1 =
		up). Clamped so the topmost visible track can never go below 1."""
		new_offset = max(0, self.track_offset + delta)
		if new_offset == self.track_offset:
			return
		self.track_offset = new_offset
		log_status(f"track_offset={self.track_offset} (tracks {1 + self.track_offset}-{5 + self.track_offset})")
		self.select_tracks()
		self.OnUpdateLiveMode(self.track_offset)

	def debugLiveMode(self, value):
		if DEBUG_LEVEL.value < DebugLevel.VERBOSE.value:
			return()

		num = patterns.patternNumber()
		log_verbose(
			f"pattern={num} name={patterns.getPatternName(num)!r} "
			f"len={patterns.getPatternLength(num)} selected={patterns.isPatternSelected(num)} "
			f"color={hex(patterns.getPatternColor(num) & 0xffffffff)} "
			f"(max={patterns.patternMax()} count={patterns.patternCount()})"
		)

		for a in range(1, 10):
			log_verbose(f"live status row={a} col0={playlist.getLiveStatus(a,0)} col1={playlist.getLiveStatus(a,1)}")

		trackNum = 1
		log_verbose(
			f"track={trackNum} name={playlist.getTrackName(trackNum)!r} "
			f"selected={playlist.isTrackSelected(trackNum)} count={int(playlist.trackCount())} "
			f"loopMode={playlist.getLiveLoopMode(trackNum)} triggerMode={playlist.getLiveTriggerMode(trackNum)} "
			f"posSnap={playlist.getLivePosSnap(trackNum)} trigSnap={playlist.getLiveTrigSnap(trackNum)}"
		)

	# This needs a serious cleanup.
	def OnUpdateLiveMode(self, value):
		if self._first_run:
			self._first_run = False
			log_status("Performance Mode Init!")

		self.debugLiveMode(value)

		# idx      = physical pad row, top -> bottom (fixed, 1-5)
		# track    = playlist track currently displayed on that row
		#            (shifts with track_offset; idx alone is never passed
		#            to playlist.* — only to self.pos, which addresses
		#            physical pads and doesn't move when scrolling)
		# blocknum = left -> right
		for idx in range(1, 6):
			track = idx + self.track_offset
			for blockNum in range(0, 8):
				active = playlist.getLiveBlockStatus(track,blockNum,0)
				if active:
					color_hex = hex(playlist.getLiveBlockColor(track,blockNum) & 0xffffffff)
					if active == 7:
						self.lighting.pad_led_on(mapping.PAD_LED_FUNCTION.id_for("bright_4"), self.pos[idx][blockNum], 6)
						log_verbose(f"row={idx} track={track} col={blockNum} pad={self.pos[idx][blockNum]} active=7 color={color_hex}")
					else:
						self.lighting.pad_led_on(mapping.PAD_LED_FUNCTION.id_for("bright_4"), self.pos[idx][blockNum], 1)
						log_verbose(f"row={idx} track={track} col={blockNum} pad={self.pos[idx][blockNum]} active={active} color={color_hex}")
				else:
					self.lighting.pad_led_off(self.pos[idx][blockNum])

		log_verbose(f"event={value}")

class MidiMessaging():
	def sendMessage(self, command, key, value):
		device.midiOutMsg((command) + (key << 8) + (value << 16))

start = InitClass()
midiHandler = MidiMessaging()
state = SessionState()
controlStates = build_control_state_store()
controls = TransportHandler(state)
lighting = PadLighting(midiHandler, state, controlStates)
live = PerformanceMode(lighting, state)
kbd = DeviceHandler(midiHandler, controls, lighting, state, controlStates, live)

def OnUpdateLiveMode(event):
	log_verbose(f"event={event}")
	live.OnUpdateLiveMode(event)

def OnControlChange(event):
	pass

# FL Studio unifies both of the device's physical MIDI ports into these two
# callbacks itself; the script doesn't need to know which physical port an
# event came from. The isPerformance() gate below is intentional and stays as
# the single dispatch mechanism — confirmed sufficient, not a gap to fix.
def OnMidiMsg(event):
	# eventHandler mutates event in place and returns nothing — don't
	# reassign `event` from its result (that would make it None).
	state.refresh()
	if state.isPerformance():
		kbd.eventHandler(event)
		log_verbose(f"data1={event.data1} data2={event.data2}")

def OnMidiIn(event):
	state.refresh()
	if not state.isPerformance():
		kbd.eventHandler(event)

def OnMidiOutMsg(event):
	pass

def OnSysEx(event):
	log_status(f"** onSysEx: {event}")

def OnInit():
	log_status("onInit")
	# Deferred from PerformanceMode.__init__ — playlist.selectTrack()/
	# deselectAll() are unsafe to call during module-level construction
	# (script import time), but are fine here.
	live.select_tracks()

def OnDeInit():
	log_status("onDeInit")
	lighting.all_funcs_off()
	#lighting.animate_pads_off()