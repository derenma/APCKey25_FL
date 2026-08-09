# name=APCKey25mk2V3
# url=https://forum.image-line.com/viewtopic.php?t=323673
# Author: Matt Deren
# Inspired by original script by Martijn Tromp: https://forum.image-line.com/viewtopic.php?f=1994&t=225886
# This script has very little in common with the original and has morphed into its own beast.
# See DEV_NOTES.md for compatibility notes, the SysEx RGB debug snippets, and other design-decision history.
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
class DebugLevel(Enum):
	"""Verbosity levels for `log_status`/`log_verbose`, checked cheaply so
	callers don't need their own "if debug" guards for the common case.

	Attributes:
		OFF: Nothing is logged.
		STATUS: General script status: init sequence, mode/transport changes,
			stub buttons firing. Readable at a glance, safe to leave on.
		VERBOSE: Everything above, plus per-event tracing, raw device ID
			dumps, and live-clip grid internals. Noisy — turn on only when
			actively debugging.
	"""
	OFF = 0
	STATUS = 1
	VERBOSE = 2

DEBUG_LEVEL = DebugLevel.STATUS

def log_status(msg):
	"""Print `msg` if `DEBUG_LEVEL` is at least `DebugLevel.STATUS`.

	Args:
		msg: Message to print, prefixed with `[APCKey25]`.
	"""
	if DEBUG_LEVEL.value >= DebugLevel.STATUS.value:
		print(f"[APCKey25] {msg}")

def _caller_label():
	"""Build a short label identifying who called `log_verbose`.

	Returns:
		str: `'ClassName.method'` for the caller of the caller of this
		function (i.e. whoever called `log_verbose`), or just the bare
		function name at module scope.
	"""
	frame = sys._getframe(2)
	func_name = frame.f_code.co_name
	self_obj = frame.f_locals.get("self")
	if self_obj is not None:
		return f"{type(self_obj).__name__}.{func_name}"
	return func_name

def log_verbose(msg):
	"""Print `msg` if `DEBUG_LEVEL` is at least `DebugLevel.VERBOSE`.

	Args:
		msg: Message to print. Automatically prefixed with the calling
			method's `ClassName.method` (via `_caller_label`), so callers
			don't need to restate where the message came from.
	"""
	if DEBUG_LEVEL.value >= DebugLevel.VERBOSE.value:
		print(f"[APCKey25:verbose] {_caller_label()}: {msg}")

class InitClass():
	"""Tiny helper that logs script init and gives the device a moment to
	settle before any MIDI is sent. Instantiated once at module scope."""
	def __init__(self):
		log_status("Init.")
		time.sleep(1)


class ControlKind(Enum):
	"""Category of a physical control, used as part of `ControlStateStore`'s
	lookup key so numerically-colliding IDs (see its docstring) don't clobber
	each other's tracked state."""
	KEY = "key"
	KNOB = "knob"
	PAD = "pad"
	FUNCTION_BUTTON = "function_button"


