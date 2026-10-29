import asyncio

import pytest

import amp as amp_module
from amp import AmpTimeoutError
from fake_amp import ZONE_1, ZONE_1_VOLUME_20, ZONE_2, ZONE_5


async def test_query_zone_returns_status(make_amp):
    amp, transport = make_amp(ZONE_1)
    status = await amp.query_zone(1)
    assert (status.zone, status.volume, status.source) == (1, 10, 2)
    assert transport.writes == [b"?11\r"]


async def test_query_zone_skips_an_echo(make_amp):
    amp, _ = make_amp(b"?11\r\r\n#" + ZONE_1)
    assert (await amp.query_zone(1)).volume == 10


async def test_query_zone_reply_in_pieces(make_amp):
    amp, _ = make_amp([b">1100", b"0100001007071002", b"00 Zone1    Sou", b"rce02\r\n", b"#"])
    assert (await amp.query_zone(1)).volume == 10


async def test_query_zone_times_out(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(None)
    with pytest.raises(AmpTimeoutError):
        await amp.query_zone(1)


async def test_query_zone_discards_stray_bytes(make_amp):
    amp, transport = make_amp(ZONE_1_VOLUME_20)
    transport.protocol.data_received(ZONE_1)  # a late reply to an earlier query of the same zone
    assert (await amp.query_zone(1)).volume == 20


async def test_query_zone_skips_another_zones_reply(make_amp):
    amp, _ = make_amp([ZONE_5, ZONE_1])  # a late reply about zone 5 arrives first
    assert (await amp.query_zone(1)).zone == 1


async def test_query_zones_survives_a_late_reply(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(None, [ZONE_1, ZONE_2])  # zone 1's reply comes too late, during zone 2's query
    result = await amp.query_zones([1, 2])
    assert result[1] is None
    assert result[2].zone == 2


async def test_commands_wait_their_turn(make_amp):
    amp, transport = make_amp(ZONE_1, ZONE_2)
    await asyncio.gather(amp.query_zone(1), amp.query_zone(2))
    assert transport.log == [("write", b"?11\r"), ("read", ZONE_1), ("write", b"?12\r"), ("read", ZONE_2)]


async def test_query_zones_marks_silent_zones(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(ZONE_1, None)
    result = await amp.query_zones([1, 2])
    assert result[1].zone == 1
    assert result[2] is None


async def test_query_zones_fails_when_no_zone_answers(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(None, None)
    with pytest.raises(AmpTimeoutError):
        await amp.query_zones([1, 2])
