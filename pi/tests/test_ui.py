import asyncio
import threading
import time

import pytest

from audiotarget.app import TargetFix, describe
from audiotarget.config import Config, load
from audiotarget.ui import system
from audiotarget.ui.keys import Action, KeyDecoder
from audiotarget.ui.menu import Item, Menu, Navigator
from audiotarget.ui.speech import clean


def run(coro):
    return asyncio.run(coro)


def test_key_decoder_select_and_long_press():
    d = KeyDecoder(800)
    assert d.feed("KEY_KP8", 1, 0.0) is Action.UP
    assert d.feed("KEY_KP8", 2, 0.1) is Action.UP  # auto-repeat allowed for moving
    assert d.feed("KEY_KP8", 0, 0.2) is None
    assert d.feed("KEY_ENTER", 1, 1.0) is None
    assert d.feed("KEY_ENTER", 0, 1.2) is Action.SELECT
    assert d.feed("KEY_ENTER", 1, 2.0) is None
    assert d.feed("KEY_ENTER", 2, 2.5) is None
    assert d.feed("KEY_ENTER", 0, 3.0) is Action.BACK
    assert d.feed("KEY_KPASTERISK", 1) is Action.REPEAT
    assert d.feed("KEY_KPASTERISK", 2) is None  # no repeat-repeat
    assert d.feed("KEY_Q", 1) is None


def test_navigator():
    said = []

    async def say(t):
        said.append(t)

    hits = []

    async def act():
        hits.append(1)

    sub = Menu("Sub", [Item("Alpha", act), Item("Beta")])
    root = Menu("Main", [Item("One"), Item("Two", submenu=sub), Item(lambda: "Three")])
    nav = Navigator(root, say)

    async def go():
        await nav.handle(Action.DOWN)
        assert said[-1] == "Two. 2 of 3"
        await nav.handle(Action.SELECT)
        assert said[-1] == "Sub. Alpha. 1 of 2"
        await nav.handle(Action.SELECT)
        assert hits == [1]
        await nav.handle(Action.UP)
        assert said[-1] == "Beta. 2 of 2"  # wraps
        await nav.handle(Action.BACK)
        assert said[-1] == "Main. Two. 2 of 3"
        await nav.handle(Action.DOWN)
        assert said[-1] == "Three. 3 of 3"
        await nav.handle(Action.BACK)
        assert said[-1].startswith("Top menu")
        await nav.handle(Action.HOME)
        assert said[-1] == "Main. One. 1 of 3"

    run(go())


def test_navigator_dynamic_and_empty_menu():
    said = []

    async def say(t):
        said.append(t)

    async def build():
        return Menu("Found", [], empty_text="Nothing found.")

    nav = Navigator(Menu("Main", [Item("Scan", submenu=build)]), say)

    async def go():
        await nav.handle(Action.SELECT)
        assert said[-1] == "Found. Nothing found."
        await nav.handle(Action.DOWN)
        assert said[-1] == "Nothing found."

    run(go())


def test_clean_speech_text():
    assert clean("Bob's\x1b[31m phone\n") == "Bob's [31m phone"
    assert len(clean("x" * 5000)) == 400


def test_describe_fix():
    now = 100.0
    assert describe(None, now) == "no target"
    assert describe(TargetFix(1234, -20, 12.4, now), now) == \
        "target 1.2 degrees right, level, 12 metres"
    assert describe(TargetFix(-500, 800, None, now), now) == \
        "target 0.5 degrees left, 0.8 degrees up"
    assert describe(TargetFix(0, 0, None, now - 5), now) == "no target"


def test_bt_parsing_and_validation():
    text = ("Device AA:BB:CC:DD:EE:FF Suunto Wing\nDevice 11:22:33:44:55:66 AudioTarget\n"
            "garbage line\nDevice ZZ:BB:CC:DD:EE:FF bad\n")
    devs = system.parse_devices(text)
    assert [d.mac for d in devs] == ["AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"]
    assert devs[0].name == "Suunto Wing"
    assert system.is_audio_device("\tIcon: audio-headset\n")
    assert system.is_audio_device("UUID: Audio Sink (0000110b-0000-1000-8000-00805f9b34fb)")
    assert not system.is_audio_device("Icon: phone")
    assert system.valid_mac("AA:BB:CC:DD:EE:FF")
    for bad in ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:FF; reboot", "-h"):
        assert not system.valid_mac(bad)
    assert run(system.bt_forget("not-a-mac")) is False


