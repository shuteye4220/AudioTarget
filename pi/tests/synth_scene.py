"""Render a target card into a synthetic camera frame at a known pose."""

from __future__ import annotations

import math

import cv2
import numpy as np

from audiotarget.card import CardLayout, marker_bits
from audiotarget.geometry import Intrinsics


def render_card(layout: CardLayout, px_per_mm: float = 4.0, bullseye_mm: float = 120.0) -> np.ndarray:
    n = int(round(layout.size_mm * px_per_mm))
    img = np.full((n, n), 255, np.uint8)
    for i, mid in enumerate(layout.ids()):
        x, y = layout.marker_origin(i)
        s = int(round(layout.marker_mm * px_per_mm))
        m = cv2.resize(marker_bits(mid, 6), (s, s), interpolation=cv2.INTER_NEAREST)
        x0, y0 = int(round(x * px_per_mm)), int(round(y * px_per_mm))
        img[y0:y0 + s, x0:x0 + s] = m
    c = n / 2.0
    r_outer = bullseye_mm / 2.0 * px_per_mm
    for k in range(10):
        r = r_outer * (1 - k / 10)
        cv2.circle(img, (int(c), int(c)), int(round(r)), 0 if k % 2 == 0 else 255, -1, cv2.LINE_AA)
    return img


def place(card: np.ndarray, layout: CardLayout, intr: Intrinsics, *, range_m: float,
          az_deg: float, el_deg: float, yaw_deg: float = 0.0, noise: float = 0.0,
          seed: int = 0) -> tuple[np.ndarray, tuple[float, float]]:
    """Put the card's centre at (az, el) from the optical axis, `range_m` away,
    turned by yaw_deg about its vertical axis. Returns frame and the true
    centre pixel."""
    k = intr.camera_matrix()
    px_per_mm = card.shape[1] / layout.size_mm
    # Card centre position in camera coords (x right, y down, z forward), mm.
    az, el = math.radians(az_deg), math.radians(el_deg)
    d = range_m * 1000.0
    centre = np.array([d * math.cos(el) * math.sin(az), -d * math.sin(el),
                       d * math.cos(el) * math.cos(az)])
    yaw = math.radians(yaw_deg)
    rot = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
    half = layout.size_mm / 2.0
    corners_card = np.array([[-half, -half, 0], [half, -half, 0], [half, half, 0], [-half, half, 0]])
    cam_pts = (rot @ corners_card.T).T + centre
    img_pts = (k @ cam_pts.T).T
    img_pts = img_pts[:, :2] / img_pts[:, 2:3]
    src = np.array([[0, 0], [card.shape[1], 0], [card.shape[1], card.shape[0]], [0, card.shape[0]]],
                   np.float32)
    h = cv2.getPerspectiveTransform(src, img_pts.astype(np.float32))
    frame = np.full((intr.height, intr.width), 140, np.uint8)  # grey background
    warped = cv2.warpPerspective(card, h, (intr.width, intr.height), flags=cv2.INTER_AREA,
                                 borderMode=cv2.BORDER_TRANSPARENT, dst=frame)
    if noise > 0:
        rng = np.random.default_rng(seed)
        warped = np.clip(warped.astype(np.float32) + rng.normal(0, noise, warped.shape), 0, 255).astype(np.uint8)
    c = k @ centre
    true_px = (float(c[0] / c[2]), float(c[1] / c[2]))
    _ = px_per_mm
    return warped, true_px
