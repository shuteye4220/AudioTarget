"""Speech output through espeak-ng (one utterance at a time, interruptible)."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil

log = logging.getLogger(__name__)

MAX_CHARS = 400
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")


def clean(text: str) -> str:
    """Make arbitrary text (e.g. Bluetooth device names) safe and short to speak."""
    return _CTRL.sub(" ", text).strip()[:MAX_CHARS]


class Speaker:
    def __init__(self, voice: str = "en-us", rate: int = 175, command: str = "espeak-ng") -> None:
        self.voice = voice
        self.rate = rate
        self.command = shutil.which(command) or command
        self.proc: asyncio.subprocess.Process | None = None
        self.last = ""

    def cancel(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass

    async def say(self, text: str, interrupt: bool = True) -> None:
        text = clean(text)
        if not text:
            return
        if interrupt:
            self.cancel()
        elif self.proc is not None:
            await self.proc.wait()
        self.last = text
        log.info("say: %s", text)
        try:
            self.proc = await asyncio.create_subprocess_exec(
                self.command, "-v", self.voice, "-s", str(self.rate), "--", text,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
        except OSError as e:
            log.error("speech unavailable: %s", e)
            self.proc = None

    async def finish(self) -> None:
        if self.proc is not None:
            await self.proc.wait()

    async def repeat(self) -> None:
        if self.last:
            await self.say(self.last)
