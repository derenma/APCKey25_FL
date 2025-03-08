# name=APCKey25mk2V2
# url=https://forum.image-line.com/viewtopic.php?f=1994&t=225886
# This import section is loading the back-end code required to execute the script. You may not need all modules that are available for all scripts.
import transport
import mixer
import ui
import sys
import device
import channels
import playlist
import patterns
import plugins
import screen
import midi
import time

# sysex info
ManufacturerIDConst = 0x47
DeviceIDBroadCastConst = 0x7F
ProductIDConst = 0x4E
MsgIDSetRGBPadLedState = 0x65

# Pad midi ID range
padIdStart = 0x00
padIdEnd = 0x28

# Color ranges for APCKey Pads
colorStart = 0x00
colorEnd = 0x7F

# Button ranges for track selection (botton 8 buttons below pads)
trackIdStart = 0x40
trackIdEend = 0x47

# Standard midi key range
midiKeyStart = 0x00
midiKeyEnd = 0x78

# Map out our song function buttons (build the dict and then build the reverse of key->data)
soundButtons = {
	0x51: "stop",
	0x5B: "play",
	0x5D: "record",
	0x62: "shift"
}
revSoundButtons = {value: key for key, value in soundButtons.items()}

trackButtons = {
	0x40: "track_1",
	0x41: "track_2",
	0x42: "track_3",
	0x43: "track_4",
	0x44: "track_5",
	0x45: "track_6",
	0x46: "track_7",
	0x47: "track_8"
}
revTrackButtons = {value: key for key, value in trackButtons.items()}

# !! 0x40 = "up" pressed/unpressed is value == 144/128
# !! 0x40 = "sustain" pressed/unpressed is value == 176
trackButtonsShift = {
	0x40: "up",
	0x41: "down",
	0x42: "left",
	0x43: "right",
	0x44: "knob_vol",
	0x45: "knob_pan",
	0x46: "knob_send",
	0x47: "knob_device"
}
revTrackButtonsShift = {value: key for key, value in trackButtonsShift.items()}

sceneButtons = {
	0x52: "scene_1",
	0x53: "scene_2",
	0x54: "scene_3",
	0x55: "scene_4",
	0x56: "scene_5"
}
revSceneButtons = {value: key for key, value in sceneButtons.items()}

sceneButtonsShift = {
	0x52: "clip_stop",
	0x53: "solo",
	0x54: "mute",
	0x55: "rec_arm",
	0x56: "select"
}
revSceneButtonsShift = {value: key for key, value in sceneButtonsShift.items()}

# This is our basic mapping for pad LED functions
padLEDFunction = {
	0x90: 'bright_0',
	0x91: 'bright_1',
	0x92: 'bright_2',
	0x93: 'bright_3',
	0x94: 'bright_4',
	0x95: 'bright_5',
	0x96: 'bright_6',
	0x97: 'pulse_1_16',
	0x98: 'pulse_1_8',
	0x99: 'pulse_1_4',
	0x9A: 'pulse_1_2',
	0x9B: 'blink_1_24',
	0x9C: 'blink_1_16',
	0x9D: 'blink_1_8',
	0x9E: 'blink_1_4',
	0x9F: 'blink_1_2'
}
revPadLEDFunction = {value: key for key, value in padLEDFunction.items()}

# Change the start animation if you want. It just plots the pads that are turned on in this order
startPattern = [[0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07],
				[0x0F,0x17,0x1F,0x27],
				[0x26,0x25,0x24,0x23,0x22,0x21,0x20],
				[0x18,0x10,0x08],
				[0x09,0x0A,0x0B,0x0C,0x0D,0x0E],
				[0x16,0x1E],
				[0x1D,0x1C,0x1B,0x1A,0x19],
				[0x11,0x12,0x13,0x14,0x15]]

class InitClass():
	def __init__(self):
		print("Init.")
		time.sleep(1)

