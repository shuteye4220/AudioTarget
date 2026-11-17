# AudioTarget phone prototype

An Android app that shows how the Pi 5's ML target fallback would behave,
using only a phone. The phone's camera stands in for the gun camera, an ML
model finds the target, and the phone plays the same guidance tone as the gun
module:

- **Pitch** = high or low. A440 is on target; each semitone up or down is
  0.1 degree high or low (adjustable).
- **Louder ear** = the side the target is on.
- **Slow beeping** = the model can't see a target. Pitch then follows the
  phone's tilt, like the gun module's tilt-only mode.
- **Fast flutter** = the phone is tipped sideways more than 2 degrees from
  where you zeroed.

Pitch and ear balance work like the gun module: higher pitch means you're
aiming high, and the louder ear is the side the target is on. That needs stereo
earphones; bone-conduction headsets like the Suunto Wing are stereo.

It runs the same "detect slowly, track quickly" design as the Pi. Set
"Model speed" to "like a Pi 5" or "like a Pi Zero 2 W" to hear how a slower
board would feel. Turn "Tracking between detections" off to hear the
difference tracking makes.

It needs no Google Play services, so it runs on GrapheneOS.

## Getting the app

Download the latest build directly:

https://github.com/shuteye4220/AudioTarget/releases/download/android-latest/audiotarget-phone.apk

Open it from the phone's Downloads to install. You'll need to allow installing
apps from your browser or file manager the first time.

Every change to the app on `main` rebuilds that file at the same address. All
builds are signed with the same key, so a new one installs over the old one
and keeps your settings. That key is committed to the repo on purpose: fine for
a prototype that only uses the camera and has no internet permission, but not
something to reuse for an app you'd publish.

## What it looks for

**The printed card first.** Print `targets/audiotarget-card-letter.pdf` (or the
A4 one). When the card is in view, the app finds it from its four corner
markers. That's more precise than object detection, and it knows the distance.
When the card isn't in view, the object model takes over.

**Ring callouts:** on the card, the app works out where your aim point falls
on the paper and says the area:

- bull's eye: within 12 mm of the centre
- first, second, third and fourth ring: each 12 mm wide, going outward
- on the card, outside the rings
- off the card

Each comes with a direction from the centre, for example "second ring, high
left". The aim point is the middle of the picture until you zero, and wherever
the card's centre was when you pressed Zero after that. A callout comes when
the area changes and holds for a moment. "Where is the target" adds the
distance and the area, for example "Card 0.4 degrees right, level, 6 metres.
Aim point: first ring, right". The "Ring callouts" button turns them off.

