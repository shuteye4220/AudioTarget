#!/usr/bin/env python3
"""Make an ML target model for AudioTarget. Run this on a PC, not the Pi.

Default: zero-shot YOLOE told in words what to look for. No training needed.

    pip install ultralytics "git+https://github.com/ultralytics/CLIP.git"
    python3 export_model.py                       # -> targets.onnx
    python3 export_model.py --prompts "bullseye,steel plate,paper silhouette target"
    python3 export_model.py --weights my_trained.pt   # your own trained detector

Copy the result to the Pi, e.g.:
    scp targets.onnx YOURUSER@PI:/tmp/ && ssh YOURUSER@PI \
      'sudo install -o audiotarget -m 600 /tmp/targets.onnx /var/lib/audiotarget/models/'
then choose "Printed card, then machine learning" in the menu (Camera, Target type).

Note: Ultralytics models and weights are AGPL-3.0 licensed; this repo's MIT
license doesn't cover the model file you create.
"""

from __future__ import annotations

import argparse
import shutil
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompts", default="bullseye,shooting target,round steel target",
                    help="comma-separated things to find (YOLOE only)")
    ap.add_argument("--weights", default="yoloe-26n-seg.pt",
                    help="YOLOE weights (zero-shot) or your own trained YOLO .pt")
    ap.add_argument("--imgsz", type=int, default=320,
                    help="input size: 320 for speed (Pi 5 / Zero 2 W), 640 for bigger targets")
    ap.add_argument("-o", "--output", default="targets.onnx")
    a = ap.parse_args()
    if a.imgsz % 32 or not 160 <= a.imgsz <= 640:
        ap.error("--imgsz must be a multiple of 32 between 160 and 640")

    from ultralytics import YOLO, YOLOE

    if "yoloe" in a.weights.lower():
        names = [p.strip() for p in a.prompts.split(",") if p.strip()]
        model = YOLOE(a.weights)
        model.set_classes(names)
    else:
        model = YOLO(a.weights)
        names = list(model.names.values())
    path = model.export(format="onnx", imgsz=a.imgsz, simplify=True)
    shutil.move(path, a.output)
    classes = ",".join(str(i) for i in range(len(names)))
    print(f"\nwrote {a.output}; classes: {', '.join(f'{i}={n}' for i, n in enumerate(names))}")
    print("Settings for /var/lib/audiotarget/audiotarget.toml, under [detector]:")
    print(f'  onnx_model = "/var/lib/audiotarget/models/{a.output}"')
    print(f"  onnx_input = {a.imgsz}")
    print(f'  onnx_classes = "{classes}"')
    print("  onnx_conf = 0.25")
    return 0


if __name__ == "__main__":
    sys.exit(main())
