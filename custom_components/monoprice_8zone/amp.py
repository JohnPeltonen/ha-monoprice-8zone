"""Talk to a Monoprice 44518 amp over RS-232.

This module must not import homeassistant: its tests run on Windows, where Home Assistant can't.
"""

import logging
import re
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


def status_command(zone: int) -> bytes:
    return b"?%d\r" % _zone_id(zone)


def set_command(zone: int, field: str, value: int) -> bytes:
    if field not in FIELD_RANGES:
        raise ValueError(f"Unknown field {field!r}")
    low, high = FIELD_RANGES[field]
    if not low <= value <= high:
        raise ValueError(f"{field} must be {low} to {high}, not {value!r}")
    return b"<%d%s%02d\r" % (_zone_id(zone), field.encode("ascii"), value)


def find_status(data: bytes) -> ZoneStatus | None:
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


def _zone_id(zone: int) -> int:
    if not 1 <= zone <= 8:
        raise ValueError(f"Zone must be 1 to 8, not {zone!r}")
    return 10 + zone
