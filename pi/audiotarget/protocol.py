"""AudioTarget line protocol (mirror of firmware/src/proto.c). See docs/protocol.md."""

from __future__ import annotations

import re
from dataclasses import dataclass

VERSION = 1
MAX_LINE = 63  # bytes, excluding the newline
MAX_ANGLE_MDEG = 45_000
MAX_RANGE_CM = 100_000
MAX_AGE_MS = 2_000

TONE_FLAG_CANT = 0x01
TONE_FLAG_LOST = 0x02

ROUTE_WIRED = 0x1
ROUTE_BT = 0x2

_INT = r"(0|[1-9][0-9]{0,9})"
_RE_TONE = re.compile(rf"^T {_INT} {_INT} {_INT} {_INT}$")
_RE_ROUTE = re.compile(r"^A ([1-3])$")
_RE_ZERO = re.compile(r"^Z ([01])$")
_RE_HELLO = re.compile(rf"^H {_INT} ([a-z0-9]{{1,8}})$")


@dataclass(frozen=True)
class Tone:
    freq_hz: float
    gain_l: float  # 0..1
    gain_r: float
    flags: int


@dataclass(frozen=True)
class Route:
    route: int


@dataclass(frozen=True)
class Zeroed:
    camera: bool


@dataclass(frozen=True)
class Hello:
    version: int
    role: str


Message = Tone | Route | Zeroed | Hello


def parse(line: str) -> Message | None:
    """Parse one line from the nRF. Returns None for anything malformed."""
    if len(line) > MAX_LINE:
        return None
    if m := _RE_TONE.match(line):
        freq_dhz, gl, gr, flags = (int(g) for g in m.groups())
        if not (200 <= freq_dhz <= 80_000 and gl <= 100 and gr <= 100 and flags <= 0xFF):
            return None
        return Tone(freq_dhz / 10.0, gl / 100.0, gr / 100.0, flags)
    if m := _RE_ROUTE.match(line):
        return Route(int(m.group(1)))
    if m := _RE_ZERO.match(line):
        return Zeroed(m.group(1) == "1")
    if m := _RE_HELLO.match(line):
        return Hello(int(m.group(1)), m.group(2))
    return None


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def fmt_hello() -> bytes:
    return f"H {VERSION} pi\n".encode()


def fmt_cam(seq: int, az_mdeg: float, el_mdeg: float, range_cm: float | None, age_ms: float) -> bytes:
    az = _clamp(round(az_mdeg), -MAX_ANGLE_MDEG, MAX_ANGLE_MDEG)
    el = _clamp(round(el_mdeg), -MAX_ANGLE_MDEG, MAX_ANGLE_MDEG)
    rng = _clamp(round(range_cm or 0), 0, MAX_RANGE_CM)
    age = _clamp(round(age_ms), 0, MAX_AGE_MS)
    return f"C {seq & 0xFFFFFFFF} {az} {el} {rng} {age}\n".encode()


def fmt_notarget(seq: int) -> bytes:
    return f"N {seq & 0xFFFFFFFF}\n".encode()


class LineAssembler:
    """Turns an untrusted byte stream into lines; drops over-long or binary lines."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._overflow = False

    def feed(self, data: bytes) -> list[str]:
        lines: list[str] = []
        for b in data:
            if b == 0x0D:
                continue
            if b == 0x0A:
                if not self._overflow and self._buf:
                    lines.append(self._buf.decode("ascii"))
                self._buf.clear()
                self._overflow = False
                continue
            if self._overflow:
                continue
            if b < 0x20 or b > 0x7E or len(self._buf) >= MAX_LINE:
                self._overflow = True
                self._buf.clear()
                continue
            self._buf.append(b)
        return lines
