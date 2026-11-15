"""Camera backends. Both return (greyscale frame, capture time from time.monotonic())."""

from __future__ import annotations

import logging
import time
from typing import Protocol

import numpy as np

from .config import CameraCfg

log = logging.getLogger(__name__)


class Camera(Protocol):
    width: int
    height: int

    def read(self) -> tuple[np.ndarray, float]: ...
    def close(self) -> None: ...


class Picamera2Camera:
    """Raspberry Pi camera on the ribbon cable (Camera Module 3, HQ, etc.)."""

    def __init__(self, cfg: CameraCfg) -> None:
        from picamera2 import Picamera2  # installed from apt: python3-picamera2

        self.cam = Picamera2()
        frame_us = int(1_000_000 / cfg.fps)
        conf = self.cam.create_video_configuration(
            main={"size": (cfg.width, cfg.height), "format": "YUV420"},
            controls={"FrameDurationLimits": (frame_us, frame_us)},
            buffer_count=3,
        )
        self.cam.configure(conf)
        self.cam.start()
        self.width, self.height = cfg.width, cfg.height
        self.rotate = cfg.rotate_180

    def read(self) -> tuple[np.ndarray, float]:
        yuv = self.cam.capture_array("main")
        t = time.monotonic()
        gray = yuv[: self.height, : self.width]  # the Y plane is the greyscale image
        if self.rotate:
            gray = gray[::-1, ::-1]
        return np.ascontiguousarray(gray), t

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()


class V4L2Camera:
    """USB (UVC) camera, e.g. a narrow-lens module on the gun cabled to a belt Pi."""

    def __init__(self, cfg: CameraCfg) -> None:
        import cv2

        dev: int | str = int(cfg.device) if cfg.device.isdigit() else cfg.device
        self.cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open camera {cfg.device}")
        # MJPEG lets most USB cameras reach full frame rate over USB 2.
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        self.cap.set(cv2.CAP_PROP_FPS, cfg.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always the newest frame
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (self.width, self.height) != (cfg.width, cfg.height):
            log.warning("camera gave %dx%d instead of %dx%d", self.width, self.height,
                        cfg.width, cfg.height)
        self.rotate = cfg.rotate_180
        self._cv2 = cv2

    def read(self) -> tuple[np.ndarray, float]:
        ok, frame = self.cap.read()
        t = time.monotonic()
        if not ok or frame is None:
            raise RuntimeError("camera read failed")
        gray = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)
        if self.rotate:
            gray = gray[::-1, ::-1]
        return np.ascontiguousarray(gray), t

    def close(self) -> None:
        self.cap.release()


def open_camera(cfg: CameraCfg) -> Camera:
    if cfg.backend == "picamera2":
        return Picamera2Camera(cfg)
    return V4L2Camera(cfg)