@dataclass
class ControlState:
	"""Tracked state for one physical control (key, knob, pad, or function button).

	Attributes:
		id: Note/CC id of the control.
		kind: The control's `ControlKind`.
		active: Pressed/held (keys, pads, function buttons); unused for knobs.
		value: Knob value (0-127); unused for everything else.
		led_mode: Pad LED status byte, i.e. a `mapping.PAD_LED_FUNCTION` id
			(pads/function buttons only).
		color: Velocity-palette index 0-127 (pads/function buttons only).
	"""
	id: int
	kind: ControlKind
	active: bool = False
	value: int = 0
	led_mode: Optional[int] = None
	color: int = 0


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
		"""Create and store a fresh `ControlState` for `(kind, control_id)`.

		Args:
			kind: The control's `ControlKind`.
			control_id: Note/CC id of the control.
			**kwargs: Extra `ControlState` field overrides.
		"""
		self._controls[(kind, control_id)] = ControlState(id=control_id, kind=kind, **kwargs)

	def get(self, kind, control_id):
		"""Look up the tracked state for one control.

		Args:
			kind: The control's `ControlKind`.
			control_id: Note/CC id of the control.

		Returns:
			ControlState | None: The tracked state, or `None` if
			`(kind, control_id)` was never registered.
		"""
		return self._controls.get((kind, control_id))

	def all(self, kind=None):
		"""List tracked controls.

		Args:
			kind: If given, only return controls of this `ControlKind`.

		Returns:
			list[ControlState]: All matching tracked controls.
		"""
		if kind is None:
			return list(self._controls.values())
		return [c for c in self._controls.values() if c.kind == kind]

	def set_active(self, kind, control_id, active):
		"""Update a control's pressed/held state, if it's registered.

		Args:
			kind: The control's `ControlKind`.
			control_id: Note/CC id of the control.
			active: New pressed/held state.
		"""
		control = self._controls.get((kind, control_id))
		if control is not None:
			control.active = active

	def set_value(self, kind, control_id, value):
		"""Update a control's value (knobs), if it's registered.

		Args:
			kind: The control's `ControlKind`.
			control_id: Note/CC id of the control.
			value: New value.
		"""
		control = self._controls.get((kind, control_id))
		if control is not None:
			control.value = value

	def set_led(self, kind, control_id, led_mode, color):
		"""Record LED state for a pad/function button.

		Args:
			kind: The control's `ControlKind`.
			control_id: Note/CC id of the control.
			led_mode: LED status byte (`mapping.PAD_LED_FUNCTION` id) being set.
			color: Velocity-palette index being set.

		Returns:
			bool: `True` if this is a change from what's already tracked —
			callers use this to skip sending redundant MIDI. Unregistered
			controls always report changed (nothing to compare against), so
			the message is sent either way.
		"""
		control = self._controls.get((kind, control_id))
		if control is None:
			return True
		changed = control.led_mode != led_mode or control.color != color
		control.led_mode = led_mode
		control.color = color
		return changed


def build_control_state_store():
	"""Build and populate a `ControlStateStore` covering every physical
	control on the device: pads, function buttons, knobs, and keybed keys.

	Note:
		Keybed key registration includes the range that numerically overlaps
		pad note IDs (`0x00`-`0x27`) — see `ControlStateStore`'s docstring.

	Returns:
		ControlStateStore: Store with one entry per control, all at their
		dataclass defaults.
	"""
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

	for note_id in range(mapping.MIDI_KEY_START, mapping.MIDI_KEY_END):
		store.register(ControlKind.KEY, note_id)

	return store

class SessionState():
	"""Mirrors FL's own transport/playlist state (not physical controller
	state — see `ControlStateStore` for that).

	`refresh()` is called once per incoming event by `OnMidiMsg`/`OnMidiIn`;
	the getters below just return the cached values in between.
	"""
	def __init__(self):
		self._isPlaying = 0
		self._isRecording = 0
		self._isPerformance = 0
		self.refresh()
		log_verbose(f"isPlaying={self._isPlaying} isRecording={self._isRecording} isPerformance={self._isPerformance}")

	def refresh(self):
		"""Explicit resync with FL transport/playlist state. Call once per
		incoming event, not from inside the getters below."""
		self._isPlaying = transport.isPlaying()
		self._isRecording = transport.isRecording()
		self._isPerformance = playlist.getPerformanceModeState()

	def isPlaying(self, set=None):
		"""Get, or force-set, the cached playing state.

		Args:
			set: If given, overwrite the cached value instead of just
				reading it (used after this script itself changes transport
				state, ahead of the next `refresh()`).

		Returns:
			int: The (possibly just-updated) cached playing state.
		"""
		if set is not None:
			self._isPlaying = set
		return(self._isPlaying)

	def isRecording(self, set=None):
		"""Get, or force-set, the cached recording state.

		Args:
			set: If given, overwrite the cached value instead of just
				reading it.

		Returns:
			int: The (possibly just-updated) cached recording state.
		"""
		if set is not None:
			self._isRecording = set
		return(self._isRecording)

	def isPerformance(self, set=None):
		"""Get, or force-set, the cached performance-mode state.

		Args:
			set: If given, overwrite the cached value instead of just
				reading it.

		Returns:
			int: The (possibly just-updated) cached performance-mode state.
		"""
		if set is not None:
			self._isPerformance = set
		return(self._isPerformance)

