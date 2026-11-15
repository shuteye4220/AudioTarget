"""Optional ML detector: a YOLO-style ONNX model run with OpenCV's DNN module.

Train a one-class detector on photos of your targets (for example with
Ultralytics YOLOv8n, exported with `format=onnx`), then point
detector.onnx_model at the .onnx file. Expect a few frames per second on a
Pi Zero 2 W and much more on a Pi 5; the ROI tracker helps either way.

The aim point is the centre of the detected box.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..config import DetectorCfg
from ..geometry import Intrinsics
from . import Detection


def letterbox(gray: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = gray.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((size, size), 114, np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    canvas[top:top + nh, left:left + nw] = resized
    return canvas, scale, left, top


def decode_yolov8(out: np.ndarray, class_id: int, conf: float) -> tuple[float, float, float, float, float] | None:
    """Best box for one class from a YOLOv8 output of shape (1, 4+nc, N).

    Returns (cx, cy, w, h, score) in network input pixels.
    """
    a = np.asarray(out)
    if a.ndim == 3:
        a = a[0]
    if a.shape[0] > a.shape[1]:  # some exports are (N, 4+nc)
        a = a.T
    if a.shape[0] < 5 or class_id + 4 >= a.shape[0]:
        return None
    scores = a[4 + class_id]
    i = int(np.argmax(scores))
    if not np.isfinite(scores[i]) or scores[i] < conf:
        return None
    cx, cy, w, h = (float(v) for v in a[:4, i])
    return cx, cy, w, h, float(scores[i])


class OnnxDetector:
    def __init__(self, cfg: DetectorCfg, intr: Intrinsics) -> None:
        self.net = cv2.dnn.readNetFromONNX(cfg.onnx_model)
        self.size = cfg.onnx_input
        self.class_id = cfg.onnx_class
        self.conf = cfg.onnx_conf
        self.width_mm = cfg.onnx_target_width_mm
        self.intr = intr

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        img, scale, left, top = letterbox(gray, self.size)
        blob = cv2.dnn.blobFromImage(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), 1 / 255.0,
                                     (self.size, self.size), swapRB=True)
        self.net.setInput(blob)
        best = decode_yolov8(self.net.forward(), self.class_id, self.conf)
        if best is None:
            return None
        cx, cy, w, h, score = best
        x = (cx - left) / scale + origin[0]
        y = (cy - top) / scale + origin[1]
        w_px = w / scale
        range_m = None
        if self.width_mm > 0 and w_px > 0:
            range_m = self.intr.fx * self.width_mm / w_px / 1000.0
        return Detection(x, y, max(w_px, h / scale), range_m, score)
