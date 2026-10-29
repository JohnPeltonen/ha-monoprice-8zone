"""Talk to a Monoprice 44518 amp over RS-232.

This module must not import homeassistant: its tests run on Windows, where Home Assistant can't.
"""

import asyncio
import errno
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import serialx

logger = logging.getLogger(__name__)

BAUD_RATE = 9600

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
# Seconds to wait for the "#" the amp sends after a set command.
SET_REPLY_TIMEOUT = 0.5
# A raw command collects what the amp sends until it has been quiet for RAW_QUIET_GAP seconds,
# or until RAW_TIMEOUT seconds have passed.
RAW_QUIET_GAP = 0.3
RAW_TIMEOUT = 2.0


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


class PortFailedError(AmpError):
    """The serial port failed or disappeared while in use."""


class PortInUseError(AmpError):
    """Another program or integration has the serial port open."""


class PortNotFoundError(AmpError):
    """The serial port doesn't exist."""


def status_command(zone: int) -> bytes:
    return b"?%d\r" % _zone_id(zone)


def set_command(zone: int, field: str, value: int) -> bytes:
    if field not in FIELD_RANGES:
        raise ValueError(f"Unknown field {field!r}")
    low, high = FIELD_RANGES[field]
    if not low <= value <= high:
        raise ValueError(f"{field} must be {low} to {high}, not {value!r}")
    return b"<%d%s%02d\r" % (_zone_id(zone), field.encode("ascii"), value)


def find_status(data: bytes | bytearray, zone: int | None = None) -> ZoneStatus | None:
    """Return the first complete status reply in data, for zone if given, skipping anything else."""
    for match in STATUS_PATTERN.finditer(data):
        found_zone = int(match.group(1))
        if zone is not None and found_zone != zone:
            continue
        digits = match.group(2)
        page, power, mute, dnd, volume, treble, bass, balance, source, keypad = (
            int(digits[i : i + 2]) for i in range(0, 20, 2)
        )
        return ZoneStatus(
            zone=found_zone,
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
    return None


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

    async def wait_for_change(self, timeout: float) -> bool:
        """Wait until bytes arrive or the port closes. Return False if timeout seconds pass first."""
        self._changed.clear()
        try:
            async with asyncio.timeout(timeout):
                await self._changed.wait()
        except TimeoutError:
            return False
        return True


class Amp:
    """One connection to the amp. Commands run one at a time."""

    def __init__(self, transport: asyncio.Transport, protocol: AmpProtocol) -> None:
        self._transport = transport
        self._protocol = protocol
        self._lock = asyncio.Lock()
        self._closed = False

    async def close(self) -> None:
        """Close the port, after any command in progress has finished."""
        async with self._lock:
            self._closed = True
            self._transport.close()
            await self._protocol.closed

    async def query_zone(self, zone: int) -> ZoneStatus:
        async with self._lock:
            return await self._query_locked(zone)

    async def query_zones(self, zones: Iterable[int]) -> dict[int, ZoneStatus | None]:
        """Query each zone in turn. A zone that doesn't answer gets None. If none answer, raise."""
        results: dict[int, ZoneStatus | None] = {}
        for zone in zones:
            try:
                results[zone] = await self.query_zone(zone)
            except AmpTimeoutError as exc:
                logger.debug("Zone %d didn't answer: %s", zone, exc)
                results[zone] = None
        if results and all(status is None for status in results.values()):
            raise AmpTimeoutError("No zone answered")
        return results

    async def set_value(self, zone: int, field: str, value: int) -> ZoneStatus:
        """Change one setting, then return the zone's status as the amp reports it."""
        command = set_command(zone, field, value)
        async with self._lock:
            self._send(command)
            try:
                await self._read_until(lambda buffer: b"#" in buffer, SET_REPLY_TIMEOUT)
            except AmpTimeoutError:
                logger.debug("No # after %r", command)
            return await self._query_locked(zone)

    async def send_raw(self, command: str) -> bytes:
        """Send one ? or < command and return whatever the amp sends back, which may be nothing."""
        # A CR or LF inside the text would start a second command, and a bare number like
        # 19200 changes the amp's baud rate until it's power cycled.
        if command[:1] not in ("?", "<") or not command.isprintable():
            raise ValueError("Send one command that starts with ? or <")
        data = command.encode("ascii") + b"\r"
        async with self._lock:
            self._send(data)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + RAW_TIMEOUT
            while True:
                if self._protocol.lost:
                    raise PortFailedError("The serial port closed while waiting for a reply")
                wait = deadline - loop.time()
                if self._protocol.buffer:
                    wait = min(wait, RAW_QUIET_GAP)
                if wait <= 0 or not await self._protocol.wait_for_change(wait):
                    return bytes(self._protocol.buffer)

    async def _query_locked(self, zone: int) -> ZoneStatus:
        self._send(status_command(zone))
        # A late reply about another zone can arrive first. find_status skips it and keeps looking.
        await self._read_until(lambda buffer: find_status(buffer, zone) is not None, STATUS_TIMEOUT)
        return find_status(self._protocol.buffer, zone)

    def _send(self, data: bytes) -> None:
        # A deliberate close isn't a port failure: the integration reloads itself on PortFailedError.
        if self._closed:
            raise AmpError("The connection is closed")
        if self._protocol.lost:
            raise PortFailedError("The serial port is gone")
        self._protocol.buffer.clear()  # throw away anything left over from an earlier command
        logger.debug("Write %r", data)
        try:
            self._transport.write(data)
        except OSError as exc:
            raise PortFailedError(f"Writing to the serial port failed: {exc}") from exc

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


async def open_amp(port: str) -> Amp:
    """Open the port at 9600 baud. serialx's defaults give 8N1, no flow control and exclusive use."""
    try:
        transport, protocol = await serialx.create_serial_connection(
            asyncio.get_running_loop(), AmpProtocol, port, baudrate=BAUD_RATE
        )
    except OSError as exc:
        if exc.errno == errno.EBUSY:
            raise PortInUseError(f"{port} is in use by another program or integration") from exc
        if exc.errno in (errno.ENOENT, errno.ENODEV, errno.ENXIO):
            raise PortNotFoundError(f"{port} doesn't exist") from exc
        raise
    return Amp(transport, protocol)


def _zone_id(zone: int) -> int:
    if not 1 <= zone <= 8:
        raise ValueError(f"Zone must be 1 to 8, not {zone!r}")
    return 10 + zone
