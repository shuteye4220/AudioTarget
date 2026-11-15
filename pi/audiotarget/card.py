"""Target card layout shared by the card generator and the ArUco detector.

Card frame: origin at the top-left corner, x to the right, y down, millimetres.
Four ArUco markers sit in the corners (IDs base+0..3: top-left, top-right,
bottom-right, bottom-left); the aim point is the card centre.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ARUCO_DICT = "DICT_4X4_50"


@dataclass(frozen=True)
class CardLayout:
    size_mm: float = 200.0
    marker_mm: float = 40.0
    margin_mm: float = 8.0
    id_base: int = 0

    @property
    def centre(self) -> tuple[float, float]:
        return self.size_mm / 2.0, self.size_mm / 2.0

    def marker_origin(self, index: int) -> tuple[float, float]:
        """Top-left corner of marker `index` (0=TL, 1=TR, 2=BR, 3=BL)."""
        near = self.margin_mm
        far = self.size_mm - self.margin_mm - self.marker_mm
        return [(near, near), (far, near), (far, far), (near, far)][index]

    def marker_corners(self, index: int) -> np.ndarray:
        """Corners in OpenCV's order (TL, TR, BR, BL), shape (4, 2), mm."""
        x, y = self.marker_origin(index)
        s = self.marker_mm
        return np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float64)

    def ids(self) -> range:
        return range(self.id_base, self.id_base + 4)


def aruco_dictionary():
    import cv2

    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICT))


def marker_bits(marker_id: int, pixels: int = 6) -> np.ndarray:
    """Marker image (0 = black, 255 = white) including its black border."""
    import cv2

    d = aruco_dictionary()
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(d, marker_id, pixels)
    return cv2.aruco.drawMarker(d, marker_id, pixels)  # OpenCV < 4.7
