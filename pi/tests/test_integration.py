"""End to end: synthetic camera -> App -> serial link (a pty) -> 'gun module'."""

import asyncio
import os
import pty
import time
import tty

from audiotarget import app as app_mod
from audiotarget.card import CardLayout
from audiotarget.config import Config
from audiotarget.geometry import Intrinsics

from synth_scene import place, render_card


class FakeCam:
    def __init__(self, frame):
        self.frame = frame
        self.height, self.width = frame.shape

    def read(self):
        time.sleep(0.02)
        return self.frame, time.monotonic()

    def close(self):
        pass


def test_camera_to_serial_and_tones_back(monkeypatch):
    intr = Intrinsics.from_hfov(1280, 720, 22.2)
    layout = CardLayout()
    frame, _ = place(render_card(layout), layout, intr, range_m=6.0, az_deg=1.5, el_deg=-0.75)
    monkeypatch.setattr(app_mod, "open_camera", lambda cfg: FakeCam(frame))

    master, slave = pty.openpty()
    tty.setraw(master)
    tty.setraw(slave)
    cfg = Config()
    cfg.profile = "zero2w"
    cfg.camera.hfov_deg = 22.2
    cfg.link.mode = "serial"
    cfg.link.serial_port = os.ttyname(slave)
    cfg.audio.bluetooth_tones = False
    a = app_mod.App(cfg)

    received = bytearray()

    async def gun_module():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while loop.time() < deadline and (received.count(b"\nC ") < 5 or b"H 1 pi" not in received):
            await asyncio.sleep(0.05)
            try:
                received.extend(os.read(master, 4096))
            except BlockingIOError:
                pass
        os.write(master, b"H 1 nrf\nA 3\nZ 1\n")
        await asyncio.sleep(0.3)

    async def main():
        os.set_blocking(master, False)
        run = asyncio.create_task(a.run())
        await gun_module()
        run.cancel()
        try:
            await run
        except asyncio.CancelledError:
            pass

    asyncio.run(main())
    lines = received.decode().splitlines()
    cams = [ln for ln in lines if ln.startswith("C ")]
    assert any(ln.startswith("H 1 pi") for ln in lines)
    assert len(cams) >= 5
    _, _seq, az, el, rng, age = cams[-1].split()
    assert abs(int(az) - 1500) < 40 and abs(int(el) + 750) < 40
    assert abs(int(rng) - 600) < 30
    assert 0 <= int(age) < 200
    assert a.route == 3 and a.gun_connected and a.nrf_source == "serial"
    assert a.describe_fix().startswith("target 1.5 degrees right, 0.7")
    os.close(master)
    os.close(slave)
