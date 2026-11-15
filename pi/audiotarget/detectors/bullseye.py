"""Plain printed bullseye (concentric rings), no markers or ML needed.

Finds groups of nested ellipses that share a centre. Less robust than the
marker card in clutter or harsh light, but works with ordinary paper targets.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..config import DetectorCfg
from ..geometry import Intrinsics
from . import Detection

MIN_RINGS = 3       # ring edges needed to call it a bullseye
FIT_QUALITY = 0.85  # contour area / ellipse area
MAX_RADIAL_ERR = 0.12  # worst contour point distance from the ellipse, relative


class BullseyeDetector:
    def __init__(self, cfg: DetectorCfg, intr: Intrinsics) -> None:
        self.outer_mm = cfg.bullseye_outer_mm
        self.intr = intr
        self.prev: tuple[float, float] | None = None

    def _ellipses(self, gray: np.ndarray) -> list[tuple[float, float, float, float]]:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        min_area = max(30.0, gray.shape[0] * gray.shape[1] * 1e-5)
        out = []
        for c in contours:
            if len(c) < 12:
                continue
            area = cv2.contourArea(c)
            if area < min_area:
                continue
            (ex, ey), (a, b), ang = cv2.fitEllipse(c)
            major, minor = max(a, b), min(a, b)
            if minor <= 0 or major / minor > 2.5:
                continue
            ell_area = np.pi * a * b / 4.0
            if area / ell_area < FIT_QUALITY or area / ell_area > 1.0 / FIT_QUALITY:
                continue
            # Every contour point must lie close to the fitted ellipse (rejects squares).
            pts = c.reshape(-1, 2).astype(np.float64) - (ex, ey)
            t = np.radians(ang)
            u = pts[:, 0] * np.cos(t) + pts[:, 1] * np.sin(t)
            v = -pts[:, 0] * np.sin(t) + pts[:, 1] * np.cos(t)
            r = np.hypot(u / (a / 2.0), v / (b / 2.0))
            if np.max(np.abs(r - 1.0)) > MAX_RADIAL_ERR:
                continue
            out.append((ex, ey, major, minor))
        return out

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        ells = [(x + origin[0], y + origin[1], a, b) for x, y, a, b in self._ellipses(gray)]
        if len(ells) < MIN_RINGS:
            return None
        ells.sort(key=lambda e: e[2])
        best = None
        used = [False] * len(ells)
        for i, (x, y, maj, _mn) in enumerate(ells):
            if used[i]:
                continue
            group = [ells[i]]
            used[i] = True
            for j in range(i + 1, len(ells)):
                xj, yj, majj, _ = ells[j]
                # Same centre (within a fraction of the smallest ring) and actually larger.
                if not used[j] and np.hypot(xj - x, yj - y) < max(2.0, 0.15 * maj) and majj > maj * 1.05:
                    group.append(ells[j])
                    used[j] = True
            if len(group) < MIN_RINGS:
                continue
            gx = float(np.mean([g[0] for g in group]))
            gy = float(np.mean([g[1] for g in group]))
            outer = max(g[2] for g in group)
            score = len(group)
            if self.prev is not None:
                score -= np.hypot(gx - self.prev[0], gy - self.prev[1]) / max(outer, 1.0) * 0.5
            if best is None or score > best[0]:
                best = (score, gx, gy, outer, len(group))
        if best is None:
            return None
        _, gx, gy, outer, n = best
        self.prev = (gx, gy)
        range_m = None
        if self.outer_mm > 0 and outer > 0:
            range_m = self.intr.fx * self.outer_mm / outer / 1000.0
        return Detection(gx, gy, outer, range_m, score=float(n))
