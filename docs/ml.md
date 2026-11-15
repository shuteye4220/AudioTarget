# Machine learning for targets without a printed card

The printed card is the most precise and reliable target, but you won't always
have one: plain paper bullseyes, steel plates and spinners are common. The
"card, then machine learning" target type uses the card when it's there and
falls back to an ML model for anything else.

## What's built

- **Target type `card_ml`**: corner markers first, then bullseye rings, then
  the ML model. Type `onnx` uses the model only.
- **Zero-shot model:** YOLOE takes plain-English prompts ("bullseye", "shooting
  target", "round steel target") and finds those things with **no training**.
  `pi/tools/export_model.py` makes the model file on a PC.
- **Detect slowly, track quickly:** the model runs in a background thread on
  the newest frame, a few times a second. When it finds the target, a small
  picture of it becomes a template, and fast image matching follows that
  template in every frame until the model's next answer refreshes it. If the
  match gets poor, the track is dropped rather than guessed.
- **Aim-centred search:** you're pointing roughly at the target, so the model
  looks at a full-resolution square in the middle of the frame. That keeps
  far, small targets visible instead of shrinking the whole frame. Every fourth
  try looks at the whole frame instead, for targets that are near or off-centre.
  A hit that's cut off by the square's edge is thrown away, because its centre
  would be wrong.
- Any other YOLO detector works too (YOLOv8, YOLO11 or YOLO26, including
  "end-to-end" exports), if you train one on your own targets.

## Measured (simulated frames, plain bullseye with no markers)

The tests rendered a 200 mm card with the markers blanked out, so only the
rings and the ML model could find it. They added sensor noise, moved the
target slowly, and ran the camera at 30 frames per second. The model was
YOLOE-26n, zero-shot, 320 input, minimum score 0.25.

| Camera | 3 m | 10 m | 20 m |
|---|---|---|---|
| 1280 x 720, 22° lens | every frame, rings | 58 of 60 frames, within 1.5 px | not found |
| 1920 x 1080, 14° lens | every frame, rings | every frame, rings | 59 of 60 frames, within 1.3 px |

For comparison, the ring detector alone stops at about 5 m with the 22° lens
and 15 m with the 14° lens (docs/range.md). So on plain bullseyes the model
roughly doubles the range. Lowering the minimum score to 0.15 found the 20 m
target on the 720p setup too, at the cost of more false alarms in a real scene.

**These are simulated scenes with plain backgrounds.** Real ranges with grass,
backstops, other targets and changing light will be harder. Expect to tune
`onnx_conf`, and expect the zero-shot model to sometimes lock onto the wrong
round thing. That's why it's a fallback and the card stays the default.

## Speed on the Pi

Ultralytics' own Pi 5 benchmarks put YOLO26n at about 128 ms per frame at 640
input (about 7.8 per second) with ONNX. A 320 input is about a quarter of the
work. I estimate the 320 YOLOE-26n model here at roughly 10 to 20 detections
per second on a Pi 5. I measured 54 ms per detection on the build machine's
x86 CPU, so treat that as a ballpark figure until it's timed on a real Pi.

That's plenty, because tracking runs on every frame between detections. In the
tests the model ran only a handful of times across 60 frames, while nearly
every frame still had a fix.

A **Pi Zero 2 W** is several times slower than a Pi 5. Expect a detection
every second or so (unmeasured), with tracking in between. It's usable to pick
up a target, but slow to recover after losing one. The ML fallback is mainly a
Pi 5 feature.

## Accelerators, if CPU isn't enough

- **Raspberry Pi AI HAT+** (Hailo-8L 13 TOPS or Hailo-8 26 TOPS) and **AI HAT+ 2**
  (Hailo-10H, 40 TOPS INT4, 8 GB of its own memory, Pi 5 only). For vision models
  the AI HAT+ 2 performs about the same as the 26 TOPS AI HAT+; its extras are
  for running language models. For AudioTarget the original AI HAT+ would be
  the one to buy. Hailo models must be compiled with Hailo's tools on a PC, and
  the zero-shot YOLOE model probably won't compile, so this route needs a YOLO
  detector trained on your targets. It isn't implemented yet.
- **Raspberry Pi AI Camera** (Sony IMX500, about US$70): runs the model on the
  camera itself and works with a **Pi Zero 2 W**, which suits layout 2. Custom
  models need converting with Sony's toolkit, which people report is fiddly.
  It also has a fixed wide lens, which limits range. Worth revisiting later.

## Setting it up

1. On a PC (your Arch machine is fine; a GPU isn't needed for exporting):
   ```
   pip install ultralytics "git+https://github.com/ultralytics/CLIP.git"
   python3 pi/tools/export_model.py
   ```
   It prints the settings to use. To change what it looks for, add
   `--prompts "bullseye,steel plate,paper silhouette target"`.
2. Copy `targets.onnx` to `/var/lib/audiotarget/models/` on the Pi. The
   commands are at the top of `export_model.py`. The SD-card image's settings
   already point there, with a 320 input and classes 0 to 2.
3. In the spoken menu: Camera, then Target type, then "Printed card, then
   machine learning for other targets".
4. To check it, use the menu's "Follow the target" while aiming at a plain
   target.

## Licensing

Ultralytics models and weights, YOLOE included, are AGPL-3.0. The model file
you export is covered by that, not by this repo's MIT license, so it isn't
shipped in the SD-card image. AudioTarget only loads the exported `.onnx` file;
it doesn't use the Ultralytics library on the Pi.

## Next steps worth doing

- **Teach it your own targets:** add a menu item that saves camera frames while
  you aim at a target, auto-labels them with the zero-shot model and the ring
  detector, and trains a small YOLO26n on your PC's GTX 1660 Super. A model
  trained on your own targets should be faster and more confident than zero-shot.
- **Hailo support** for that trained model on a Pi 5 with an AI HAT+.
