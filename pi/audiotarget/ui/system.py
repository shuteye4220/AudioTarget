"""System helpers for the voice menu: Bluetooth audio, volume, power, network.

Every command is run as an argument list (never through a shell) with a
timeout, and anything that came from outside (device addresses) is validated.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

MAC_RE = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
_DEVICE_LINE = re.compile(r"^Device ([0-9A-F:]{17}) (.*)$")


async def run(*args: str, timeout: float = 15.0) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
    except OSError as e:
        return 127, str(e)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "timed out"
    return proc.returncode or 0, out.decode("utf-8", "replace")


def valid_mac(mac: str) -> bool:
    return bool(MAC_RE.match(mac))


@dataclass(frozen=True)
class BtDevice:
    mac: str
    name: str


def parse_devices(text: str) -> list[BtDevice]:
    out = []
    for line in text.splitlines():
        m = _DEVICE_LINE.match(line.strip())
        if m:
            out.append(BtDevice(m.group(1), m.group(2).strip()))
    return out


def is_audio_device(info: str) -> bool:
    return ("Icon: audio-" in info or "Audio Sink" in info
            or "0000110b-0000-1000-8000-00805f9b34fb" in info.lower())


async def bt_scan_audio(seconds: int = 10) -> list[BtDevice]:
    await run("bluetoothctl", "--timeout", str(seconds), "scan", "on", timeout=seconds + 5)
    _, text = await run("bluetoothctl", "devices")
    found = []
    for dev in parse_devices(text)[:30]:
        _, info = await run("bluetoothctl", "info", dev.mac, timeout=5)
        if is_audio_device(info):
            found.append(dev)
    return found


async def bt_paired() -> list[BtDevice]:
    _, text = await run("bluetoothctl", "devices", "Paired")
    return parse_devices(text)


async def bt_connect_audio(mac: str) -> bool:
    if not valid_mac(mac):
        return False
    await run("bluetoothctl", "--timeout", "20", "pair", mac, timeout=25)
    await run("bluetoothctl", "trust", mac)
    rc, out = await run("bluetoothctl", "--timeout", "15", "connect", mac, timeout=20)
    return rc == 0 and "Connection successful" in out


async def bt_forget(mac: str) -> bool:
    if not valid_mac(mac):
        return False
    rc, _ = await run("bluetoothctl", "remove", mac)
    return rc == 0


async def volume_change(step_percent: int) -> int | None:
    sign = "+" if step_percent >= 0 else "-"
    await run("wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@",
              f"{abs(step_percent)}%{sign}")
    return await volume_get()


async def volume_get() -> int | None:
    rc, out = await run("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@")
    m = re.search(r"Volume:\s*([0-9.]+)", out)
    return round(float(m.group(1)) * 100) if rc == 0 and m else None


def sink_usable(inspect_output: str, rc: int) -> bool:
    """Is there a default audio output someone could hear? HDMI with no TV doesn't count."""
    if rc != 0:
        return False
    m = re.search(r'node\.name = "([^"]*)"', inspect_output)
    name = m.group(1).lower() if m else ""
    return bool(name) and "hdmi" not in name and "auto_null" not in name


async def audio_output_ready() -> bool:
    rc, out = await run("wpctl", "inspect", "@DEFAULT_AUDIO_SINK@", timeout=5)
    return sink_usable(out, rc)


async def ip_addresses() -> list[str]:
    _, out = await run("hostname", "-I")
    return [a for a in out.split() if re.match(r"^[0-9.]+$", a)]


async def hostname() -> str:
    _, out = await run("hostname")
    return out.strip()


async def power(action: str) -> None:
    if action in ("poweroff", "reboot"):
        await run("systemctl", action)