class DeviceHandler():
	"""Owns incoming-event handling for every physical control.

	`eventHandler` does a small amount of shared work (performance-mode
	remap, active-state tracking) and then dispatches to one `_handle_*`
	method per control via a lookup table built in `__init__`.
	"""
	def __init__(self, midiHandler, controls, buttons, state, controlStates, live):
		"""
		Args:
			midiHandler: `MidiMessaging` instance used to send raw LED MIDI.
			controls: `TransportHandler` instance for play/record/etc.
			buttons: `PadLighting` instance for outgoing LED control.
			state: Shared `SessionState` instance.
			controlStates: Shared `ControlStateStore` instance.
			live: `PerformanceMode` instance.
		"""
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

		Args:
			note_id: Incoming note or CC id.

		Returns:
			ControlKind: Best-effort classification of `note_id`.
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
		generic press/release tracking at the top of eventHandler.

		Returns:
			bool: `True` if SHIFT is currently engaged.
		"""
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

		Starting a clip is intentionally NOT done here — see DEV_NOTES.md:
		_handle_pad_performance_trigger for why.

		Args:
			event: Incoming FL MIDI event. Mutated in place (`event.handled`
				is set) if this press stops a playing clip; otherwise left
				untouched.

		Note:
			`getLiveBlockStatus(row, col, 0)` returns a bitmask: filled=1,
			scheduled=2, playing=4 (FL Studio MIDI scripting docs). Only the
			playing bit matters here — a filled-but-not-yet-playing
			(scheduled) block shouldn't be stopped by a press, it should
			start.
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
			# blockNum=-1 — see DEV_NOTES.md: _handle_pad_performance_trigger.
			playlist.triggerLiveClip(track, -1, midi.TLC_Fill)
			log_status(f"Stopped live clip: row={row} track={track} col={col} pad={event.data1}")
			event.handled = True

	def knobAdjust(self, event):
		"""Normalize the "built-in" relative-encoder velocity data a knob
		turn sends into an absolute per-knob value.

		Values just above 100 mean "turned down" (encoded as 127 minus the
		delta), values just above 0 mean "turned up" (the delta itself).
		This accumulates those deltas into a per-knob absolute value clamped
		to 1-128, stored in `self.knobs`.

		Args:
			event: Incoming FL MIDI event; `data1` selects the knob
				(`0x30`-`0x37`), `data2` carries the relative delta.

		Returns:
			The same `event`, with `data2` overwritten to the knob's new
			absolute value.
		"""
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
		"""Entry point for every incoming note/CC event on this device.

		In performance mode, pad presses are remapped to FL's expected
		live-clip trigger notes and returned immediately (never dispatched
		below — see the inline comment on the collision this used to cause
		with the knob CCs). Otherwise, this tracks press/release state for
		non-knob, non-SHIFT controls and dispatches to the bound `_handle_*`
		method for `event.data1`, if any.

		Args:
			event: Incoming FL MIDI event, mutated in place. Callers must
				not reassign `event` from this method's (non-existent)
				return value.
		"""
		# Map the pads if in performance mode
		if self.state.isPerformance():
			log_verbose(f"performance-mode remap: shift={self._shift_active()} data1={event.data1} data2={event.data2}")
			self._handle_pad_performance_trigger(event)
			grid_pos = mapping.PAD_TO_GRID_POSITION.get(event.data1)
			if grid_pos is not None:
				row, col = grid_pos
				track = row + self.live.track_offset
				event.data1 = mapping.performance_note_for(track, col)
				# Must NEVER fall into the dispatch lookup below — see DEV_NOTES.md: eventHandler
				# (performance-mode remap & the row-5/knob collision bug) for why.
				return
			# Not marked handled: this only remaps event.data1 before
			# dispatch below decides what (if anything) to do with it.

		# Knobs/SHIFT excluded — see DEV_NOTES.md: eventHandler.
		control_kind = self._classify_control(event.data1)
		if control_kind != ControlKind.KNOB and event.data1 != mapping.SOUND_BUTTONS.id_for("shift"):
			self.controlStates.set_active(control_kind, event.data1, event.data2 != 0)

		handler = self._dispatch.get(event.data1)
		if handler is not None:
			handler(event)

	def _handle_shift(self, event):
		"""Handle the SHIFT button.

		SHIFT is a toggle: press to engage, press again to release. The
		physical release/note-off is ignored by design (matches the
		original behavior); state lives in `ControlStateStore` rather than
		a separate flag so there's one place controller state lives.

		Args:
			event: Incoming FL MIDI event; only full presses (`data2 == 127`)
				toggle state. Always marked handled.
		"""
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

		# event.handled=True is provisional — see DEV_NOTES.md: _handle_shift.
		event.handled = True

	def _handle_play(self, event):
		"""Handle the PLAY button: toggle FL transport playback.

		Args:
			event: Incoming FL MIDI event; only full presses (`data2 == 127`)
				act. Always marked handled.
		"""
		if event.data2 == 127:
			if self.state.isPlaying() == 1:
				self.controls.togglePlay()
				self.state.isPlaying(set=0)
			else:
				self.state.isPlaying(set=1)
				self.controls.togglePlay()
		event.handled = True

	def _handle_record(self, event):
		"""Handle the REC button: toggle FL transport recording.

		Args:
			event: Incoming FL MIDI event; only full presses (`data2 == 127`)
				act. Always marked handled.
		"""
		if event.data2 == 127:
			# Called on every press — see DEV_NOTES.md: _handle_record.
			self.controls.toggleRecord()
		event.handled = True

	def _handle_track_button(self, event):
		"""Handle one of the 8 track-select buttons.

		In performance mode, SHIFT + up/down scrolls the visible 5-row pad
		window up/down the playlist track list. Everything else about the
		track buttons is still a stub — shift-mode names are already mapped
		in `mapping.py` (`TRACK_BUTTONS_SHIFT`) for whenever this gets
		implemented.

		Args:
			event: Incoming FL MIDI event. Always marked handled.
		"""
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
		"""Handle one of the 5 scene-launch buttons. Stubbed — see
		`_handle_track_button`.

		Args:
			event: Incoming FL MIDI event. Always marked handled.
		"""
		name = mapping.SCENE_BUTTONS_SHIFT[event.data1] if self._shift_active() else mapping.SCENE_BUTTONS[event.data1]
		log_status(f"[stub] scene button '{name}' ({hex(event.data1)}) not implemented")
		event.handled = True

	def _handle_knob(self, event):
		"""Handle a knob CC: decode its relative delta and record the
		resulting absolute value.

		Args:
			event: Incoming FL MIDI event. Always marked handled.
		"""
		self.knobAdjust(event)
		self.controlStates.set_value(ControlKind.KNOB, event.data1, event.data2)
		event.handled = True

	def deviceInfo(self):
		"""Log device name/assignment status, and — at `VERBOSE` debug level
		only — the raw device ID byte dump via `parseDevID`."""
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
		"""Log each byte of `device.getDeviceID()` alongside its label from
		`self.dIdMap`, at `VERBOSE` debug level."""
		mmcOffset = 5
		for idx,c in enumerate(device.getDeviceID()):
			log_verbose(f"raw device ID byte {idx:02d}/{idx+1+mmcOffset:02d} ({self.dIdMap[idx]}): 0x{c:02X}")

class TransportHandler():
	"""Play/record/loop/fast-forward/rewind wrappers around FL's `transport`
	module, kept in sync with the shared `SessionState`."""
	def __init__(self, state):
		self.state = state
		self.state.refresh()

	def toggleLoopMode(self):
		"""Toggle FL's song/pattern loop mode, but only if playback isn't
		already running."""
		if (transport.isPlaying() == 0): #Only toggle loop mode if not already playing
			transport.setLoopMode()
			log_status("Song/Pattern Mode toggled")

	def pressFastForward(self):
		"""Fast-forward FL's transport."""
		transport.fastForward(2)

	def pressRewind(self):
		"""Rewind FL's transport."""
		transport.rewind(2)

	def togglePlay(self):
		"""Start or stop FL playback (whichever is opposite the current
		state), and update `SessionState` to match."""
		if (transport.isPlaying() == 0):
			transport.start()
			self.state.isPlaying(set=1)
		elif (transport.isPlaying() == 1):
			transport.stop()
			self.state.isPlaying(set=0)
		log_verbose(f"isPlaying={transport.isPlaying()}")

	def toggleRecord(self):
		"""Start FL recording, if playback isn't already running.

		If playback is already running, recording is not started — the
		state is force-cleared instead. `SessionState` is resynced from FL
		after a successful toggle so `isRecording`/`isPlaying`/`isPerformance`
		all reflect FL's actual state.
		"""
		if (transport.isPlaying() == 0): # Only enable recording if not already playing
			transport.record()
			self.state.refresh()  # resync isRecording (and isPlaying/isPerformance) from FL after the toggle
			log_status(f"Toggled recording: {self.state.isRecording()}")
		else:
			self.state.isRecording(set=0)
			log_status("Currently Playing; Canceled Record Command")

