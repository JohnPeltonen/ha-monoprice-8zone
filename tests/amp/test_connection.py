import asyncio
import errno

import pytest

import amp as amp_module
from amp import AmpError, PortFailedError, PortInUseError, PortNotFoundError, open_amp
from fake_amp import ZONE_1, FakeTransport


def fake_opener(calls, replies):
    async def create_serial_connection(loop, protocol_factory, url, baudrate, **kwargs):
        calls.append((url, baudrate))
        protocol = protocol_factory()
        transport = FakeTransport(protocol, replies)
        protocol.connection_made(transport)
        return transport, protocol

    return create_serial_connection


async def test_open_amp_opens_the_port_at_9600(monkeypatch):
    calls = []
    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", fake_opener(calls, [ZONE_1]))
    amp = await open_amp("/dev/ttyUSB0")
    assert calls == [("/dev/ttyUSB0", 9600)]
    assert (await amp.query_zone(1)).zone == 1


@pytest.mark.parametrize(
    ("error_number", "error_type"),
    [
        (errno.EBUSY, PortInUseError),
        (errno.ENOENT, PortNotFoundError),
        (errno.ENODEV, PortNotFoundError),
        (errno.ENXIO, PortNotFoundError),
    ],
)
async def test_open_amp_port_errors(monkeypatch, error_number, error_type):
    async def create_serial_connection(*args, **kwargs):
        raise OSError(error_number, "test")

    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", create_serial_connection)
    with pytest.raises(error_type):
        await open_amp("/dev/ttyUSB0")


async def test_open_amp_other_errors_pass_through(monkeypatch):
    async def create_serial_connection(*args, **kwargs):
        raise OSError(errno.EACCES, "test")

    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", create_serial_connection)
    with pytest.raises(PermissionError):
        await open_amp("/dev/ttyUSB0")


async def test_close_closes_the_port(make_amp):
    amp, transport = make_amp()
    await amp.close()
    assert transport.closed
    assert transport.protocol.closed.done()


async def test_command_after_port_failure(make_amp):
    amp, transport = make_amp(ZONE_1)
    transport.protocol.connection_lost(OSError(errno.EIO, "device disconnected"))
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)
    assert transport.writes == []


async def test_port_failure_during_a_read(make_amp):
    amp, transport = make_amp(None)
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected"))
    started = loop.time()
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)
    assert loop.time() - started < 0.5  # well before the 1-second status timeout


async def test_write_failure_is_a_port_failure(make_amp):
    amp, transport = make_amp(ZONE_1)
    transport.write_error = OSError(errno.EIO, "device disconnected or in use by another process")
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)


async def test_command_after_close_is_not_a_port_failure(make_amp):
    amp, _ = make_amp(ZONE_1)
    await amp.close()
    with pytest.raises(AmpError) as caught:
        await amp.query_zone(1)
    assert not isinstance(caught.value, PortFailedError)
