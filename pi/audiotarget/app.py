"""Main service: camera -> detector -> angles -> gun module; tones -> speaker."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

from . import protocol
from .camera import open_camera
from .config import Config, DetectorCfg
from .detectors import make_pipeline
from .geometry import Intrinsics
from .transport import BleLink, LinkManager, SerialLink

log = logging.getLogger(__name__)

CAMERA_RETRY_S = 5.0


@dataclass
class TargetFix:
    az_mdeg: float
    el_mdeg: float
    range_m: float | None
    t: float


def describe(fix: TargetFix | None, now: float, max_age_s: float = 1.0) -> str:
    """Spoken description of where the target is relative to the camera axis."""
    if fix is None or now - fix.t > max_age_s:
        return "no target"

    def part(v: float, pos: str, neg: str, zero: str) -> str:
        d = abs(v) / 1000.0
        if d < 0.05:
            return zero
        return f"{d:.1f} degrees {pos if v > 0 else neg}"

    text = f"target {part(fix.az_mdeg, 'right', 'left', 'centred')}, " \
           f"{part(fix.el_mdeg, 'up', 'down', 'level')}"
    if fix.range_m:
        text += f", {fix.range_m:.0f} metres"
    return text


class App:
    def __init__(self, cfg: Config, dry_run: bool = False, config_path: str | None = None) -> None:
        self.cfg = cfg
        self.config_path = config_path
        self.dry_run = dry_run
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop = threading.Event()
        self.tracking = threading.Event()
        self.tracking.set()
        self.synth = None
        self.ui = None

        # Status, read by the voice menu.
        self.nrf_seen = 0.0
        self.nrf_source = ""
        self.route = protocol.ROUTE_WIRED
        self.last_fix: TargetFix | None = None
        self.camera_ok = False
        self.camera_error = ""
        self.fps = 0.0
        self.hit_rate = 0.0
        self.seq = 0

        links = []
        if not dry_run and cfg.link.mode in ("serial", "both"):
            links.append(SerialLink(cfg.link.serial_port, cfg.link.baud, self.on_line))
        if not dry_run and cfg.link.mode in ("ble", "both"):
            links.append(BleLink(cfg.link.ble_address, cfg.link.ble_name, self.on_line))
        self.links = LinkManager(links)

    # ---- status helpers
    @property
    def gun_connected(self) -> bool:
        return time.monotonic() - self.nrf_seen < 3.0

    def ble_link(self) -> BleLink | None:
        return next((lk for lk in self.links.links if isinstance(lk, BleLink)), None)

    def describe_fix(self) -> str:
        return describe(self.last_fix, time.monotonic())

    # ---- incoming from the gun module (event-loop thread)
    def on_line(self, source: str, line: str) -> None:
        msg = protocol.parse(line)
        if msg is None:
            log.debug("ignored line from %s: %r", source, line)
            return
        self.nrf_seen = time.monotonic()
        self.nrf_source = source
        if isinstance(msg, protocol.Tone):
            if self.synth is not None:
                self.synth.update(msg)
        elif isinstance(msg, protocol.Route):
            if msg.route != self.route:
                log.info("audio route: %s", {1: "wired", 2: "bluetooth", 3: "both"}[msg.route])
            self.route = msg.route
        elif isinstance(msg, protocol.Zeroed):
            log.info("zeroed (%s)", "camera + tilt" if msg.camera else "tilt only")
            if self.ui is not None:
                self.ui.on_app_event("zeroed_cam" if msg.camera else "zeroed_tilt")

    # ---- camera thread
    def _send(self, line: bytes) -> None:
        if self.loop is not None and not self.dry_run:
            self.loop.call_soon_threadsafe(self.links.send, line)

    def _make_tracker(self, intr: Intrinsics):
        try:
            return make_pipeline(self.cfg.detector, intr)
        except Exception as e:  # missing or broken ML model: keep going on the card
            log.error("detector %s unavailable (%s); using the printed card", self.cfg.detector.type, e)
            self._notify_ui("model_error")
            fallback = DetectorCfg(**{**self.cfg.detector.__dict__, "type": "card"})
            return make_pipeline(fallback, intr)

    def _track(self, cam, intr: Intrinsics, exposure_latency_ms: float) -> None:
        tracker = self._make_tracker(intr)
        last_print = window_start = time.monotonic()
        frames = hits = 0
        while not self.stop.is_set():
            if not self.tracking.is_set():
                tracker.reset()
                self.fps = 0.0
                self.tracking.wait(0.5)
                continue
            gray, t_cap = cam.read()
            det = tracker.detect(gray)
            now = time.monotonic()
            age_ms = (now - t_cap) * 1000.0 + exposure_latency_ms
            self.seq += 1
            frames += 1
            if det is not None:
                hits += 1
                az, el = intr.pixel_to_angles_mdeg(det.x, det.y)
                self.last_fix = TargetFix(az, el, det.range_m, now)
                rng = det.range_m * 100.0 if det.range_m else None
                self._send(protocol.fmt_cam(self.seq, az, el, rng, age_ms))
            else:
                self._send(protocol.fmt_notarget(self.seq))
            if now - window_start >= 5.0:
                self.fps = frames / (now - window_start)
                self.hit_rate = hits / frames if frames else 0.0
                frames = hits = 0
                window_start = now
            if self.dry_run and now - last_print >= 0.5:
                last_print = now
                print(self.describe_fix(), flush=True)

    def _camera_thread(self, intr: Intrinsics) -> None:
        cam_cfg = self.cfg.resolved_camera()
        while not self.stop.is_set():
            cam = None
            try:
                cam = open_camera(cam_cfg)
                if (cam.width, cam.height) != (intr.width, intr.height):
                    intr = intr.scaled(cam.width, cam.height)
                self.camera_ok, self.camera_error = True, ""
                self._notify_ui("camera_ok")
                self._track(cam, intr, cam_cfg.exposure_latency_ms)
            except Exception as e:  # unplugged, not detected, driver error...
                log.warning("camera: %s", e)
                self.camera_ok, self.camera_error = False, str(e) or type(e).__name__
                self._notify_ui("camera_error")
            finally:
                if cam is not None:
                    try:
                        cam.close()
                    except Exception:
                        pass
            self.stop.wait(CAMERA_RETRY_S)

    def _notify_ui(self, event: str) -> None:
        if self.ui is not None and self.loop is not None:
            self.loop.call_soon_threadsafe(self.ui.on_app_event, event)

    async def _hello(self) -> None:
        while True:
            self.links.send(protocol.fmt_hello())
            await asyncio.sleep(1.0)

    async def _stats(self) -> None:
        while True:
            await asyncio.sleep(30.0)
            log.info("%.1f fps, target seen in %d%% of frames, gun module %s",
                     self.fps, round(self.hit_rate * 100),
                     f"connected ({self.nrf_source})" if self.gun_connected else "not heard from")

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        cam_cfg = self.cfg.resolved_camera()
        if self.cfg.camera.calibration:
            intr = Intrinsics.from_file(self.cfg.camera.calibration)
        else:
            intr = Intrinsics.from_hfov(cam_cfg.width, cam_cfg.height, cam_cfg.hfov_deg)

        if self.cfg.audio.bluetooth_tones and not self.dry_run:
            try:
                from .synth import ToneSynth

                self.synth = ToneSynth(self.cfg.audio.sample_rate, self.cfg.audio.device)
            except Exception as e:  # missing PortAudio, no output device, ...
                log.warning("tone output disabled: %s", e)

        tasks = [self.links.run(), self._hello(), self._stats()]
        if self.cfg.ui.enabled and not self.dry_run:
            from .ui.frontend import Frontend

            self.ui = Frontend(self)
            tasks.append(self.ui.run())

        cam = threading.Thread(target=self._camera_thread, args=(intr,), daemon=True)
        cam.start()
        try:
            await asyncio.gather(*tasks)
        finally:
            self.stop.set()
            self.tracking.set()  # release a paused camera thread
            if self.synth is not None:
                self.synth.close()
