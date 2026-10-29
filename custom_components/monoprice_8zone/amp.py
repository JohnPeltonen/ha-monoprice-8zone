"""Talk to a Monoprice 44518 amp over RS-232.

This module must not import homeassistant: its tests run on Windows, where Home Assistant can't.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

POWER = "PR"
MUTE = "MU"
DO_NOT_DISTURB = "DT"
VOLUME = "VO"
TREBLE = "TR"
BASS = "BS"
BALANCE = "BL"
SOURCE = "CH"

FIELD_RANGES: dict[str, tuple[int, int]] = {
    POWER: (0, 1),
    MUTE: (0, 1),
    DO_NOT_DISTURB: (0, 1),
    VOLUME: (0, 38),
    TREBLE: (0, 14),
    BASS: (0, 14),
    BALANCE: (0, 20),
    SOURCE: (1, 6),
}

# A status line for one of the MASTER amp's zones (11 to 18), up to the "#" that ends it.
# The zone and source names between the digits and the "#" are ignored.
STATUS_PATTERN = re.compile(rb">1([1-8])(\d{20})[^#]*#")

# Seconds to wait for a complete status reply. One takes about 50 ms to arrive at 9600 baud.
STATUS_TIMEOUT = 1.0


@dataclass(frozen=True)
class ZoneStatus:
    zone: int
    page: bool
    power: bool
    mute: bool
    do_not_disturb: bool
    volume: int
    treble: int
    bass: int
    balance: int
    source: int
    keypad: bool


class AmpError(Exception):
    """Something went wrong talking to the amp."""


class AmpTimeoutError(AmpError):
    """The amp didn't answer in time."""


class BadReplyError(AmpError):
    """The amp answered about a different zone."""


class PortFailedError(AmpError):
    """The serial port failed or disappeared while in use."""


def status_command(zone: int) -> bytes:
    return b"?%d\r" % _zone_id(zone)


def set_command(zone: int, field: str, value: int) -> bytes:
    if field not in FIELD_RANGES:
        raise ValueError(f"Unknown field {field!r}")
    low, high = FIELD_RANGES[field]
    if not low <= value <= high:
        raise ValueError(f"{field} must be {low} to {high}, not {value!r}")
    return b"<%d%s%02d\r" % (_zone_id(zone), field.encode("ascii"), value)


def find_status(data: bytes | bytearray) -> ZoneStatus | None:
    """Return the first complete status reply in data, skipping anything before it."""
    match = STATUS_PATTERN.search(data)
    if match is None:
        return None
    digits = match.group(2)
    page, power, mute, dnd, volume, treble, bass, balance, source, keypad = (
        int(digits[i : i + 2]) for i in range(0, 20, 2)
    )
    return ZoneStatus(
        zone=int(match.group(1)),
        page=bool(page),
        power=bool(power),
        mute=bool(mute),
        do_not_disturb=bool(dnd),
        volume=volume,
        treble=treble,
        bass=bass,
        balance=balance,
        source=source,
        keypad=bool(keypad),
    )


class AmpProtocol(asyncio.Protocol):
    """Collects what the amp sends, and wakes up whoever is waiting for it."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.lost = False
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._changed = asyncio.Event()

    def data_received(self, data: bytes) -> None:
        logger.debug("Read %r", data)
        self.buffer += data
        self._changed.set()

    def connection_lost(self, exc: Exception | None) -> None:
        logger.debug("Serial port closed: %r", exc)
        self.lost = True
        if not self.closed.done():
            self.closed.set_result(None)
        self._changed.set()

    async def wait_for_change(self, timeout: float) -> None:
        """Wait until bytes arrive or the port closes, or until timeout seconds pass."""
        self._changed.clear()
        try:
            async with asyncio.timeout(timeout):
                await self._changed.wait()
        except TimeoutError:
            pass


class Amp:
    """One connection to the amp. Commands run one at a time."""

    def __init__(self, transport: asyncio.Transport, protocol: AmpProtocol) -> None:
        self._transport = transport
        self._protocol = protocol
        self._lock = asyncio.Lock()

    async def query_zone(self, zone: int) -> ZoneStatus:
        async with self._lock:
            return await self._query_locked(zone)

    async def query_zones(self, zones: Iterable[int]) -> dict[int, ZoneStatus | None]:
        """Query each zone in turn. A zone that doesn't answer gets None. If none answer, raise."""
        results: dict[int, ZoneStatus | None] = {}
        for zone in zones:
            try:
                results[zone] = await self.query_zone(zone)
            except (AmpTimeoutError, BadReplyError) as exc:
                logger.debug("Zone %d didn't answer: %s", zone, exc)
                results[zone] = None
        if results and all(status is None for status in results.values()):
            raise AmpTimeoutError("No zone answered")
        return results

    async def _query_locked(self, zone: int) -> ZoneStatus:
        self._send(status_command(zone))
        await self._read_until(lambda buffer: find_status(buffer) is not None, STATUS_TIMEOUT)
        status = find_status(self._protocol.buffer)
        if status.zone != zone:
            raise BadReplyError(f"Asked about zone {zone}, got a reply for zone {status.zone}")
        return status

    def _send(self, data: bytes) -> None:
        if self._protocol.lost:
            raise PortFailedError("The serial port is gone")
        self._protocol.buffer.clear()  # throw away anything left over from an earlier command
        logger.debug("Write %r", data)
        self._transport.write(data)

    async def _read_until(self, done: Callable[[bytearray], bool], timeout: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not done(self._protocol.buffer):
            if self._protocol.lost:
                raise PortFailedError("The serial port closed while waiting for a reply")
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise AmpTimeoutError(
                    f"No complete reply within {timeout} s, received {bytes(self._protocol.buffer)!r}"
                )
            await self._protocol.wait_for_change(remaining)


def _zone_id(zone: int) -> int:
    if not 1 <= zone <= 8:
        raise ValueError(f"Zone must be 1 to 8, not {zone!r}")
    return 10 + zone
