import math

import numpy as np
import pytest

from audiotarget.card import CardLayout
from audiotarget.config import DetectorCfg
from audiotarget.detectors import RoiTracker
from audiotarget.detectors.aruco import ArucoDetector
from audiotarget.detectors.bullseye import BullseyeDetector
from audiotarget.detectors.onnx import decode, letterbox, parse_classes
from audiotarget.geometry import Intrinsics

from synth_scene import place, render_card

# A narrow lens, like an HQ camera with a 16 mm lens (~22 deg across) at 1280x720.
INTR = Intrinsics.from_hfov(1280, 720, 22.0)
LAYOUT = CardLayout()
CARD = render_card(LAYOUT, px_per_mm=4.0)


# Ranges stay inside what this lens/card can do (see docs/range.md).
@pytest.mark.parametrize("range_m,az,el,yaw", [
    (3.0, 0.0, 0.0, 0.0),
    (6.0, 2.0, -1.5, 20.0),
    (8.0, -4.0, 2.5, -30.0),
    (10.0, 1.0, 1.0, 10.0),
])
def test_aruco_angle_and_range(range_m, az, el, yaw):
    frame, true_px = place(CARD, LAYOUT, INTR, range_m=range_m, az_deg=az, el_deg=el,
                           yaw_deg=yaw, noise=3.0)
    det = ArucoDetector(DetectorCfg(), INTR).detect(frame)
    assert det is not None
    # Within half a pixel of the true centre, even with the card turned.
    assert math.hypot(det.x - true_px[0], det.y - true_px[1]) < 0.75
    az_m, el_m = INTR.pixel_to_angles_mdeg(det.x, det.y)
    assert abs(az_m - az * 1000) < 30 and abs(el_m - el * 1000) < 30
    assert det.range_m == pytest.approx(range_m, rel=0.05)


def test_aruco_partial_card_still_works():
    frame, true_px = place(CARD, LAYOUT, INTR, range_m=6.0, az_deg=0.5, el_deg=0.0)
    # Hide the right half of the card (two markers) behind something.
    frame[:, int(true_px[0]) + 5:] = 140
    det = ArucoDetector(DetectorCfg(), INTR).detect(frame)
    assert det is not None
    assert math.hypot(det.x - true_px[0], det.y - true_px[1]) < 1.5


def test_aruco_no_target():
    frame = np.full((720, 1280), 140, np.uint8)
    assert ArucoDetector(DetectorCfg(), INTR).detect(frame) is None


def test_roi_tracker_matches_full_frame():
    det_full = ArucoDetector(DetectorCfg(), INTR)
    tracker = RoiTracker(ArucoDetector(DetectorCfg(), INTR))
    for az in (1.0, 1.1, 1.2):
        frame, true_px = place(CARD, LAYOUT, INTR, range_m=8.0, az_deg=az, el_deg=-0.5)
        a = det_full.detect(frame)
        b = tracker.detect(frame)
        assert a is not None and b is not None
        assert math.hypot(a.x - b.x, a.y - b.y) < 0.05
        assert b.range_m == pytest.approx(a.range_m, rel=1e-3)
    assert tracker.last is not None


def test_bullseye():
    frame, true_px = place(CARD, LAYOUT, INTR, range_m=5.0, az_deg=-1.0, el_deg=0.8, noise=2.0)
    det = BullseyeDetector(DetectorCfg(), INTR).detect(frame)
    assert det is not None
    assert math.hypot(det.x - true_px[0], det.y - true_px[1]) < 1.5
    assert det.range_m == pytest.approx(5.0, rel=0.1)


def test_card_detector_falls_back_to_rings():
    from audiotarget.detectors import make_detector

    det = make_detector(DetectorCfg(type="card"), INTR)
    frame, true_px = place(CARD, LAYOUT, INTR, range_m=4.0, az_deg=0.3, el_deg=0.2)
    # Smudge all four markers: only the rings are left.
    for i in range(4):
        x, y = LAYOUT.marker_origin(i)
        cx, cy = true_px[0] + (x + 20 - 100) * INTR.fx / 4000, true_px[1] + (y + 20 - 100) * INTR.fy / 4000
        frame[int(cy) - 18:int(cy) + 18, int(cx) - 18:int(cx) + 18] = 255
    d = det.detect(frame)
    assert d is not None and math.hypot(d.x - true_px[0], d.y - true_px[1]) < 1.5


def test_angles_signs():
    az, el = INTR.pixel_to_angles_mdeg(INTR.cx + 100, INTR.cy - 50)
    assert az > 0 and el > 0
    assert INTR.pixel_to_angles_mdeg(INTR.cx, INTR.cy) == (0.0, 0.0)


