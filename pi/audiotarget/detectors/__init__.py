"""Target detectors. All take a greyscale frame and return a Detection or None."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..config import DetectorCfg
from ..geometry import Intrinsics


@dataclass
class Detection:
    x: float           # aim point, pixels
    y: float
    size_px: float     # rough target size, used to size the search window
    range_m: float | None = None
    score: float = 1.0


class Detector(Protocol):
    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        """`gray` may be a crop; `origin` is its top-left in the full frame.
        Returned coordinates are always full-frame."""
        ...


class FirstOf:
    """Try detectors in order; first hit wins."""

    def __init__(self, *detectors: Detector) -> None:
        self.detectors = detectors

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        for d in self.detectors:
            det = d.detect(gray, origin)
            if det is not None:
                return det
        return None


def make_detector(cfg: DetectorCfg, intr: Intrinsics) -> Detector:
    if cfg.type == "card":
        # The printed card has both: markers are precise up close, the
        # bullseye rings are big enough to find further away.
        from .aruco import ArucoDetector
        from .bullseye import BullseyeDetector

        return FirstOf(ArucoDetector(cfg, intr), BullseyeDetector(cfg, intr))
    if cfg.type == "aruco":
        from .aruco import ArucoDetector

        return ArucoDetector(cfg, intr)
    if cfg.type == "bullseye":
        from .bullseye import BullseyeDetector

        return BullseyeDetector(cfg, intr)
    if cfg.type == "onnx":
        from .onnx import OnnxDetector

        return OnnxDetector(cfg, intr)
    raise ValueError(f"unknown detector {cfg.type}")


class RoiTracker:
    """Search a window around the last hit first: much faster on a Pi Zero.

    Falls back to the full frame when the target isn't in the window.
    """

    def __init__(self, detector: Detector, scale: float = 3.0, min_px: int = 160) -> None:
        self.detector = detector
        self.scale = scale
        self.min_px = min_px
        self.last: Detection | None = None

    def detect(self, gray: np.ndarray) -> Detection | None:
        if self.last is not None:
            h, w = gray.shape[:2]
            half = max(self.min_px, self.last.size_px * self.scale) / 2.0
            x0 = int(max(0, self.last.x - half))
            y0 = int(max(0, self.last.y - half))
            x1 = int(min(w, self.last.x + half))
            y1 = int(min(h, self.last.y + half))
            if x1 - x0 >= 32 and y1 - y0 >= 32:
                det = self.detector.detect(gray[y0:y1, x0:x1], (x0, y0))
                if det is not None:
                    self.last = det
                    return det
        det = self.detector.detect(gray)
        self.last = det
        return det