class PadLighting():
	"""All outgoing LED control, for both the 5x8 pad grid and the
	track/scene function buttons.

	Note:
		The single-pad methods below (`pad_color`, `pad_pressed`,
		`pad_unpressed`, `pad_led_on`, `pad_led_off`) diff against
		`ControlStateStore` and skip sending when nothing would change —
		these are the natural call sites for that (e.g. `PerformanceMode`
		redraws the whole live-clip grid on every playlist update, one pad
		at a time). The bulk methods (`cycle_pads` and friends) always send,
		since their point is guaranteed uniform state across every pad, not
		traffic reduction.
	"""
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
		"""Send the same LED status byte/velocity to every pad.

		Always sends, doesn't diff against tracked state — the point of
		this method is guaranteed uniform state across every pad, not
		traffic reduction. It also keeps the store in sync so the
		single-pad diffed methods below (pad_led_on/off etc.) have an
		accurate baseline afterward.

		Args:
			command: LED status byte (`mapping.PAD_LED_FUNCTION` id).
			value: Velocity-palette index.
			speed: Seconds to sleep between pads.
		"""
		for a in range(mapping.PAD_ID_START, mapping.PAD_ID_END):
			device.midiOutMsg(command + (a << 8) + (value << 16))
			self.controlStates.set_led(ControlKind.PAD, a, command, value)
			time.sleep(speed)

	def _set_func_buttons(self, value):
		"""Send `value` to every track/scene function button LED."""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_0")
		for key in mapping.TRACK_BUTTONS.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

		for key in mapping.SCENE_BUTTONS.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def _set_knob_ctrl_dim(self, value):
		"""Send `value` to the 4 knob-control button LEDs at dim brightness."""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		for key in mapping.KNOB_CTRL.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def _set_knob_ctrl_bright(self, value):
		"""Send `value` to the 4 knob-control button LEDs at full brightness."""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_0")
		for key in mapping.KNOB_CTRL.by_id:
			self.midiHandler.sendMessage(mode, key, value)
			self.controlStates.set_led(ControlKind.FUNCTION_BUTTON, key, mode, value)

	def all_funcs_on(self):
		"""Turn on every track/scene function button LED."""
		self._set_func_buttons(0x01)

	def all_funcs_off(self):
		"""Turn off every track/scene function button LED."""
		self._set_func_buttons(0x00)

	def all_funcs_flash(self):
		"""Set every track/scene function button LED to flash."""
		self._set_func_buttons(0x02)

	def all_funcs_stop_flash(self):
		"""Stop every track/scene function button LED from flashing (back
		to solid on)."""
		self._set_func_buttons(0x01)

	def knob_ctrl_dim(self):
		"""Dim the 4 knob-control button LEDs (SHIFT engaged)."""
		self._set_knob_ctrl_dim(0x00)

	def knob_ctrl_bright(self):
		"""Brighten the 4 knob-control button LEDs (SHIFT released)."""
		self._set_knob_ctrl_dim(0x01)

	def all_pads_on(self, speed=0.05):
		"""Turn on every pad LED (no color, no extra brightness).

		Args:
			speed: Seconds to sleep between pads.
		"""
		log_verbose(f"speed={speed}")
		# no bright, no color
		self.cycle_pads(mapping.PAD_LED_FUNCTION.id_for("bright_0"), 0x00, speed=speed)

	def animate_pads_on(self, speed=0.1):
		"""Light pads one at a time in `mapping.START_PATTERN` order, for
		the power-on animation.

		Args:
			speed: Unused — kept for call-site symmetry with
				`animate_pads_off`; the per-pad delay is currently
				hardcoded below.
		"""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_5")
		for row in mapping.START_PATTERN:
			for key in row:
				self.midiHandler.sendMessage(mode, key, 0x05)
				self.controlStates.set_led(ControlKind.PAD, key, mode, 0x05)
				time.sleep(0.02)

	def animate_pads_off(self, speed=0.1):
		"""Turn off pads one at a time in `mapping.START_PATTERN` order, for
		the shutdown animation.

		Args:
			speed: Unused — see `animate_pads_on`.
		"""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_5")
		for row in mapping.START_PATTERN:
			for key in row:
				self.midiHandler.sendMessage(mode, key, 0x22)
				self.controlStates.set_led(ControlKind.PAD, key, mode, 0x22)
				time.sleep(0.02)

	def all_pads_off(self, speed=0.05):
		"""Turn off every pad LED (no color, no extra brightness).

		Args:
			speed: Seconds to sleep between pads.
		"""
		# no bright, no color
		log_verbose(f"speed={speed}")
		self.cycle_pads(mapping.PAD_LED_FUNCTION.id_for("bright_0"), 0x00, speed=speed)

	def all_pads_dim(self, color, speed=0.05):
		"""Set every pad LED to `color` at the default dim brightness.

		Args:
			color: Velocity-palette index.
			speed: Seconds to sleep between pads.
		"""
		log_verbose(f"color={color} speed={speed}")
		self.cycle_pads(self.initialDim, color, speed=speed)

	def pad_color(self, key, color):
		"""Set one pad to `color` at bright_4, if different from its
		currently tracked state.

		Args:
			key: Pad note id.
			color: Velocity-palette index.
		"""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		if self.controlStates.set_led(ControlKind.PAD, key, mode, color):
			self.midiHandler.sendMessage(mode, key, color)

	def pad_pressed(self, key):
		"""Light one pad to indicate it's pressed, if different from its
		currently tracked state.

		Args:
			key: Pad note id.
		"""
		mode = mapping.PAD_LED_FUNCTION.id_for("bright_4")
		if self.controlStates.set_led(ControlKind.PAD, key, mode, 10):
			self.midiHandler.sendMessage(mode, key, 10)

	def pad_unpressed(self, key):
		"""Return one pad to its default dim state, if different from its
		currently tracked state.

		Args:
			key: Pad note id.
		"""
		if self.controlStates.set_led(ControlKind.PAD, key, self.initialDim, self.initialColor):
			self.midiHandler.sendMessage(self.initialDim, key, self.initialColor)

	def pad_led_on(self, mode, key, color):
		"""Set one pad's LED status/color, if different from its currently
		tracked state.

		Args:
			mode: LED status byte (`mapping.PAD_LED_FUNCTION` id).
			key: Pad note id.
			color: Velocity-palette index.
		"""
		if self.controlStates.set_led(ControlKind.PAD, key, mode, color):
			self.midiHandler.sendMessage(mode, key, color)

	def pad_led_off(self, key):
		"""Return one pad to its default dim state, if different from its
		currently tracked state. Alias of `pad_unpressed`, used by
		`PerformanceMode` for empty grid cells.

		Args:
			key: Pad note id.
		"""
		if self.controlStates.set_led(ControlKind.PAD, key, self.initialDim, self.initialColor):
			self.midiHandler.sendMessage(self.initialDim, key, self.initialColor)