def test_intrinsics_scaling():
    small = INTR.scaled(640, 360)
    a1 = INTR.pixel_to_angles_mdeg(900, 200)
    a2 = small.pixel_to_angles_mdeg(450, 100)
    assert a1 == pytest.approx(a2)


def test_yolo_decode_and_letterbox():
    out = np.zeros((1, 6, 10), np.float32)  # 2 classes, 10 candidates
    out[0, :4, 3] = [320, 300, 50, 40]
    out[0, 5, 3] = 0.9  # class 1
    out[0, 4, 7] = 0.95  # class 0 elsewhere
    out[0, :4, 7] = [100, 100, 10, 10]
    assert decode(out, [1], 0.5) == pytest.approx((320, 300, 50, 40, 0.9))
    assert decode(out, [1], 0.95) is None
    assert decode(out, [0, 1], 0.5)[:2] == pytest.approx((100, 100))  # best of either
    # YOLOE-seg style: 3 classes then 32 mask coefficients, which must be ignored
    seg = np.zeros((1, 4 + 3 + 32, 50), np.float32)
    seg[0, 4 + 3:, :] = 5.0  # big mask coefficients
    seg[0, :4, 9] = [10, 20, 30, 40]
    seg[0, 5, 9] = 0.7
    assert decode(seg, [0, 1, 2], 0.5) == pytest.approx((10, 20, 30, 40, 0.7))
    # End-to-end (YOLO26 / YOLOv10): N x [x1 y1 x2 y2 score class]
    e2e = np.zeros((1, 300, 6), np.float32)
    e2e[0, 4] = [100, 50, 140, 90, 0.8, 2]
    e2e[0, 5] = [0, 0, 10, 10, 0.9, 7]
    assert decode(e2e, [2], 0.5) == pytest.approx((120, 70, 40, 40, 0.8))
    assert decode(e2e, [3], 0.5) is None
    img = np.zeros((720, 1280), np.uint8)
    boxed, scale, left, top = letterbox(img, 640)
    assert boxed.shape == (640, 640) and scale == 0.5 and left == 0 and top == 140
    assert parse_classes("0, 2,5") == [0, 2, 5] and parse_classes("") == [0]


class SlowFake:
    """Stands in for an ML model: right answer, but slow."""

    def __init__(self, truth, delay=0.15):
        self.truth, self.delay, self.calls = truth, delay, 0

    def detect(self, gray, origin=(0, 0)):
        import time as _t
        from audiotarget.detectors import Detection
        self.calls += 1
        _t.sleep(self.delay)
        x, y = self.truth(gray)
        return Detection(x, y, 60.0, 9.0, 0.8)


def test_ml_tracker_follows_between_slow_detections():
    import time as _t
    from audiotarget.detectors.ml_tracker import MlTracker

    plain = CARD.copy()
    for i in range(4):  # no markers: only the ML path can find it
        x, y = LAYOUT.marker_origin(i)
        s = int(LAYOUT.marker_mm * 4)
        plain[int(y * 4):int(y * 4) + s, int(x * 4):int(x * 4) + s] = 255
    frames = []
    for k in range(40):
        f, t = place(plain, LAYOUT, INTR, range_m=6.0, az_deg=0.6 + 0.02 * k, el_deg=-0.3,
                     noise=2.0, seed=k)
        frames.append((f, t))
    truth_by_id = {id(f): t for f, t in frames}

    def truth(gray):  # the worker gets a copy; match by content
        for f, t in frames:
            if np.array_equal(f, gray):
                return t
        raise AssertionError("unknown frame")

    fake = SlowFake(truth)
    trk = MlTracker(fake, refresh_s=0.5)
    errs = []
    got = 0
    for f, t in frames:
        d = trk.detect(f)
        if d is not None:
            got += 1
            errs.append(math.hypot(d.x - t[0], d.y - t[1]))
        _t.sleep(0.03)  # ~30 fps camera
    assert fake.calls <= 6           # the model ran rarely...
    assert got >= 30                 # ...but almost every frame had a fix
    assert max(errs) < 1.5 and np.mean(errs) < 0.6
    assert truth_by_id  # silence unused


def test_ml_tracker_drops_lost_target():
    from audiotarget.detectors.ml_tracker import MlTracker

    frame, t = place(CARD, LAYOUT, INTR, range_m=6.0, az_deg=0.0, el_deg=0.0)
    trk = MlTracker(SlowFake(lambda g: t, delay=0.0), refresh_s=10.0)
    import time as _t
    for _ in range(20):
        if trk.detect(frame) is not None:
            break
        _t.sleep(0.02)
    assert trk.template is not None
    blank = np.full_like(frame, 140)
    assert trk.detect(blank) is None and trk.template is None
