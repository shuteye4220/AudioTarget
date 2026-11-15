"""Links to the gun module: wired serial and Bluetooth LE (Nordic UART Service).

Both carry the same line protocol and can run at once; outgoing lines go to
every link that's up.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable

from .protocol import LineAssembler

log = logging.getLogger(__name__)

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # we write here
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # nRF notifies here

LineHandler = Callable[[str, str], None]  # (source, line)


class SerialLink:
    name = "serial"

    def __init__(self, port: str, baud: int, on_line: LineHandler) -> None:
        self.port, self.baud, self.on_line = port, baud, on_line
        self.ser = None
        self.asm = LineAssembler()
        self._lost = asyncio.Event()

    @property
    def up(self) -> bool:
        return self.ser is not None

    async def run(self) -> None:
        import serial

        loop = asyncio.get_running_loop()
        while True:
            if not os.path.exists(self.port):
                await asyncio.sleep(2.0)
                continue
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=0, write_timeout=0)
            except (OSError, serial.SerialException) as e:
                log.warning("serial %s: %s", self.port, e)
                await asyncio.sleep(2.0)
                continue
            log.info("serial link open on %s", self.port)
            self._lost.clear()
            loop.add_reader(self.ser.fileno(), self._readable)
            await self._lost.wait()
            loop.remove_reader(self.ser.fileno())
            self.ser.close()
            self.ser = None
            await asyncio.sleep(1.0)

    def _readable(self) -> None:
        try:
            data = self.ser.read(256)
        except OSError:
            self._lost.set()
            return
        for line in self.asm.feed(data):
            self.on_line(self.name, line)

    def send(self, data: bytes) -> None:
        if self.ser is None:
            return
        try:
            self.ser.write(data)
        except Exception:  # write timeout (buffer full) or unplugged: drop the line
            log.debug("serial write dropped")


class BleLink:
    name = "ble"

    def __init__(self, address: str, device_name: str, on_line: LineHandler) -> None:
        self.address = address.strip().upper()
        self.device_name = device_name
        self.on_line = on_line
        self.client = None
        self.asm = LineAssembler()
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)
        self._ready = False

    @property
    def up(self) -> bool:
        return self._ready

    async def _find(self):
        from bleak import BleakScanner

        if self.address:
            return await BleakScanner.find_device_by_address(self.address, timeout=10.0)

        def match(dev, adv) -> bool:
            uuids = [u.lower() for u in (adv.service_uuids or [])]
            return adv.local_name == self.device_name and NUS_SERVICE in uuids

        return await BleakScanner.find_device_by_filter(match, timeout=10.0)

    async def run(self) -> None:
        from bleak import BleakClient
        from bleak.exc import BleakError

        backoff = 1.0
        while True:
            try:
                dev = await self._find()
                if dev is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                    continue
                if not self.address:
                    log.warning("connected to %s by name; set link.ble_address=%s to pin it",
                                self.device_name, dev.address)
                disconnected = asyncio.Event()
                async with BleakClient(dev, disconnected_callback=lambda _c: disconnected.set()) as client:
                    self.client = client
                    try:
                        # Bonding: the gun module ignores unencrypted links.
                        await client.pair()
                    except (BleakError, NotImplementedError) as e:
                        log.debug("pair(): %s (already bonded?)", e)
                    await client.start_notify(NUS_TX, self._notify)
                    self._ready = True
                    backoff = 1.0
                    log.info("BLE link up to %s", dev.address)
                    writer = asyncio.create_task(self._writer(client))
                    await disconnected.wait()
                    writer.cancel()
            except (BleakError, asyncio.TimeoutError, OSError) as e:
                log.warning("BLE: %s", e)
            finally:
                self._ready = False
                self.client = None
                self.asm = LineAssembler()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def _notify(self, _char, data: bytearray) -> None:
        for line in self.asm.feed(bytes(data)):
            self.on_line(self.name, line)

    async def _writer(self, client) -> None:
        while True:
            data = await self.queue.get()
            mtu = 20
            try:
                mtu = client.services.get_characteristic(NUS_RX).max_write_without_response_size
            except Exception:
                pass
            try:
                for i in range(0, len(data), mtu):
                    await client.write_gatt_char(NUS_RX, data[i:i + mtu], response=False)
            except Exception as e:
                log.debug("BLE write failed: %s", e)

    def send(self, data: bytes) -> None:
        if not self._ready:
            return
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            # Stale camera data is worse than none: drop the oldest.
            self.queue.get_nowait()
            self.queue.put_nowait(data)


class LinkManager:
    def __init__(self, links: list) -> None:
        self.links = links

    async def run(self) -> None:
        await asyncio.gather(*(link.run() for link in self.links))

    def send(self, data: bytes) -> None:
        for link in self.links:
            link.send(data)

    @property
    def any_up(self) -> bool:
        return any(link.up for link in self.links)
