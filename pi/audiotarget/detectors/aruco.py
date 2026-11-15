"""Printed card with four ArUco markers: fast, robust to lighting, gives range."""

from __future__ import annotations

import cv2
import numpy as np

from ..card import CardLayout, aruco_dictionary
from ..config import DetectorCfg
from ..geometry import Intrinsics
from . import Detection


class ArucoDetector:
    def __init__(self, cfg: DetectorCfg, intr: Intrinsics) -> None:
        self.layout = CardLayout(cfg.card_size_mm, cfg.marker_size_mm, cfg.marker_margin_mm,
                                 cfg.marker_id_base)
        self.intr = intr
        d = aruco_dictionary()
        if hasattr(cv2.aruco, "ArucoDetector"):
            params = cv2.aruco.DetectorParameters()
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            det = cv2.aruco.ArucoDetector(d, params)
            self._detect = det.detectMarkers
        else:  # OpenCV < 4.7 (Debian/Raspberry Pi OS Bookworm ships 4.6)
            params = cv2.aruco.DetectorParameters_create()
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            self._detect = lambda img: cv2.aruco.detectMarkers(img, d, parameters=params)
        self._index = {mid: i for i, mid in enumerate(self.layout.ids())}

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        corners, ids, _ = self._detect(gray)
        if ids is None or len(ids) == 0:
            return None
        obj, img = [], []
        sizes = []
        for c, mid in zip(corners, ids.flatten()):
            idx = self._index.get(int(mid))
            if idx is None:
                continue
            obj.append(self.layout.marker_corners(idx))
            pts = c.reshape(4, 2).astype(np.float64) + np.array(origin, np.float64)
            img.append(pts)
            sizes.append(float(np.linalg.norm(pts[0] - pts[1])))
        if not obj:
            return None
        obj_pts = np.concatenate(obj)
        img_pts = np.concatenate(img)

        hmat, _ = cv2.findHomography(obj_pts, img_pts, 0)
        if hmat is None:
            return None
        cx, cy = self.layout.centre
        p = hmat @ np.array([cx, cy, 1.0])
        if abs(p[2]) < 1e-9:
            return None
        x, y = float(p[0] / p[2]), float(p[1] / p[2])

        # Range from a full pose solve.
        range_m = None
        obj3 = np.hstack([obj_pts, np.zeros((len(obj_pts), 1))])
        ok, _rvec, tvec = cv2.solvePnP(obj3, img_pts, self.intr.camera_matrix(),
                                       self.intr.dist, flags=cv2.SOLVEPNP_IPPE)
        if ok:
            range_m = float(np.linalg.norm(tvec)) / 1000.0

        marker_px = float(np.mean(sizes))
        card_px = marker_px * self.layout.size_mm / self.layout.marker_mm
        return Detection(x, y, card_px, range_m, score=len(obj) / 4.0)
