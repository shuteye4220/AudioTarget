"""The spoken menu: ties keys, speech and menu items to the running App.

Keys (USB numeric keypad / keyboard / GPIO buttons):
  Up / 8, Down / 2       move through the menu
  Select / Enter / 5     choose (hold for Back on a 3-button setup)
  Back / Backspace / 0   go back
  + and -                volume
  *                      repeat the last thing spoken
  /                      top menu
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import sys
import time
from typing import TYPE_CHECKING, Callable

from ..config import Config, ConfigError, save
from . import system
from .keys import Action, KeyReader
from .menu import Item, Menu, Navigator
from .speech import Speaker

if TYPE_CHECKING:
    from ..app import App

log = logging.getLogger(__name__)

# (spoken name, camera backend, horizontal field of view in degrees)
LENS_PRESETS: list[tuple[str, str, float]] = [
    ("Pi H Q camera with 16 millimetre lens", "picamera2", 22.2),
    ("Pi H Q camera with 25 millimetre lens", "picamera2", 14.3),
    ("Pi H Q camera with 35 millimetre lens", "picamera2", 10.3),
    ("Pi H Q camera with 50 millimetre lens", "picamera2", 7.2),
    ("Pi Camera Module 3", "picamera2", 66.0),
    ("Pi Camera Module 3 wide", "picamera2", 102.0),
    ("U S B camera, narrow, 30 degrees", "v4l2", 30.0),
    ("U S B camera, standard, 60 degrees", "v4l2", 60.0),
]

DETECTORS = [
    ("Printed AudioTarget card, recommended", "card"),
    ("Card markers only", "aruco"),
    ("Plain bullseye rings only", "bullseye"),
    ("Machine learning model", "onnx"),
]

LINK_MODES = [("Wire and Bluetooth", "both"), ("Wire only", "serial"),
              ("Bluetooth only", "ble")]

ROUTE_NAMES = {1: "wired earphones", 2: "Bluetooth", 3: "wired and Bluetooth"}
CONFIRM_S = 5.0


class Frontend:
    def __init__(self, app: "App") -> None:
        self.app = app
        ui = app.cfg.ui
        self.speaker = Speaker(ui.voice, ui.speech_rate)
        self.nav = Navigator(self._root(), self.speaker.say)
        self.actions: asyncio.Queue[Action] = asyncio.Queue(maxsize=16)
        self.keys = KeyReader(self._on_key, ui.long_press_ms)
        self._gun_was = False
        self._camera_was: bool | None = None
        self._confirm: tuple[str, float] | None = None
        self._follow: asyncio.Task | None = None

    # ------------------------------------------------------------ plumbing
    def _on_key(self, action: Action) -> None:
        try:
            self.actions.put_nowait(action)
        except asyncio.QueueFull:
            pass

    async def run(self) -> None:
        await self._bootstrap_audio()
        await self.speaker.say("AudioTarget ready. Press select for the menu.")
        await asyncio.gather(self.keys.run(), self._consume(), self._watch())

    async def _bootstrap_audio(self, tries: int = 12) -> None:
        """With nothing to speak through (e.g. a Zero 2 W on first boot), pair the
        first headset or speaker found in pairing mode, so the menu can be heard.
        Plugging in a USB sound card also works and skips this."""
        for _ in range(tries):
            if await system.audio_output_ready():
                return
            if await system.bt_paired():
                await asyncio.sleep(5.0)  # a known headset may just be switched off
                if await system.audio_output_ready():
                    return
            devices = await system.bt_scan_audio(10)
            for dev in devices:
                if await system.bt_connect_audio(dev.mac):
                    await asyncio.sleep(2.0)
                    await self.speaker.say(f"Connected to {dev.name}.")
                    return
        log.warning("no audio output found; continuing silently")

    async def _consume(self) -> None:
        while True:
            action = await self.actions.get()
            if self._follow is not None:  # any key stops target following
                self._follow.cancel()
                self._follow = None
                if action not in (Action.VOL_UP, Action.VOL_DOWN):
                    await self.speaker.say("Stopped following.")
                    continue
            try:
                if action in (Action.VOL_UP, Action.VOL_DOWN):
                    vol = await system.volume_change(5 if action is Action.VOL_UP else -5)
                    await self.speaker.say(f"Volume {vol} percent" if vol is not None
                                           else "Volume control not available")
                elif action is Action.REPEAT:
                    await self.speaker.repeat()
                else:
                    await self.nav.handle(action)
            except Exception:
                log.exception("menu action failed")
                await self.speaker.say("Sorry, that didn't work.")

    async def _watch(self) -> None:
        """Announce gun-module connects and disconnects."""
        while True:
            await asyncio.sleep(1.0)
            if not self.app.cfg.ui.announce:
                continue
            now = self.app.gun_connected
            if now != self._gun_was:
                self._gun_was = now
                await self.speaker.say(
                    f"Gun module connected by {self._source_name()}." if now
                    else "Gun module disconnected.", interrupt=False)

    def on_app_event(self, event: str) -> None:
        text = None
        if event == "camera_ok" and self._camera_was is not True:
            text = "Camera ready." if self._camera_was is False else None
            self._camera_was = True
        elif event == "camera_error" and self._camera_was is not False:
            text = "Camera not found. Retrying."
            self._camera_was = False
        elif event == "zeroed_cam":
            text = "Zeroed on target."
        elif event == "zeroed_tilt":
            text = "Zeroed, tilt only."
        if text and self.app.cfg.ui.announce:
            asyncio.create_task(self.speaker.say(text, interrupt=False))

    def _source_name(self) -> str:
        return {"ble": "Bluetooth", "serial": "wire"}.get(self.app.nrf_source, "link")

    # ------------------------------------------------------------ status
    def status_text(self) -> str:
        a = self.app
        parts = ["Tracking on." if a.tracking.is_set() else "Tracking paused."]
        if a.gun_connected:
            parts.append(f"Gun module connected by {self._source_name()}, "
                         f"tones to {ROUTE_NAMES.get(a.route, 'unknown')}.")
        else:
            parts.append("Gun module not connected.")
        if a.camera_ok:
            parts.append(f"Camera running at {a.fps:.0f} frames per second, "
                         f"target seen {round(a.hit_rate * 100)} percent of the time.")
        else:
            parts.append("Camera not found.")
        return " ".join(parts)

    # ------------------------------------------------------------ settings
    async def _apply(self, change: Callable[[Config], None], message: str) -> None:
        """Change a setting, save it, and restart the service to use it."""
        if not self.app.config_path:
            await self.speaker.say("No settings file, so this can't be saved.")
            return
        cfg = copy.deepcopy(self.app.cfg)
        change(cfg)
        try:
            save(cfg, self.app.config_path)
        except (ConfigError, OSError) as e:
            await self.speaker.say(f"Couldn't save: {e}")
            return
        await self.speaker.say(f"{message}. Restarting.")
        await self.speaker.finish()
        os.execv(sys.executable, [sys.executable, "-m", "audiotarget", *sys.argv[1:]])

    def _save_quietly(self) -> None:
        if self.app.config_path:
            try:
                save(self.app.cfg, self.app.config_path)
            except (ConfigError, OSError) as e:
                log.warning("couldn't save settings: %s", e)

    async def _confirmed(self, key: str, prompt: str) -> bool:
        now = time.monotonic()
        if self._confirm and self._confirm[0] == key and now - self._confirm[1] < CONFIRM_S:
            self._confirm = None
            return True
        self._confirm = (key, now)
        await self.speaker.say(prompt)
        return False

    # ------------------------------------------------------------ actions
    async def _say_status(self) -> None:
        await self.speaker.say(self.status_text())

    async def _where(self) -> None:
        await self.speaker.say(self.app.describe_fix())

    async def _follow_target(self) -> None:
        async def loop() -> None:
            while True:
                await self.speaker.say(self.app.describe_fix())
                await asyncio.sleep(2.0)
        await self.speaker.say("Following target. Press any key to stop.")
        await self.speaker.finish()
        self._follow = asyncio.create_task(loop())

    async def _toggle_tracking(self) -> None:
        if self.app.tracking.is_set():
            self.app.tracking.clear()
            await self.speaker.say("Tracking paused.")
        else:
            self.app.tracking.set()
            await self.speaker.say("Tracking on.")

    async def _bt_scan_menu(self) -> Menu:
        await self.speaker.say("Searching for headphones and speakers. Make sure yours is in "
                               "pairing mode. This takes about 10 seconds.")
        devices = await system.bt_scan_audio(10)

        def connect(dev: system.BtDevice):
            async def act() -> None:
                await self.speaker.say(f"Connecting to {dev.name}.")
                ok = await system.bt_connect_audio(dev.mac)
                await self.speaker.say(f"Connected to {dev.name}." if ok
                                       else f"Couldn't connect to {dev.name}.")
            return act

        return Menu("Devices found", [Item(d.name or d.mac, connect(d)) for d in devices],
                    empty_text="No headphones or speakers found. Press back to try again.")

    async def _bt_paired_menu(self) -> Menu:
        devices = await system.bt_paired()

        def forget(dev: system.BtDevice):
            async def act() -> None:
                if await self._confirmed(f"forget {dev.mac}",
                                         f"Press select again to forget {dev.name}."):
                    ok = await system.bt_forget(dev.mac)
                    await self.speaker.say("Forgotten." if ok else "Couldn't forget it.")
            return act

        return Menu("Paired devices, select to forget",
                    [Item(d.name or d.mac, forget(d)) for d in devices],
                    empty_text="No paired devices.")

    async def _pair_gun(self) -> None:
        from bleak import BleakScanner

        from ..transport import NUS_SERVICE

        await self.speaker.say("Searching for the gun module.")
        found = await BleakScanner.discover(timeout=10.0, return_adv=True)
        best = None
        for dev, adv in found.values():
            uuids = [u.lower() for u in (adv.service_uuids or [])]
            if NUS_SERVICE in uuids and adv.local_name == self.app.cfg.link.ble_name:
                if best is None or adv.rssi > best[1].rssi:
                    best = (dev, adv)
        if best is None:
            await self.speaker.say("No gun module found. Hold its mode button for 3 seconds "
                                   "until it beeps three times, then try again.")
            return
        address = best[0].address.upper()

        def change(cfg: Config) -> None:
            cfg.link.ble_address = address
            if cfg.link.mode == "serial":
                cfg.link.mode = "both"

        await self._apply(change, "Found the gun module. It will pair after the restart")

    async def _speak_ip(self) -> None:
        ips = await system.ip_addresses()
        name = await system.hostname()
        if not ips:
            await self.speaker.say(f"No network. Host name {name}.")
        else:
            spoken = ", ".join(" dot ".join(ip.split(".")) for ip in ips)
            await self.speaker.say(f"Address {spoken}. Host name {name}.")

    async def _power(self, what: str) -> None:
        word = "shut down" if what == "poweroff" else "restart"
        if await self._confirmed(what, f"Press select again to {word}."):
            await self.speaker.say("Shutting down." if what == "poweroff" else "Restarting.")
            await self.speaker.finish()
            await system.power(what)

    async def _rate(self, delta: int) -> None:
        ui = self.app.cfg.ui
        ui.speech_rate = max(80, min(450, ui.speech_rate + delta))
        self.speaker.rate = ui.speech_rate
        self._save_quietly()
        await self.speaker.say(f"Speech rate {ui.speech_rate}.")

    async def _toggle_announce(self) -> None:
        ui = self.app.cfg.ui
        ui.announce = not ui.announce
        self._save_quietly()
        await self.speaker.say("Announcements on." if ui.announce else "Announcements off.")

    # ------------------------------------------------------------ menus
    def _choice_menu(self, title: str, options, current: Callable[[], object],
                     change: Callable[[Config, object], None]) -> Menu:
        def item(label: str, value) -> Item:
            async def act() -> None:
                if current() == value:
                    await self.speaker.say(f"{label} is already selected.")
                    return
                await self._apply(lambda cfg: change(cfg, value), f"{label} selected")
            return Item(lambda: f"{label}{', selected' if current() == value else ''}", act)
        return Menu(title, [item(label, value) for label, value in options])

    def _root(self) -> Menu:
        cfg = self.app.cfg

        def set_lens(c: Config, v) -> None:
            c.camera.backend, c.camera.hfov_deg = v

        def set_detector(c: Config, v) -> None:
            c.detector.type = v

        def set_link(c: Config, v) -> None:
            c.link.mode = v

        def set_tones(c: Config, v) -> None:
            c.audio.bluetooth_tones = v

        camera = Menu("Camera", [
            Item("Camera and lens", submenu=self._choice_menu(
                "Camera and lens", [(n, (b, f)) for n, b, f in LENS_PRESETS],
                lambda: (cfg.camera.backend, cfg.camera.hfov_deg), set_lens)),
            Item("Target type", submenu=self._choice_menu(
                "Target type", DETECTORS, lambda: cfg.detector.type, set_detector)),
            Item("Turn the picture upside down", self._flip),
        ])
        gun = Menu("Gun module", [
            Item("Pair a gun module by Bluetooth", self._pair_gun),
            Item("Connection type", submenu=self._choice_menu(
                "Connection type", LINK_MODES, lambda: cfg.link.mode, set_link)),
            Item("Play guidance tones on this Pi's audio", submenu=self._choice_menu(
                "Guidance tones on this Pi", [("On", True), ("Off", False)],
                lambda: cfg.audio.bluetooth_tones, set_tones)),
        ])
        bluetooth = Menu("Bluetooth audio", [
            Item("Search for headphones and speakers", submenu=self._bt_scan_menu),
            Item("Paired devices", submenu=self._bt_paired_menu),
        ])
        speech = Menu("Speech", [
            Item("Faster", lambda: self._rate(25)),
            Item("Slower", lambda: self._rate(-25)),
            Item(lambda: f"Announcements {'on' if cfg.ui.announce else 'off'}",
                 self._toggle_announce),
        ])
        system_menu = Menu("System", [
            Item("Speak network address", self._speak_ip),
            Item("Restart", lambda: self._power("reboot")),
            Item("Shut down", lambda: self._power("poweroff")),
        ])
        return Menu("Main menu", [
            Item("Status", self._say_status),
            Item("Where is the target", self._where),
            Item("Follow the target", self._follow_target),
            Item(lambda: "Pause tracking" if self.app.tracking.is_set() else "Resume tracking",
                 self._toggle_tracking),
            Item("Bluetooth audio", submenu=bluetooth),
            Item("Gun module", submenu=gun),
            Item("Camera", submenu=camera),
            Item("Speech", submenu=speech),
            Item("System", submenu=system_menu),
        ])

    async def _flip(self) -> None:
        flipped = not self.app.cfg.camera.rotate_180

        def change(cfg: Config) -> None:
            cfg.camera.rotate_180 = flipped

        await self._apply(change, "Picture flipped" if flipped else "Picture upright")
