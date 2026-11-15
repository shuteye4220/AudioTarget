"""Plays the guidance tone on the Pi's audio output (e.g. a Bluetooth speaker).

ToneRenderer is pure numpy (testable); ToneSynth wraps it in a sounddevice
stream. The gating patterns match firmware/src/audio.c.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from .protocol import TONE_FLAG_CANT, TONE_FLAG_LOST, Tone

log = logging.getLogger(__name__)

STALE_S = 0.3  # silence if the gun module stops sending


def gate_on(flags: int, t_ms: int) -> bool:
    on = True
    if flags & TONE_FLAG_CANT:
        on = on and ((t_ms // 62) & 1) == 0
    if flags & TONE_FLAG_LOST:
        on = on and (t_ms % 500) < 150
    return on


class ToneRenderer:
    def __init__(self, sample_rate: int) -> None:
        self.sr = sample_rate
        self.phase = 0.0
        self.samples = 0
        self.cur_l = 0.0
        self.cur_r = 0.0
        self.tone = Tone(440.0, 0.0, 0.0, 0)
        self.updated = 0.0
        self.lock = threading.Lock()

    def update(self, tone: Tone, now: float | None = None) -> None:
        with self.lock:
            self.tone = tone
            self.updated = time.monotonic() if now is None else now

    def render(self, frames: int, now: float | None = None) -> np.ndarray:
        now = time.monotonic() if now is None else now
        with self.lock:
            tone, updated = self.tone, self.updated
        t_ms = self.samples * 1000 // self.sr
        live = (now - updated) < STALE_S and gate_on(tone.flags, t_ms)
        tgt_l = tone.gain_l if live else 0.0
        tgt_r = tone.gain_r if live else 0.0

        inc = 2.0 * np.pi * tone.freq_hz / self.sr
        ph = self.phase + inc * np.arange(1, frames + 1)
        self.phase = float(ph[-1] % (2.0 * np.pi))
        s = np.sin(ph)
        ramp = np.linspace(0.0, 1.0, frames, endpoint=False)
        gl = self.cur_l + (tgt_l - self.cur_l) * ramp
        gr = self.cur_r + (tgt_r - self.cur_r) * ramp
        self.cur_l, self.cur_r = tgt_l, tgt_r
        self.samples += frames
        out = np.empty((frames, 2), np.float32)
        out[:, 0] = s * gl * 0.8
        out[:, 1] = s * gr * 0.8
        return out


class ToneSynth:
    def __init__(self, sample_rate: int, device: str = "") -> None:
        import sounddevice as sd

        self.renderer = ToneRenderer(sample_rate)
        self.stream = sd.OutputStream(
            samplerate=sample_rate, channels=2, dtype="float32", blocksize=256,
            latency="low", device=device or None, callback=self._callback)
        self.stream.start()

    def _callback(self, outdata, frames, _time, status) -> None:
        if status:
            log.debug("audio: %s", status)
        outdata[:] = self.renderer.render(frames)

    def update(self, tone: Tone) -> None:
        self.renderer.update(tone)

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()
