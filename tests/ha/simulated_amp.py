"""A stand-in 44518 for the HA tests. It answers commands byte for byte, and locks its port as serialx does."""

import asyncio
import errno
import os
import re

# A command as the integration writes it: ?1z, or <1zPPuu.
COMMAND = re.compile(rb"([?<])1([1-8])(?:([A-Z]{2})(\d{2}))?\r")
# The fields of a status reply, in PROTOCOL.md's order.
FIELDS = ("PA", "PR", "MU", "DT", "VO", "TR", "BS", "BL", "CH", "LS")


class SimulatedAmp:
    def __init__(self) -> None:
        # Every zone starts at the values in the PROTOCOL.md capture.
        self.zones = {
            zone: {"PA": 0, "PR": 1, "MU": 0, "DT": 0, "VO": 10, "TR": 7, "BS": 7, "BL": 10, "CH": 2, "LS": 0}
            for zone in range(1, 9)
        }
        self.silent_zones: set[int] = set()
        self.open_error: OSError | None = None
        self.connections: list[SimulatedConnection] = []
        self.writes: list[bytes] = []

    async def create_serial_connection(self, loop, protocol_factory, url, baudrate, **kwargs):
        """Stands in for serialx.create_serial_connection."""
        if self.open_error is not None:
            raise self.open_error
        device = os.path.realpath(url)
        if any(connection.device == device and not connection.closed for connection in self.connections):
            raise OSError(errno.EBUSY, f"{url} is already locked by another process")
        protocol = protocol_factory()
        connection = SimulatedConnection(self, protocol, url, device)
        self.connections.append(connection)
        protocol.connection_made(connection)
        return connection, protocol

    def reply(self, data: bytes) -> bytes | None:
        """What the amp sends back for one command, or None for nothing."""
        match = COMMAND.fullmatch(data)
        if match is None or int(match[2]) in self.silent_zones:
            return None
        zone = int(match[2])
        state = self.zones[zone]
        if match[1] == b"<":
            state[match[3].decode()] = int(match[4])
            return b"#"
        digits = "".join(f"{state[field]:02d}" for field in FIELDS)
        return f">1{zone}{digits} Zone{zone}    Source{state['CH']:02d}\r\n#".encode()


class SimulatedConnection(asyncio.Transport):
    def __init__(self, amp: SimulatedAmp, protocol: asyncio.Protocol, port: str, device: str) -> None:
        super().__init__()
        self.amp = amp
        self.protocol = protocol
        self.port = port
        self.device = device
        self.closed = False

    def write(self, data: bytes) -> None:
        self.amp.writes.append(bytes(data))
        reply = self.amp.reply(bytes(data))
        if reply is not None:
            asyncio.get_running_loop().call_soon(self.protocol.data_received, reply)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            asyncio.get_running_loop().call_soon(self.protocol.connection_lost, None)

    def is_closing(self) -> bool:
        return self.closed

    def unplug(self) -> None:
        """The USB adapter is pulled out."""
        self.closed = True
        self.protocol.connection_lost(OSError(errno.EIO, "device disconnected"))