class State():
	def __init__(self):
		print("State class init")
		self._isPlaying = 0
		self._isRecording = 0
		self._shiftActive = 0
		self._isPerformance = 0
		self._perfFirstRun = True
		self._perfRemapped = False
		self.getStates()

	def getStates(self):
		self._isPlaying = transport.isPlaying()
		self._isRecording = transport.isRecording()
		self._isPerformance = playlist.getPerformanceModeState()

	def perfFirstRun(self, set=None):
		if set is not None:
			self._perfFirstRun = set
		return(self._perfFirstRun)

	def isPlaying(self, set=None):
		self.getStates()
		if set is not None:
			self._isPlaying = set
		return(self._isPlaying)
	
	def isRecording(self, set=None):
		self.getStates()
		if set is not None:
			self._isRecording = set
		return(self._isRecording)
	
	def shiftActive(self, set=None):
		if set is not None:
			self._shiftActive = set
		return(self._shiftActive)

	def isPerformance(self, set=None):
		self.getStates()
		if set is not None:
			self._isPerformance = set
		return(self._isPerformance)
	
	def isPerfMapped(self, set=None):
		self.getStates()
		if set is not None:
			self._perfRemapped = set
		return(self._perfRemapped)

# This can be used to get all of your controller information
class DeviceHandler():
	def __init__(self, midiHandler, controls, buttons, state):
		self.midiHander = midiHandler
		self.buttons = buttons
		self.state = state
		self.controls = controls

		self.knobs = [0,0,0,0,0,0,0,0]
		
		self.map = {}
		self.map[0] = 48
		self.map[1] = 49
		self.map[2] = 50 
		self.map[3] = 51
		self.map[4] = 52
		self.map[5] = 53
		self.map[6] = 54
		self.map[7] = 55
		
		self.map[8] = 36
		self.map[9] = 37
		self.map[10] = 38
		self.map[11] = 39
		self.map[12] = 40
		self.map[13] = 41
		self.map[14] = 42
		self.map[15] = 43
		
		self.map[16] = 24
		self.map[17] = 25
		self.map[18] = 26
		self.map[19] = 27
		self.map[20] = 28
		self.map[21] = 29
		self.map[22] = 30
		self.map[23] = 31

		self.map[24] = 12
		self.map[25] = 13
		self.map[26] = 14
		self.map[27] = 15
		self.map[28] = 16
		self.map[29] = 17
		self.map[30] = 18
		self.map[31] = 19

		self.map[32] = 0
		self.map[33] = 1
		self.map[34] = 2
		self.map[35] = 3
		self.map[36] = 4
		self.map[37] = 5
		self.map[38] = 6
		self.map[39] = 7

		self.deviceInfo()

	def knobAdjust(self, event):
		knob = event.data1 - 48
		value = event.data2

		if value > 100 and value < 128:
			vel = (value - 127) * -1
			#old_val = self.knobs[knob]
			if self.knobs[knob] > -1:				
				self.knobs[knob] = self.knobs[knob] - (vel+1)
				if self.knobs[knob] < 1:
					self.knobs[knob] = 1
			#print(f"Knob {knob} DOWN by {vel+1} from {old_val}")

		if value > 0 and value < 28:
			vel = value
			old_val = self.knobs[knob]
			if self.knobs[knob] < 128:
				self.knobs[knob] = self.knobs[knob] + (vel+1)
				if self.knobs[knob] > 128:
					self.knobs[knob] = 128
			#print(f"Knob {knob} UP by {vel+1} from {old_val}")

		event.data2 = self.knobs[knob]
		#print(f"knob: {knob} 	in_value: {value}	const_val: {self.knobs[knob]}")
		return(event)

	def eventHandler(self, event):
		# Map the pads if in performance mode
		if self.state.isPerformance():
			print(f"Pads: {self.state.shiftActive()} [{event.data1} {event.data2}]")
			try:
				event.data1 = self.map[event.data1]
			except KeyError:
				pass
			#event.handled = True
			#return(event)

		## stateHandlers
		# SHIFT
		if event.data1 == revSoundButtons["shift"]:
			if event.data2 == 127:
				if self.state.shiftActive() == 1:
					self.state.shiftActive(set=0)
					self.buttons.all_funcs_stop_flash()
				else:
					self.state.shiftActive(set=1)
					self.buttons.all_funcs_flash()
   
			#print(f"Shift State: {self.shiftState} [{event.data1} {event.data2}]")
			event.handled = True
			#return(event)

		# PLAY
		if event.data1 == revSoundButtons["play"]:
			if event.data2 == 127:
				if self.state.isPlaying() == 1:
					self.controls.togglePlay()
					self.state.isPlaying(set=0)
				else:
					self.state.isPlaying(set=1)
					self.controls.togglePlay()
			#event.handled = True
			#return(event)

		# REC
		if event.data1 == revSoundButtons["record"]:
			if event.data2 == 127:
				if self.state.isRecording() == 1:
					self.state.isRecording(set=0)
				else:
					self.state.isRecording(set=1)
					self.controls.toggleRecord()
			#event.handled = True
			#return(event)

		#knobs
		if event.data1 >= 0x30 and event.data1 <= 0x37:
			#print(f"key: {hex(event.data1)}	knob #: {event.data1-48}") 
			event = self.knobAdjust(event)
			#event.handled = True
			#return(event)

	def deviceInfo(self):
		print("Device Info:")
		print(" - getName:" + str(device.getName()))
		print(" - isAssigned:" + str(device.isAssigned()))
		
		# deviceID Data Map
		self.dIdMap = [None] * 29
		self.dIdMap[0] = "Manu. ID" # 0x47
		self.dIdMap[1] = "Prod. ID" # 0x4E
		self.dIdMap[2] = "Bytes Start" # 0x00
		self.dIdMap[3] = "Bytes End" # 0x19
		self.dIdMap[4] = "<Version>"
		self.dIdMap[5:7] = "xxx"
		self.dIdMap[8] = "<DeviceID>"
		self.dIdMap[9] = "<Serial>"
		self.dIdMap[10:12] = "xxx"
		self.dIdMap[13] = "<Manufacturing>"
		self.dIdMap[14:28] = "xxxxxxxxxxxxxxx"

		self.parseDevID()

	def parseDevID(self):
		mmcOffset = 5
		print(" - Raw Device ID:")
		for idx,c in enumerate(device.getDeviceID()):
			print(f"  - {idx:02d}/{idx+1+mmcOffset:02d}: {self.dIdMap[idx]:>15}: (x){c}") # (d){c:02X}

	def sendMessage(self, command, key, value):
		device.midiOutMsg(command + (key << 8) + (value << 16))  