def test_sink_usable():
    assert system.sink_usable('  * node.name = "bluez_output.AA_BB.1"\n', 0)
    assert system.sink_usable('node.name = "alsa_output.usb-C-Media.analog-stereo"', 0)
    assert not system.sink_usable('node.name = "alsa_output.platform-107c701400.hdmi.hdmi-stereo"', 0)
    assert not system.sink_usable("", 1)
    assert not system.sink_usable('node.name = "auto_null"', 0)


def test_bootstrap_pairs_first_headset(frontend, monkeypatch):
    f = frontend
    state = {"ready": False}

    async def ready():
        return state["ready"]

    async def paired():
        return []

    async def scan(_s):
        return [system.BtDevice("AA:BB:CC:DD:EE:FF", "Suunto Wing")]

    async def connect(mac):
        state["ready"] = True
        return mac == "AA:BB:CC:DD:EE:FF"

    async def nosleep(_s):
        return None

    monkeypatch.setattr(system, "audio_output_ready", ready)
    monkeypatch.setattr(system, "bt_paired", paired)
    monkeypatch.setattr(system, "bt_scan_audio", scan)
    monkeypatch.setattr(system, "bt_connect_audio", connect)
    from audiotarget.ui import frontend as fe
    monkeypatch.setattr(fe.asyncio, "sleep", nosleep)
    run(f._bootstrap_audio())
    assert f.speaker.said == ["Connected to Suunto Wing."]


class FakeSpeaker:
    def __init__(self):
        self.said = []
        self.rate = 175
        self.last = ""

    async def say(self, text, interrupt=True):
        self.said.append(text)
        self.last = text

    async def finish(self):
        pass

    async def repeat(self):
        self.said.append(self.last)


class FakeApp:
    def __init__(self, cfg, path):
        self.cfg = cfg
        self.config_path = path
        self.tracking = threading.Event()
        self.tracking.set()
        self.gun_connected = True
        self.nrf_source = "ble"
        self.route = 3
        self.camera_ok = True
        self.fps = 29.6
        self.hit_rate = 0.82

    def describe_fix(self):
        return "target 0.4 degrees left, level"


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    from audiotarget.ui import frontend as fe

    path = tmp_path / "audiotarget.toml"
    path.write_text('[camera]\nhfov_deg = 22.2\n[ui]\nenabled = true\n')
    app = FakeApp(load(path), str(path))
    f = fe.Frontend(app)
    f.speaker = FakeSpeaker()
    f.nav.say = f.speaker.say
    execs = []
    monkeypatch.setattr(fe.os, "execv", lambda *a: execs.append(a))
    f.execs = execs
    return f


def test_frontend_status_and_menu(frontend):
    f = frontend

    async def go():
        await f.nav.handle(Action.SELECT)  # Status
        s = f.speaker.said[-1]
        assert "Tracking on" in s and "connected by Bluetooth" in s and "30 frames" in s
        assert "82 percent" in s
        await f.nav.handle(Action.DOWN)
        await f.nav.handle(Action.SELECT)  # Where is the target
        assert f.speaker.said[-1] == "target 0.4 degrees left, level"
        await f.nav.handle(Action.DOWN)
        await f.nav.handle(Action.DOWN)
        assert f.speaker.said[-1].startswith("Pause tracking")
        await f.nav.handle(Action.SELECT)
        assert not f.app.tracking.is_set()
        assert f.nav.current_text().startswith("Resume tracking")

    run(go())


def test_frontend_setting_change_saves_and_restarts(frontend):
    f = frontend

    async def go():
        await f.nav.handle(Action.HOME)
        for _ in range(6):
            await f.nav.handle(Action.DOWN)  # Camera
        assert f.nav.current_text().startswith("Camera")
        await f.nav.handle(Action.SELECT)
        await f.nav.handle(Action.SELECT)  # Camera and lens
        assert "16 millimetre lens, selected" in f.speaker.said[-1]
        await f.nav.handle(Action.DOWN)    # 25 mm
        await f.nav.handle(Action.SELECT)

    run(go())
    assert f.execs, "should restart after saving"
    saved = load(f.app.config_path)
    assert saved.camera.hfov_deg == pytest.approx(14.3)
    assert saved.ui.enabled


def test_frontend_shutdown_needs_confirmation(frontend, monkeypatch):
    f = frontend
    calls = []

    async def fake_power(what):
        calls.append(what)

    monkeypatch.setattr(system, "power", fake_power)

    async def go():
        await f._power("poweroff")
        assert calls == [] and "again" in f.speaker.said[-1]
        await f._power("poweroff")
        assert calls == ["poweroff"]

    run(go())


def test_frontend_onnx_without_model_is_refused(frontend):
    f = frontend

    async def go():
        await f._apply(lambda c: setattr(c.detector, "type", "onnx"), "ML selected")

    run(go())
    assert not f.execs
    assert "Couldn't save" in f.speaker.said[-1]
