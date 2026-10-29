import asyncio
import errno
import logging

import pytest

import amp as amp_module
from amp import VOLUME, PortFailedError
from fake_amp import ZONE_1, ZONE_1_VOLUME_20, ZONE_2


async def test_set_value_waits_for_hash_then_queries(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.log == [
        ("write", b"<11VO20\r"), ("read", b"#"), ("write", b"?11\r"), ("read", ZONE_1_VOLUME_20),
    ]


async def test_set_value_without_hash_still_queries(make_amp, monkeypatch, caplog):
    monkeypatch.setattr(amp_module, "SET_REPLY_TIMEOUT", 0.05)
    caplog.set_level(logging.DEBUG)
    amp, transport = make_amp(None, ZONE_1_VOLUME_20)
    loop = asyncio.get_running_loop()
    started = loop.time()
    status = await amp.set_value(1, VOLUME, 20)
    assert loop.time() - started < 0.5  # waited SET_REPLY_TIMEOUT, not the 1-second STATUS_TIMEOUT
    assert status.volume == 20
    assert transport.writes == [b"<11VO20\r", b"?11\r"]
    assert "No # after" in caplog.text


async def test_set_value_rejects_bad_values(make_amp):
    amp, transport = make_amp()
    with pytest.raises(ValueError):
        await amp.set_value(1, VOLUME, 39)
    assert transport.writes == []


async def test_send_raw_returns_everything_until_quiet(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, transport = make_amp([ZONE_1[:-1], b"#"])
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await amp.send_raw("?11") == ZONE_1
    assert loop.time() - started < 1.0  # stopped at the quiet gap, not the 2-second limit
    assert transport.writes == [b"?11\r"]


async def test_send_raw_returns_nothing_when_the_amp_is_silent(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_TIMEOUT", 0.1)
    amp, _ = make_amp(None)
    assert await amp.send_raw("<11MU01") == b""


async def test_send_raw_collects_past_a_hash(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, _ = make_amp([ZONE_1, ZONE_2])  # like the reply to ?10: one zone after another
    assert await amp.send_raw("?10") == ZONE_1 + ZONE_2


async def test_send_raw_waits_for_a_slow_first_byte(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, transport = make_amp(None)
    asyncio.get_running_loop().call_later(0.2, transport.protocol.data_received, ZONE_1)
    assert await amp.send_raw("?11") == ZONE_1


@pytest.mark.parametrize("command", ["19200", "", "?11é", "?11\r19200", "?11\n"])
async def test_send_raw_rejects_other_commands(make_amp, command):
    amp, transport = make_amp()
    with pytest.raises(ValueError):
        await amp.send_raw(command)
    assert transport.writes == []


async def test_send_raw_port_failure(make_amp):
    amp, transport = make_amp(None)
    asyncio.get_running_loop().call_later(
        0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected")
    )
    with pytest.raises(PortFailedError):
        await amp.send_raw("?11")
