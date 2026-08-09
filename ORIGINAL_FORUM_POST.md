Updated script from this post: viewtopic.php?f=1994&t=225886 // Martijn Tromp (aka tijnzor)

---> 3/8/2025 - V2 is here: https://github.com/derenma/APCKey25_FL <----

Script output is good for debugging or seeing if there is a code failure! (FL Studio -> View -> Script Output) There is a quite a bit of debugging notes and output from the FL Studio python hooks. Most of it is pointless to the end user and is intended to help me make bits of this script portable to other devices.

*********
OLD Source: https://github.com/derenma/FLSKEY25
Original Source: https://github.com/tijnzor/FLSKEY25

--------------

3/8/2025

I have done nearly a complete rewrite as the original script was a bit overpowered for what it was. (It was just fine, btw. One or two original lines remain, so tijnzor still gets credit for doing the brunt of the work in the OG code.)

Read the most recent posts of mine for configuration clarification.

When the script initializes, all the lights should turn on and do a simple animation. The pattern is in the code in one array, so feel free to f* with it and customize the gfx.

I have more ideas about functionality, so there is extra code that isn't used in this release and it's mainly around matching pad colors to the pattern colors in performance mode. (The default color palette for the APCKEY25 does not align with the color scheme in FL Studio and I ain't mapping that shit manually. I have tried a couple of hacks to align the colors programmatically, but it really isn't worth the time.) There are dangling arrays that have mapping to the "soft keys" but isn't used, yet. (I need to write the code to track the state of each of the soft keys and have been putting that off.)

Row and Column buttons (the red and green ones below and to the right of the pads are only turned on for show) They will be useful for enabling / disabling rows of instruments in performance mode, or even scrolling around the "grid" of patterns like with the Akai Fire, as well as using them for what they were intended for, as noted by their respective text on the device.

Side note: This really is a good device and minus a few quirks, should have been formally adapted for FL Studio as well as Ableton.

Known "bug": The lights will periodically flash super quick. I suspect this is a hardware issue with the device itself when it performs some kind of "led status refresh". This is likely caused by code in an internal MCU or if the LED driver wasn't decoupled properly. I need to pull out my oscilloscope and finally crack this thing open to debug this particular problem. I suspect I can "buffer" the LED power with a chonky capacitor on its power rail, but that may cause other LEDs to fade ON and fade OFF, which is even more annoying.

ORIGINAL POST BELOW - Mostly outdated..

--------------
========
Hi!

I have been making significant changes to Martjn's original script to support Performance Mode in FL Studio. Me, like the dumbass that I am, didn't check to see if this midi controller was for FL Studio or not when I ordered it. So, I am just making it work.

** I am brand new to using midi controllers so I really don't know the entire scope of their use yet!
** Any feedback on functionality is welcomed and its THE reason I released this script in an early stage.

--------------

Important notes:
- Pad rows are now turned off by respective SoftKey for pad row (This actually restricts changing the mode of the keyboard, lulz. I'll think of a fix for this)
- This is still kind of a hacky script, but it works for what we need it for. (Code cleanup later!)
- Using the same script for handling the keys should be easy, but just keep them using the "generic keyboard" settings for now.
- Since I am new to FL Studio scripting, it took me longer than it should to figure out that the script location for windows was in the Documents directory. (Screenshot attached.)
- I'll change the colors of the pads later. For now, active ones in performance are bright, inactive ones are dim. (This is based on the play state of the pattern/sample and NOT when you hit the pad.)
- Not all of the variables at the start of the script do what they say they do. (Some are just artifacts and will be cleaned out later)
- LED Pad numbers !== Note numbers! (That is really silly.) I had to create two mappings: One for fast(er) LED updates; Another for mapping notes to their respective position in performance mode.

The pad note numbers have a super weird offset, btw. I suspect the note mapping is an artifact to handle on-off.

Mapping is as follows:

"Real" LED Map
32,33,34,35,36,37,38,39
24,25,26,27,28,29,30,31
16,17,18,19,20,21,22,23
08,09,10,11,12,13,14,15
00,01,02,03,04,05,06,07

Mapping for performance mode
Off - 08
00,01,02,03,04,05,06,07
Off - 20
12,13,14,15,16,17,18,19
Off - 32
24,25,26,27,28,29,30,31
Off - 44
36,37,38,39,40,41,42,43
Off - 56
48,49,50,51,52,53,54,55

Change log:
Author: Martijn Tromp // Matt Deren
Changelog:
23/04/2020 0.01: Implement Play/Pause Button (AKFSM-2)
23/04/2020 0.02: Clean up code and handle Note Off
23/04/2020 0.03: Add Record and Pattern/Song toggle
24/04/2020 0.04: More refactoring, making it easier to map and implement new stuff.
02/05/2020 0.05: Implement stuff for calling LEDs on the controller. The played note gets passed to the method.
03/05/2020 0.06: Basic fast forward functionality using playback speed. Time in FL studio seems to be mismatched. Lights work. Mode switching now using shift modifier.
08/05/2020 0.07: fastForward/rewind implemented using transport.fastForward/transport.rewind kill LEDs when exiting FL Studio
--------------------
03/06/2024 0.10:
- Reworked most of the LED controls
- Added better knob control (no longer jumps from 1 to 127)
- Performance mode scripting added! (No color changing yet; LED's do turn on/off as expected.)
- Updating script will turn off pad leds until a change is made to the playlist
- Added mappings for LEDs as well as pad controls
03/07/2024 0.10:
- Fixed SoftKey LEDs
- SoftKeys now turn their row off in performance mode
- Starts in UserMode when the script is loaded by FL Studio (aka Performance Mode)
- Upbeat light moved to row below pads

TODO:
- Clean and refactor for brevity (It's still a wierd mix of two different scripts..)
- Map the rest of the controls
- There is a *ton* of debug/info lines in this code. Will remove after beta
- Controls to the right and bottom of the pads have NOT been mapped yet
- ??
- Profit?