class PerformanceMode:
	"""Mirrors FL's live-clip launch grid onto the pad LEDs, and owns the
	track-scroll window used to translate between physical pad rows and
	playlist tracks.

	Attributes:
		track_offset: How many tracks the visible 5-row pad window is
			scrolled down by. Pad grid row `idx` (1-5) always displays
			playlist track `idx + track_offset`. `0` = default
			(rows 1-5 -> tracks 1-5).
	"""
	def __init__(self, lighting, state):
		"""
		Args:
			lighting: `PadLighting` instance used to draw the grid.
			state: Shared `SessionState` instance.
		"""
		self.lighting = lighting
		self.state = state
		self.pos = mapping.LIVE_GRID_PAD_POSITIONS
		self._first_run = True
		self.track_offset = 0

		# select_tracks() is NOT called here — see DEV_NOTES.md:
		# PerformanceMode.__init__ for why. See module-level OnInit().

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
		"""Shift the visible track window by `delta` rows and redraw.

		Args:
			delta: `+1` to scroll down, `-1` to scroll up.

		Note:
			Clamped so the topmost visible track can never go below 1. If
			the offset doesn't actually change (e.g. scrolling up while
			already at the top), nothing is reselected or redrawn.
		"""
		new_offset = max(0, self.track_offset + delta)
		if new_offset == self.track_offset:
			return
		self.track_offset = new_offset
		log_status(f"track_offset={self.track_offset} (tracks {1 + self.track_offset}-{5 + self.track_offset})")
		self.select_tracks()
		self.OnUpdateLiveMode(self.track_offset)

	def debugLiveMode(self, value):
		"""Dump extra pattern/track/live-status details via `log_verbose`,
		at `VERBOSE` debug level only. Diagnostic aid, not required for
		normal operation.

		Args:
			value: Unused — accepted for symmetry with `OnUpdateLiveMode`,
				which calls this.
		"""
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
		"""Redraw every pad LED from FL's current live-clip grid state.

		Called by FL (via the module-level `OnUpdateLiveMode` callback)
		whenever the live-clip grid changes, and once at startup/scroll to
		force a full redraw.

		Args:
			value: Event value passed through from FL; only used for
				logging here.

		Note:
			`idx` is the physical pad row, top to bottom (fixed, 1-5).
			`track` is the playlist track currently displayed on that row
			(shifts with `track_offset`; `idx` alone is never passed to
			`playlist.*` — only to `self.pos`, which addresses physical
			pads and doesn't move when scrolling). `blockNum` runs left to
			right.
		"""
		if self._first_run:
			self._first_run = False
			log_status("Performance Mode Init!")

		self.debugLiveMode(value)

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
	"""Thin helper for sending short (non-SysEx) MIDI-out messages."""
	def sendMessage(self, command, key, value):
		"""Send a short MIDI-out message.

		Args:
			command: Status byte (e.g. a `mapping.PAD_LED_FUNCTION` id).
			key: Data byte 1 (note/CC number).
			value: Data byte 2 (velocity/value).
		"""
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
	"""FL callback: forwarded to `PerformanceMode.OnUpdateLiveMode`.

	Args:
		event: Event value passed through from FL.
	"""
	log_verbose(f"event={event}")
	live.OnUpdateLiveMode(event)