Range: the corner markers need to be about 10 pixels across. At 1x that is
roughly 4 to 5 m; Zoom 5x (the Pixel 10's telephoto) reaches about 20 m.
The card needs even light, without glare on the markers, and must be flat.

**If it doesn't find the card:** press **Status**. It says how many of the
four corner markers it has seen in the last 2 seconds (any one is enough to
aim). "0 of 4" with the card in view means it can't read the markers: get
closer, zoom in, or improve the light. Then press **Save camera picture**:
it saves exactly what the detector sees to Pictures/AudioTarget, which you
can send in to find out why.

**Everyday objects too.** The APK also has a **built-in object model** (YOLO26n, trained on COCO, a set of 80
everyday object types). **Look for** chooses "the card, or any object" (the default), "the card only",
or, for that object only: a person, chair,
couch, bench, potted plant, bottle, cup, sports ball, backpack, suitcase, TV,
laptop, teddy bear, stop sign, fire hydrant or car. Big, plain objects like
chairs and suitcases make good practice targets. The model has no "head"
type; it finds whole people.

It always tells you what it's on:

- When it locks on: "Chair found".
- If it moves to a different kind of object and stays there for most of a
  second: "Now on person".
- When you zero: "Zeroed on chair".
- "Where is the target" names it too: "Chair 1.2 degrees right, level".
- "Target lost" when it can't see anything for a second.

That built-in model is Ultralytics' and is AGPL-3.0 licensed, so the APK as a
whole falls under AGPL-3.0. The app's own code here stays MIT.

## Using your own model instead

To find printed bullseyes, steel plates and similar, make a model:

```
pip install ultralytics "git+https://github.com/ultralytics/CLIP.git"
python3 pi/tools/export_model.py          # writes targets.onnx (YOLOE, zero-shot, 320 input)
```

Copy `targets.onnx` to the phone, press **Load model**, and pick it. The app
switches to it and remembers it. **Model** switches between the built-in
objects and your file. **Look for** then offers your model's own types.

## Using it

Hold the phone in landscape, camera facing the target, like a scope.

| Button | Does |
|---|---|
| Zero | Saves the current target position (and tilt) as "on target" |
| Where is the target | Says what and where, for example "Chair 1.2 degrees right, level" |
| Mute / Unmute | Silences the guidance tone |
| Look for | The card or any object, the card only, or one kind of object |
| Ring callouts | Say which ring the aim point is in (card only) |
| Camera | "USB if plugged in" (the default) or "phone" only |
| Zoom | 1x, 2x, 5x (the Pixel 10's telephoto lens), 10x. Narrower zoom = longer range |
| Model speed | Phone speed / like a Pi 5 (10 a second) / like a Pi Zero 2 W (1 a second) |
| Tracking between detections | On: correlation tracking fills every frame. Off: model answers only |
| Semitone step | 0.05, 0.1, 0.2 or 0.5 degrees per semitone |
| Minimum score | How sure the model must be: 0.15, 0.25 or 0.4 |
| Status | Card corners seen, camera frame rate, zoom, field of view, model time per detection and detections per second |
| Save camera picture | Saves what the detector sees to Pictures/AudioTarget, for diagnosing |
| Model | Built-in objects, or your own file |
| Detail | Auto, high (640 input, sees smaller and further things) or fast (320 input, about 4 times less work) |
| Load model | Pick a `.onnx` file |
| Volume keys as buttons | When on: volume up = Zero, volume down = Where is the target |
| Announcements | "Target found" / "Target lost" on or off |

With a screen reader running (Backtalk, TalkBack), announcements go through
the screen reader, in its own voice and at its own rate. Without one, the app
uses text-to-speech.

## USB cameras

With Camera on "USB if plugged in", the app switches to a USB camera as soon as
Android offers one to apps, and back to the phone's camera when it's unplugged.
It says which it's using. That suits a camera on the gun with the phone in your
pocket. In that setup the phone's own tilt says nothing about your aim, so tilt
guidance and the sideways-tilt flutter are off while the USB camera is in use.

**The catch:** Android only offers USB cameras to apps on phones whose makers
switched that on, and most phones haven't. Press Status: it says whether this
phone supports USB cameras. If yours doesn't, a USB camera would need the app
to carry its own USB camera driver (a UVC library). That's possible, but it's
a bigger job and works on some phones and not others.

## Other phones (Samsung and others)

The app should run on any phone with Android 10 or newer: Galaxy A and S
series, Pixels and others. Every release build is started on Android 10 and
Android 15 emulators first, and only published if it starts, loads the model,
runs it, and shows every button on screen.

- **Slower phones:** with Detail on "auto", the app times its first few
  detections. If the detailed model takes more than a quarter of a second, it
  says so, switches to the fast model and remembers that.
- **No telephoto:** zoom asks for 5x; a phone without a telephoto lens gives
  you as much digital zoom as it has. Aiming still works; range is shorter.
- **No gyroscope:** budget phones without a gravity sensor use a smoothed
  accelerometer for the tilt guidance instead.
- **Navigation bar:** on Android 15 and later (One UI 7), apps draw right to
  the screen edges. The app keeps its buttons clear of the navigation bar,
  status bar and camera cut-out.

## What it measures that the Pi can't yet

Press **Status** on the phone to hear real milliseconds per detection on the
Tensor G5. It's a lot faster than a Pi 5. Set Model speed to "like a Pi 5" to
get a realistic feel for the Pi.

## Limits of the prototype

- Field of view comes from the main camera's specs divided by the zoom, so
  angles at 5x and 10x are approximate. Zeroing makes the guidance relative
  anyway.
- There's no gun module link: everything happens on the phone.
- The CPU runs the model through ONNX Runtime with XNNPACK. The Tensor G5's
  TPU isn't used.
