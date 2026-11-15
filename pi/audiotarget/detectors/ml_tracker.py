"""Detect slowly, track quickly.

An ML model on a Pi CPU manages a few frames per second; aiming needs every
frame. The model runs in a background thread on the latest frame; when it
finds the target, a small image patch around it becomes a template, and
normalised cross-correlation follows that patch in every frame until the next
model result refreshes it. If the match gets poor, the track is dropped
rather than guessed.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from . import Detection, Detector

MATCH_MIN = 0.6     # correlation needed to keep tracking
SEARCH_SCALE = 2.5  # search window size relative to the template
TEMPLATE_MIN, TEMPLATE_MAX = 16, 160


def _subpixel(res: np.ndarray, x: int, y: int) -> tuple[float, float]:
    """Parabolic peak refinement around (x, y) in a match-score map."""
    dx = dy = 0.0
    if 0 < x < res.shape[1] - 1:
        l, c, r = res[y, x - 1], res[y, x], res[y, x + 1]
        d = l - 2 * c + r
        dx = 0.5 * (l - r) / d if d != 0 else 0.0
    if 0 < y < res.shape[0] - 1:
        u, c, b = res[y - 1, x], res[y, x], res[y + 1, x]
        d = u - 2 * c + b
        dy = 0.5 * (u - b) / d if d != 0 else 0.0
    return x + float(np.clip(dx, -0.5, 0.5)), y + float(np.clip(dy, -0.5, 0.5))


class MlTracker:
    def __init__(self, detector: Detector, refresh_s: float = 0.5) -> None:
        self.detector = detector
        self.refresh_s = refresh_s
        self._lock = threading.Lock()
        self._job: np.ndarray | None = None
        self._result: tuple[np.ndarray, Detection | None] | None = None
        self._busy = False
        self._wake = threading.Event()
        self._last_submit = 0.0
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()
        self.reset()

    def reset(self) -> None:
        self.template: np.ndarray | None = None
        self.pos: tuple[float, float] | None = None
        self.size = 0.0
        self.range_m: float | None = None
        self.score = 0.0

    # ---------------------------------------------------------------- worker
    def _work(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                frame, self._job = self._job, None
            if frame is None:
                continue
            try:
                det = self.detector.detect(frame)
            except Exception:  # a bad model shouldn't kill tracking
                det = None
            with self._lock:
                self._result = (frame, det)
                self._busy = False

    def _submit(self, gray: np.ndarray, now: float) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True
            self._job = gray.copy()
        self._last_submit = now
        self._wake.set()

    # ---------------------------------------------------------------- tracking
    def _set_template(self, frame: np.ndarray, det: Detection) -> None:
        half = int(np.clip(det.size_px * 0.6, TEMPLATE_MIN, TEMPLATE_MAX))
        h, w = frame.shape[:2]
        x0, y0 = int(round(det.x)) - half, int(round(det.y)) - half
        if x0 < 0 or y0 < 0 or x0 + 2 * half > w or y0 + 2 * half > h:
            return  # too close to the edge to cut a clean patch
        self.template = frame[y0:y0 + 2 * half, x0:x0 + 2 * half].copy()
        self.pos = (det.x, det.y)
        self.size = det.size_px
        self.range_m = det.range_m

    def _track(self, gray: np.ndarray) -> Detection | None:
        th, tw = self.template.shape
        sh, sw = int(th * SEARCH_SCALE), int(tw * SEARCH_SCALE)
        h, w = gray.shape[:2]
        cx, cy = self.pos
        x0 = int(np.clip(cx - sw / 2, 0, max(0, w - sw)))
        y0 = int(np.clip(cy - sh / 2, 0, max(0, h - sh)))
        win = gray[y0:y0 + sh, x0:x0 + sw]
        if win.shape[0] < th or win.shape[1] < tw:
            return None
        res = cv2.matchTemplate(win, self.template, cv2.TM_CCOEFF_NORMED)
        _, best, _, (bx, by) = cv2.minMaxLoc(res)
        if best < MATCH_MIN:
            return None
        px, py = _subpixel(res, bx, by)
        self.pos = (x0 + px + tw / 2.0, y0 + py + th / 2.0)
        self.score = float(best)
        return Detection(self.pos[0], self.pos[1], self.size, self.range_m, self.score)

    def detect(self, gray: np.ndarray, origin: tuple[int, int] = (0, 0)) -> Detection | None:
        now = time.monotonic()
        with self._lock:
            result, self._result = self._result, None
        if result is not None:
            frame, det = result
            if det is not None:
                self._set_template(frame, det)
            elif self.template is None:
                self.reset()
        if self.template is None or now - self._last_submit >= self.refresh_s:
            self._submit(gray, now)
        if self.template is None:
            return None
        det = self._track(gray)
        if det is None:
            self.reset()
        return det