# Our transport class
class TransportHandler():
	def __init__(self, state):
		self.state = state
		self.state.getStates()

	def toggleLoopMode(self):
		if (transport.isPlaying() == 0): #Only toggle loop mode if not already playing
			transport.setLoopMode()
			print("Song/Pattern Mode toggled")
			
	def pressFastForward(self):
		transport.fastForward(2)
		#ledCtrl = LedControl()
		#ledCtrl.setLedMono(note, False)
	 	#print("FastForward on")

	def pressRewind(self):
		transport.rewind(2)
		#ledCtrl = LedControl()
		#ledCtrl.setLedMono(note, False)
		#print("Rewind on")
  
	def togglePlay(self):
		if (transport.isPlaying() == 0):
			transport.start()
			self.state.isPlaying(set=1)
		elif (transport.isPlaying() == 1):
			transport.stop()
			self.state.isPlaying(set=0)
		#print("isPlaying: " + str(transport.isPlaying()))

	def toggleRecord(self):
		if (transport.isPlaying() == 0): # Only enable recording if not already playing
			transport.record()
			if self.state.isRecording():
				self.state.isRecording(set=1)
			else:
				self.state.isRecording(set=0)
			print(f"Toggled recording: {self.state.isRecording()}")
		else:
			self.state.isRecording(set=0)
			print("Currently Playing; Canceled Record Command")

