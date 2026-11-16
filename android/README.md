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

The APK has a **built-in object model** (YOLO26n, trained on COCO, a set of 80
everyday object types). Use **Look for** to pick: anything, a person, chair,
couch, bench, potted plant, bottle, cup, sports ball, backpack, suitcase, TV,
laptop, teddy bear, stop sign, fire hydrant or car. Big, plain objects like
chairs and suitcases make good practice targets. The model has no "head"
type; it finds whole people.

When it locks on, it says what it found ("Chair found"). "Where is the target"
also names it ("Chair 1.2 degrees right, level").

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
| Look for | Anything, or one kind of object |
| Zoom | 1x, 2x, 5x (the Pixel 10's telephoto lens), 10x. Narrower zoom = longer range |
| Model speed | Phone speed / like a Pi 5 (10 a second) / like a Pi Zero 2 W (1 a second) |
| Tracking between detections | On: correlation tracking fills every frame. Off: model answers only |
| Semitone step | 0.05, 0.1, 0.2 or 0.5 degrees per semitone |
| Minimum score | How sure the model must be: 0.15, 0.25 or 0.4 |
| Status | Camera frame rate, zoom, field of view, model time per detection and detections per second |
| Model | Built-in objects, or your own file |
| Load model | Pick a `.onnx` file |
| Volume keys as buttons | When on: volume up = Zero, volume down = Where is the target |
| Announcements | "Target found" / "Target lost" on or off |

With a screen reader running (Backtalk, TalkBack), announcements go through
the screen reader, in its own voice and at its own rate. Without one, the app
uses text-to-speech.

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
