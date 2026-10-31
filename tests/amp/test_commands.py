import asyncio
import errno
import logging

import pytest

import amp as amp_module
from amp import BALANCE, BASS, DO_NOT_DISTURB, MUTE, POWER, SOURCE, TREBLE, VOLUME, PortFailedError
from fake_amp import ZONE_1, ZONE_1_DND, ZONE_1_DND_VOLUME_20, ZONE_1_OFF_DND, ZONE_1_VOLUME_20, ZONE_2

LIFTED = [b"<11VO20\r", b"?11\r", b"<11DT00\r", b"<11VO20\r", b"<11DT01\r", b"?11\r"]


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


async def test_ignored_command_lifts_do_not_disturb(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", b"#", b"#", ZONE_1_DND_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert (status.volume, status.do_not_disturb) == (20, True)
    assert transport.writes == LIFTED


async def test_ignored_power_command_lifts_do_not_disturb(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_OFF_DND, b"#", b"#", b"#", ZONE_1_DND)
    status = await amp.set_value(1, POWER, 1)
    assert (status.power, status.do_not_disturb) == (True, True)
    assert transport.writes == [b"<11PR01\r", b"?11\r", b"<11DT00\r", b"<11PR01\r", b"<11DT01\r", b"?11\r"]


@pytest.mark.parametrize(
    ("field", "value"),
    [(VOLUME, 10), (POWER, 1), (MUTE, 0), (TREBLE, 7), (BASS, 7), (BALANCE, 10), (SOURCE, 2)],
)
async def test_command_that_took_leaves_do_not_disturb_alone(make_amp, field, value):
    amp, transport = make_amp(b"#", ZONE_1_DND)
    await amp.set_value(1, field, value)
    assert len(transport.writes) == 2  # the command and one query


async def test_do_not_disturb_commands_are_never_retried(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND)  # the status is late to show it off
    await amp.set_value(1, DO_NOT_DISTURB, 0)
    assert transport.writes == [b"<11DT00\r", b"?11\r"]


async def test_lifting_works_without_hash(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "SET_REPLY_TIMEOUT", 0.05)
    amp, transport = make_amp(None, ZONE_1_DND, None, None, None, ZONE_1_DND_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.writes == LIFTED


async def test_query_waits_until_do_not_disturb_is_back_on(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", b"#", b"#", ZONE_1_DND_VOLUME_20, ZONE_1_DND_VOLUME_20)
    await asyncio.gather(amp.set_value(1, VOLUME, 20), amp.query_zone(1))
    assert transport.writes == [*LIFTED, b"?11\r"]


@pytest.mark.parametrize(
    ("writes", "replies"),
    [
        (3, [b"#", ZONE_1_DND, None, b"#"]),  # still waiting for the # after Do Not Disturb goes off
        (4, [b"#", ZONE_1_DND, b"#", None, b"#"]),  # still waiting for the # after the second try
    ],
)
async def test_do_not_disturb_goes_back_on_when_cancelled(make_amp, writes, replies):
    amp, transport = make_amp(*replies)
    task = asyncio.create_task(amp.set_value(1, VOLUME, 20))
    while len(transport.writes) < writes and not task.done():  # before the change, the task just finishes
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes[-1] == b"<11DT01\r"


async def test_port_failure_while_do_not_disturb_is_lifted(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", None)
    asyncio.get_running_loop().call_later(
        0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected")
    )
    with pytest.raises(PortFailedError):
        await amp.set_value(1, VOLUME, 20)


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
