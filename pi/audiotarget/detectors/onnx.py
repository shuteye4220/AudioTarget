"""Optional ML detector: a YOLO-family ONNX model.

Works with:
- YOLOE / YOLO-World exported with text prompts baked in ("bullseye",
  "shooting target", ...): finds targets with no training at all
  (pi/tools/export_model.py makes one on a PC).
- Any YOLOv8 / YOLO11 / YOLO26 detector you trained on your own targets.

Both raw outputs (1, 4 + classes [+ mask coefficients], N) and end-to-end
outputs (1, N, 6) are understood. onnxruntime is used if installed (faster on
ARM); otherwise OpenCV's DNN module.

Speed matters on a Pi, so the model looks at a native-resolution square in the
middle of the frame first (you're aiming roughly at the target, and small far
targets survive), and only every few tries at the whole frame scaled down.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from ..config import DetectorCfg
from ..geometry import Intrinsics
from . import Detection

log = logging.getLogger(__name__)

FULL_FRAME_EVERY = 4  # every Nth search looks at the whole frame instead of the centre


def letterbox(gray: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = gray.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA) if scale != 1 else gray
    canvas = np.full((size, size), 114, np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, scale, left, top


def parse_classes(spec: str) -> list[int]:
    out = []
    for part in spec.replace(" ", "").split(","):
        if part:
            v = int(part)
            if not 0 <= v < 1000:
                raise ValueError("class ids must be 0..999")
            out.append(v)
    return out or [0]


def decode(out: np.ndarray, classes: list[int], conf: float) -> tuple[float, float, float, float, float] | None:
    """Best box among `classes` as (cx, cy, w, h, score) in network-input pixels.

    Raw YOLO output: (1, 4 + nc [+ 32 mask coefs], N) or its transpose (if nc > 2).
    End-to-end output (YOLOv10 / YOLO26 end2end): (1, N, 6) = x1 y1 x2 y2 score class.
    """
    a = np.asarray(out, dtype=np.float32)
    if a.ndim == 3:
        a = a[0]
    if a.ndim != 2 or a.size == 0:
        return None
    if a.shape[1] == 6 and a.shape[0] != 6:  # end-to-end
        keep = np.isin(a[:, 5].astype(int), classes) & (a[:, 4] >= conf)
        if not keep.any():
            return None
        r = a[keep][np.argmax(a[keep][:, 4])]
        x1, y1, x2, y2, score = (float(v) for v in r[:5])
        return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1, score
    if a.shape[0] > a.shape[1] and a.shape[1] > 6:  # candidates-first exports
        a = a.T
    rows = [4 + c for c in classes if 4 + c < a.shape[0]]
    if not rows:
        return None
    scores = a[rows].max(axis=0)
    i = int(np.argmax(scores))
    if not np.isfinite(scores[i]) or scores[i] < conf:
        return None
    cx, cy, w, h = (float(v) for v in a[:4, i])
    return cx, cy, w, h, float(scores[i])


class _Runner:
    def __init__(self, path: str) -> None:
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 3  # leave a core for the camera loop
            self.sess = ort.InferenceSession(path, opts, providers=["CPUExecutionProvider"])
            self.input = self.sess.get_inputs()[0].name
            self.net = None
            log.info("ML model on onnxruntime: %s", path)
        except ImportError:
            self.sess = None
            self.net = cv2.dnn.readNetFromONNX(path)
            log.info("ML model on OpenCV DNN: %s", path)

    def __call__(self, blob: np.ndarray) -> np.ndarray:
        if self.sess is not None:
            return self.sess.run(None, {self.input: blob})[0]
        self.net.setInput(blob)
        return self.net.forward()


class OnnxDetector:
    def __init__(self, cfg: DetectorCfg, intr: Intrinsics) -> None:
        self.run = _Runner(cfg.onnx_model)
        self.size = cfg.onnx_input
        self.classes = parse_classes(cfg.onnx_classes)
        self.conf = cfg.onnx_conf
        self.width_mm = cfg.onnx_target_width_mm
        self.intr = intr
        self.tries = 0

    def _infer(self, gray: np.ndarray):
        img, scale, left, top = letterbox(gray, self.size)
        rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        blob = rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        best = decode(self.run(blob), self.classes, self.conf)
        if best is None:
            return None
        cx, cy, w, h, score = best
        return (cx - left) / scale, (cy - top) / scale, w / scale, h / scale, score

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        h, w = gray.shape[:2]
        self.tries += 1
        crop = min(h, w) > self.size and self.tries % FULL_FRAME_EVERY != 0
        if crop:
            x0, y0 = (w - self.size) // 2, (h - self.size) // 2
            region = gray[y0:y0 + self.size, x0:x0 + self.size]
        else:
            x0, y0, region = 0, 0, gray
        r = self._infer(region)
        if r is None:
            return None
        x, y, bw, bh, score = r
        if crop and (x - bw / 2 < 2 or y - bh / 2 < 2 or x + bw / 2 > self.size - 2
                     or y + bh / 2 > self.size - 2):
            # Cut off by the crop edge (target bigger than the crop, or off to one
            # side): its centre would be wrong. Look at the whole frame next time.
            self.tries = FULL_FRAME_EVERY - 1
            return None
        range_m = None
        if self.width_mm > 0 and bw > 0:
            range_m = self.intr.fx * self.width_mm / bw / 1000.0
        return Detection(x + x0 + origin[0], y + y0 + origin[1], max(bw, bh), range_m, score)
