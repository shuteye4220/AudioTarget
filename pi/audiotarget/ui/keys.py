"""Key input from any keyboard, USB numeric keypad, or GPIO buttons.

GPIO buttons are set up in /boot/firmware/config.txt with the gpio-key
overlay so they appear as ordinary key presses (KEY_UP, KEY_DOWN,
KEY_ENTER); everything goes through evdev.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import Callable

log = logging.getLogger(__name__)


class Action(enum.Enum):
    UP = "up"
    DOWN = "down"
    SELECT = "select"
    BACK = "back"
    VOL_UP = "volume up"
    VOL_DOWN = "volume down"
    REPEAT = "repeat"
    HOME = "home"


KEYMAP: dict[str, Action] = {
    "KEY_UP": Action.UP, "KEY_KP8": Action.UP,
    "KEY_DOWN": Action.DOWN, "KEY_KP2": Action.DOWN,
    "KEY_ENTER": Action.SELECT, "KEY_KPENTER": Action.SELECT, "KEY_KP5": Action.SELECT,
    "KEY_SPACE": Action.SELECT, "KEY_RIGHT": Action.SELECT, "KEY_KP6": Action.SELECT,
    "KEY_BACKSPACE": Action.BACK, "KEY_ESC": Action.BACK, "KEY_LEFT": Action.BACK,
    "KEY_KP4": Action.BACK, "KEY_KP0": Action.BACK,
    "KEY_KPPLUS": Action.VOL_UP, "KEY_VOLUMEUP": Action.VOL_UP, "KEY_EQUAL": Action.VOL_UP,
    "KEY_KPMINUS": Action.VOL_DOWN, "KEY_VOLUMEDOWN": Action.VOL_DOWN, "KEY_MINUS": Action.VOL_DOWN,
    "KEY_KPASTERISK": Action.REPEAT, "KEY_R": Action.REPEAT,
    "KEY_KPSLASH": Action.HOME, "KEY_HOME": Action.HOME, "KEY_H": Action.HOME,
}

REPEATABLE = {Action.UP, Action.DOWN, Action.VOL_UP, Action.VOL_DOWN}


class KeyDecoder:
    """Turns raw (key name, value) events into actions. Pure logic, testable.

    Select fires on release so that holding it can mean Back instead, which
    gives a 3-button setup (up, down, select) a way back out of menus.
    """

    def __init__(self, long_press_ms: int = 800) -> None:
        self.long_s = long_press_ms / 1000.0
        self.select_down: float | None = None

    def feed(self, key: str, value: int, now: float | None = None) -> Action | None:
        now = time.monotonic() if now is None else now
        action = KEYMAP.get(key)
        if action is None:
            return None
        if action is Action.SELECT:
            if value == 1:
                self.select_down = now
            elif value == 0 and self.select_down is not None:
                held = now - self.select_down
                self.select_down = None
                return Action.BACK if held >= self.long_s else Action.SELECT
            return None
        if value == 1 or (value == 2 and action in REPEATABLE):
            return action
        return None


class KeyReader:
    """Reads every keyboard-like input device, including ones plugged in later."""

    def __init__(self, on_action: Callable[[Action], None], long_press_ms: int) -> None:
        self.on_action = on_action
        self.long_press_ms = long_press_ms
        self.open: dict[str, asyncio.Task] = {}

    async def run(self) -> None:
        import evdev

        wanted = {evdev.ecodes.ecodes[k] for k in KEYMAP if k in evdev.ecodes.ecodes}
        while True:
            for path in evdev.list_devices():
                if path in self.open and not self.open[path].done():
                    continue
                try:
                    dev = evdev.InputDevice(path)
                except OSError:
                    continue
                keys = set(dev.capabilities().get(evdev.ecodes.EV_KEY, []))
                if not keys & wanted:
                    dev.close()
                    continue
                # Grab keypads and the belt buttons so their presses don't land in the
                # login console; leave full keyboards shared so the console still works.
                grab = evdev.ecodes.KEY_A not in keys
                log.info("input device: %s (%s)%s", dev.name, path, " [exclusive]" if grab else "")
                self.open[path] = asyncio.create_task(self._read(dev, grab))
            await asyncio.sleep(3.0)

    async def _read(self, dev, grab: bool) -> None:
        import evdev

        decoder = KeyDecoder(self.long_press_ms)
        try:
            if grab:
                try:
                    dev.grab()
                except OSError:
                    pass
            async for ev in dev.async_read_loop():
                if ev.type != evdev.ecodes.EV_KEY:
                    continue
                name = evdev.ecodes.KEY.get(ev.code)
                if isinstance(name, list):
                    name = name[0]
                action = decoder.feed(name or "", ev.value)
                if action is not None:
                    self.on_action(action)
        except OSError:
            log.info("input device removed: %s", dev.path)
        finally:
            try:
                dev.close()
            except Exception:
                pass