class PadLighting():
	def __init__(self, midiHandler, state):
		self.midiHander = midiHandler
		self.state = state		
  
		self.initialDim = revPadLEDFunction["bright_2"]
		self.initialColor = 0x02 # a bright white/grey or something
		time.sleep(1)
		
		print("turning pads on.")
		print("sleeping and testing")
		time.sleep(3)
		self.all_pads_on(speed=0.01)
		#self.self_test()
		#time.sleep(1)
		self.animate_pads_on()
		self.all_pads_dim(self.initialColor, speed=0.05)
		
		print("turning on all other buttons.")
		self.all_funcs_on()
	
	def cycle_pads(self, command, value, speed=0.05):
		for a in range(padIdStart, padIdEnd):
			#midiHandler.sendMessage([command, a, value])
			device.midiOutMsg(command + (a << 8) + (value << 16))
			time.sleep(speed)

	def self_test(self, speed=0.05):
		# Cycle through each button color function for every button
		for key, value in padLEDFunction.items():
			self.cycle_pads(key, 0x02, speed=speed)

	def all_funcs_on(self):
		for key, value in trackButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x01)
		
		for key, value in sceneButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x01)
			
	def all_funcs_off(self):
		for key, value in trackButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x00)
		
		for key, value in sceneButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x00)

	def all_funcs_flash(self):
		for key, value in trackButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x02)
			
		for key, value in sceneButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x02)
		
	def all_funcs_stop_flash(self):
		for key, value in trackButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x01)
			
		for key, value in sceneButtons.items():
			midiHandler.sendMessage(revPadLEDFunction["bright_0"], key, 0x01)

	def all_pads_on(self, speed=0.05):
		print("Turning all buttons on.")
		# no bright, no color
		self.cycle_pads(revPadLEDFunction["bright_0"], 0x00, speed=speed)
		
	def animate_pads_on(self, speed=0.1):
		for row in startPattern:
			for key in row:
				midiHandler.sendMessage(revPadLEDFunction["bright_5"], key, 0x05)
				time.sleep(0.02)
				
	def animate_pads_off(self, speed=0.1):
		for row in startPattern:
			for key in row:
				midiHandler.sendMessage(revPadLEDFunction["bright_5"], key, 0x22)
				time.sleep(0.02)

	def all_pads_off(self, speed=0.05):
		# no bright, no color
		print("Turning all buttons off.")
		self.cycle_pads(revPadLEDFunction["bright_0"], 0x00, speed=speed)
		
	def all_pads_dim(self, color, speed=0.05):
		print("All buttons dim.")
		self.cycle_pads(self.initialDim, color, speed=speed)

	def pad_color(self, key, color):
		midiHandler.sendMessage([revPadLEDFunction["bright_4"]], key, color)

	def pad_pressed(self, key):
		midiHandler.sendMessage([revPadLEDFunction["bright_4"], key, 10])
		#print("pad pressed")
	
	def pad_unpressed(self, key):
		midiHandler.sendMessage([self.initialDim, key, self.initialColor])
		#print("pad unpressed")

	# def sendMessage(self, command, key, value):
	def pad_led_on(self, mode, key, color):
		midiHandler.sendMessage(mode, key, color)
		#print("pad on")
	
	def pad_led_off(self, key):
		midiHandler.sendMessage(self.initialDim, key, self.initialColor)
		#print("pad off")


