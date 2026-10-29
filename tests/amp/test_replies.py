import pytest

from amp import BALANCE, DO_NOT_DISTURB, SOURCE, VOLUME, ZoneStatus, find_status, set_command, status_command
from fake_amp import ZONE_1

CAPTURED_STATUS = ZoneStatus(
    zone=1, page=False, power=True, mute=False, do_not_disturb=False,
    volume=10, treble=7, bass=7, balance=10, source=2, keypad=False,
)


def test_status_command():
    assert status_command(1) == b"?11\r"
    assert status_command(8) == b"?18\r"


@pytest.mark.parametrize("zone", [0, 9])
def test_status_command_rejects_other_zones(zone):
    with pytest.raises(ValueError):
        status_command(zone)


def test_set_command():
    assert set_command(1, VOLUME, 10) == b"<11VO10\r"
    assert set_command(5, DO_NOT_DISTURB, 1) == b"<15DT01\r"
    assert set_command(2, SOURCE, 6) == b"<12CH06\r"


@pytest.mark.parametrize(
    ("zone", "field", "value"),
    [(1, VOLUME, 39), (1, VOLUME, -1), (1, SOURCE, 0), (1, BALANCE, 21), (1, "XX", 1), (9, VOLUME, 10)],
)
def test_set_command_rejects_bad_input(zone, field, value):
    with pytest.raises(ValueError):
        set_command(zone, field, value)


def test_find_status_parses_captured_reply():
    assert find_status(ZONE_1) == CAPTURED_STATUS


def test_find_status_reads_each_number_in_its_place():
    # Every number differs, so two fields read in the wrong order would show.
    assert find_status(b">1400010000210312170500\r\n#") == ZoneStatus(
        zone=4, page=False, power=True, mute=False, do_not_disturb=False,
        volume=21, treble=3, bass=12, balance=17, source=5, keypad=False,
    )


@pytest.mark.parametrize(
    ("digits", "flag"),
    [
        (b"01000000100707100200", "page"),
        (b"00010000100707100200", "power"),
        (b"00000100100707100200", "mute"),
        (b"00000001100707100200", "do_not_disturb"),
        (b"00000000100707100201", "keypad"),
    ],
)
def test_find_status_reads_each_flag_in_its_place(digits, flag):
    status = find_status(b">11" + digits + b"\r\n#")
    flags = {name: getattr(status, name) for name in ("page", "power", "mute", "do_not_disturb", "keypad")}
    assert flags == {name: name == flag for name in flags}


def test_find_status_skips_an_echo():
    assert find_status(b"?11\r\r\n#" + ZONE_1) == CAPTURED_STATUS


def test_find_status_needs_the_closing_hash():
    assert find_status(ZONE_1[:-1]) is None


def test_find_status_ignores_slave_zones():
    assert find_status(b">2100010000100707100200\r\n#") is None


def test_find_status_ignores_odd_bytes_in_names():
    assert find_status(b">1100010000100707100200 K\xfcche\x00  Source02\r\n#") == CAPTURED_STATUS
