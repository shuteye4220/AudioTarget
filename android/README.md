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

Every push builds a debug APK on GitHub Actions: open the repository's
Actions tab, pick the latest CI run, and download the
`audiotarget-android-prototype` artifact (a zip containing the APK). Install
it from your file manager.

Each CI build is signed with a different throwaway key, so to install a newer
build, uninstall the old one first.

## Getting a model

The app needs an ONNX model. The same file works for the Pi:

```
pip install ultralytics "git+https://github.com/ultralytics/CLIP.git"
python3 pi/tools/export_model.py          # writes targets.onnx (YOLOE, zero-shot, 320 input)
```

Copy `targets.onnx` to the phone, then press **Load model** and pick it. The
app reads the model's class names, says what it's looking for, and keeps the
model for next time. Without a model, the app gives tilt-only guidance.

(You can also put `targets.onnx` in `android/app/src/main/assets/` before
building to bundle it. That folder is git-ignored, because the weights are
AGPL-licensed.)

## Using it

Hold the phone in landscape, camera facing the target, like a scope.

| Button | Does |
|---|---|
| Zero | Saves the current target position (and tilt) as "on target" |
| Where is the target | Says where the target is, for example "Target 1.2 degrees right, level" |
| Mute / Unmute | Silences the guidance tone |
| Zoom | 1x, 2x, 5x (the Pixel 10's telephoto lens), 10x. Narrower zoom = longer range |
| Model speed | Phone speed / like a Pi 5 (10 a second) / like a Pi Zero 2 W (1 a second) |
| Tracking between detections | On: correlation tracking fills every frame. Off: model answers only |
| Semitone step | 0.05, 0.1, 0.2 or 0.5 degrees per semitone |
| Minimum score | How sure the model must be: 0.15, 0.25 or 0.4 |
| Status | Camera frame rate, zoom, field of view, model time per detection and detections per second |
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