class PerformanceMode:
	def __init__(self, lighting, state):
		self.lighting = lighting
		self.state = state

		self.pos = []
		self.pos.append([0])
		self.pos.append([32,33,34,35,36,37,38,39])
		self.pos.append([24,25,26,27,28,29,30,31])
		self.pos.append([16,17,18,19,20,21,22,23])
		self.pos.append([8,  9,10,11,12,13,14,15])
		self.pos.append([0,  1, 2, 3, 4, 5, 6, 7])

		# If script restart, this should update the LEDs
		self.OnUpdateLiveMode(0)

	def debugLiveMode(self, value):
		print(f"-----------------------------------------------")
		print(" Patterns")
		num = patterns.patternNumber()
		print(f"patternMax: {patterns.patternMax()}")
		print(f"patternCount: {patterns.patternCount()}")
		print(f"(selected) patternNumber: {num}")
		print(f"(selected) getPatternName: {patterns.getPatternName(num)}")
		print(f"(selected) getPatternLength: {patterns.getPatternLength(num)}")
		print(f"(selected) isPatternSelected {patterns.isPatternSelected(num)}")
		print(f"(selected) getPatternName: {patterns.getPatternName(num)}")
		print(f"(selected) getPatternColor: {hex(patterns.getPatternColor(num)& 0xffffffff)}")

		for a in range(1, 10):
			print(f"{a}.0.getLiveStatus: {str(playlist.getLiveStatus(a,0))}")
			print(f"{a}.1.getLiveStatus: {str(playlist.getLiveStatus(a,1))}")
		print("-----------------------------------------------")
		print(" Tracks")
		trackNum = 1
		print(f"isTrackSelected: {playlist.isTrackSelected(trackNum)}")
		print(f"trackCount: {int(playlist.trackCount())}")
		print(f"getTrackName: {playlist.getTrackName(trackNum)}")
		print(f"getLiveLoopMode: {playlist.getLiveLoopMode(trackNum)}")
		print(f"getLiveTriggerMode: {playlist.getLiveTriggerMode(trackNum)}")
		print(f"getLivePosSnap: {playlist.getLivePosSnap(trackNum)}")
		print(f"getLiveTrigSnap: {playlist.getLiveTrigSnap(trackNum)}")

	def OnUpdateLiveMode(self, value):
		if self.state.perfFirstRun == True:
			self.state.perfFirstRun(set=False)
			print("Performance Mode Init!")

		self.debugLiveMode(value)

		# idx      = top -> bottom
		# blocknum = left -> right
		for idx in range(1, 6):
			for blockNum in range(0, 8):
				active = playlist.getLiveBlockStatus(idx,blockNum,0)
				#print(f"{idx}.{blockNum}.0.getLiveBlockStatus: {playlist.getLiveBlockStatus(idx,blockNum,0)}")
				if active:
					#print(f"{idx},{blockNum},{self.pos[idx][blockNum]}")
					# def sendMessage(self, command, key, value):
					if active == 7:
						self.lighting.pad_led_on(revPadLEDFunction["bright_4"], self.pos[idx][blockNum], 6)
						print(f"getLiveBlockColor1: {hex(playlist.getLiveBlockColor(idx,blockNum) & 0xffffffff)}")
					else:
						self.lighting.pad_led_on(revPadLEDFunction["bright_4"], self.pos[idx][blockNum], 1)
						print(f"getLiveBlockColor2: {hex(playlist.getLiveBlockColor(idx,blockNum) & 0xffffffff)}")
				else:
					self.lighting.pad_led_off(self.pos[idx][blockNum])
					#print(f"getLiveBlockColor3: {playlist.getLiveBlockColor(idx,blockNum)& 0xffffffff}")
				#print(f"{idx}.{blockNum}.1.getLiveBlockStatus:", playlist.getLiveBlockStatus(idx,blockNum,1))
				#print(f"{idx}.{blockNum}.2.getLiveBlockStatus:", playlist.getLiveBlockStatus(idx,blockNum,2))
		
		#print(f"getLiveBlockColor3: {playlist.getLiveBlockColor(1,0) & 0xffffffff}")
		print(f"OnUpdateLiveMode: {value} changed")

class MidiMessaging():
	def sendMessage(self, command, key, value):
		device.midiOutMsg((command) + (key << 8) + (value << 16))

start = InitClass()
midiHandler = MidiMessaging()
state = State()
controls = TransportHandler(state)
lighting = PadLighting(midiHandler, state)
kbd = DeviceHandler(midiHandler, controls, lighting, state)
live = PerformanceMode(lighting, state)

def OnUpdateLiveMode(event):
	print("!!PERFMODE UPDATE!!")
	live.OnUpdateLiveMode(event)

def OnControlChange(event):
	pass
	#print(f"OnControlChange: {event.data1} {event.data2}")

def OnMidiMsg(event):
	if state.isPerformance():
		event = kbd.eventHandler(event)
		print(f"** onMidiMsg: fired")
	#event = kbd.eventHandler(event)

def OnMidiIn(event):
	#print(f"** onMidiIn: fired")
	if not state.isPerformance():
		event = kbd.eventHandler(event)
	#print(f"onMidiIn: {event}")
	#return(event)

def OnMidiOutMsg(event):
	pass
	#print(f"onMidiOutMsg: {event}")

def OnSysEx(event):
	print(f"** onSysEx: {event}")

def OnInit():
	print("onInit")
	
def OnDeInit():
	print("killing self. bang.")
	lighting.all_funcs_off()
	lighting.animate_pads_off()