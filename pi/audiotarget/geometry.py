"""Pixel <-> angle conversion for the gun camera."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class Intrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    dist: np.ndarray | None = None  # OpenCV distortion coefficients, optional

    @classmethod
    def from_hfov(cls, width: int, height: int, hfov_deg: float) -> "Intrinsics":
        """Approximate intrinsics from horizontal field of view (square pixels)."""
        if not (1.0 <= hfov_deg <= 170.0):
            raise ValueError("hfov_deg must be between 1 and 170")
        fx = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        return cls(width, height, fx, fx, width / 2.0, height / 2.0)

    @classmethod
    def from_file(cls, path: str) -> "Intrinsics":
        """Load an OpenCV calibration (npz with K, dist, width, height)."""
        with np.load(path, allow_pickle=False) as z:
            k = z["K"]
            return cls(int(z["width"]), int(z["height"]), float(k[0, 0]), float(k[1, 1]),
                       float(k[0, 2]), float(k[1, 2]), z["dist"].astype(np.float64))

    def scaled(self, width: int, height: int) -> "Intrinsics":
        """Same lens at a different capture resolution."""
        sx, sy = width / self.width, height / self.height
        return Intrinsics(width, height, self.fx * sx, self.fy * sy, self.cx * sx, self.cy * sy,
                          self.dist)

    def camera_matrix(self) -> np.ndarray:
        return np.array([[self.fx, 0, self.cx], [0, self.fy, self.cy], [0, 0, 1]], np.float64)

    def undistort_point(self, x: float, y: float) -> tuple[float, float]:
        if self.dist is None:
            return x, y
        import cv2

        pts = np.array([[[x, y]]], np.float64)
        out = cv2.undistortPoints(pts, self.camera_matrix(), self.dist, P=self.camera_matrix())
        return float(out[0, 0, 0]), float(out[0, 0, 1])

    def pixel_to_angles_mdeg(self, x: float, y: float) -> tuple[float, float]:
        """Angle of a pixel from the optical axis: (+right, +up) in millidegrees."""
        x, y = self.undistort_point(x, y)
        az = math.degrees(math.atan2(x - self.cx, self.fx)) * 1000.0
        el = math.degrees(math.atan2(self.cy - y, self.fy)) * 1000.0
        return az, el