def OnControlChange(event):
	"""FL callback: currently unused.

	Args:
		event: Incoming FL MIDI event.
	"""
	pass

# See DEV_NOTES.md: OnMidiMsg / OnMidiIn for the dual-port dispatch rationale.
def OnMidiMsg(event):
	"""FL callback for one of the device's two physical MIDI ports.

	Only dispatches into `DeviceHandler.eventHandler` while performance mode
	is active — see `OnMidiIn` for the complementary standard-mode port.

	Args:
		event: Incoming FL MIDI event, mutated in place by `eventHandler`.
			Don't reassign `event` from `eventHandler`'s (non-existent)
			return value.
	"""
	state.refresh()
	if state.isPerformance():
		kbd.eventHandler(event)
		log_verbose(f"data1={event.data1} data2={event.data2}")

def OnMidiIn(event):
	"""FL callback for the device's other physical MIDI port.

	Only dispatches into `DeviceHandler.eventHandler` while performance mode
	is *not* active — see `OnMidiMsg` for the complementary performance-mode
	port.

	Args:
		event: Incoming FL MIDI event, mutated in place by `eventHandler`.
	"""
	state.refresh()
	if not state.isPerformance():
		kbd.eventHandler(event)

def OnMidiOutMsg(event):
	"""FL callback: currently unused.

	Args:
		event: Outgoing FL MIDI event.
	"""
	pass

def OnSysEx(event):
	"""FL callback: log any incoming SysEx message.

	Args:
		event: Incoming FL SysEx event.
	"""
	log_status(f"** onSysEx: {event}")

def OnInit():
	"""FL callback: called once the script has finished loading.

	Performs the initial playlist track selection deferred from
	`PerformanceMode.__init__` — `playlist.selectTrack()`/`deselectAll()`
	are unsafe to call during module-level construction (script import
	time), but are fine here.
	"""
	log_status("onInit")
	live.select_tracks()

def OnDeInit():
	"""FL callback: called when the script is being unloaded. Turns off the
	function button LEDs."""
	log_status("onDeInit")
	lighting.all_funcs_off()
	#lighting.animate_pads_off()
