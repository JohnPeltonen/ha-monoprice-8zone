"""Stand-ins for the amp, shared by the tests."""

import asyncio

# The capture in PROTOCOL.md. The others change its values.
ZONE_1 = b">1100010000100707100200 Zone1    Source02\r\n#"
ZONE_1_VOLUME_20 = b">1100010000200707100200 Zone1    Source02\r\n#"
ZONE_2 = b">1200010000150707100100 Zone2    Source01\r\n#"
ZONE_5 = b">1500010000050707100100 Zone5    Source01\r\n#"


class FakeTransport(asyncio.Transport):
    """Answers each write with the next scripted reply: bytes, a list of pieces, or None for silence."""

    def __init__(self, protocol: asyncio.Protocol, replies: list[bytes | list[bytes] | None]) -> None:
        super().__init__()
        self.protocol = protocol
        self.replies = list(replies)
        self.writes: list[bytes] = []
        self.log: list[tuple[str, bytes]] = []
        self.closed = False
        # serialx's write() raises like this when the port has just failed.
        self.write_error: OSError | None = None

    def write(self, data: bytes) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(bytes(data))
        self.log.append(("write", bytes(data)))
        reply = self.replies.pop(0) if self.replies else None
        if reply is None:
            return
        pieces = [reply] if isinstance(reply, bytes) else list(reply)
        asyncio.get_running_loop().call_soon(self._deliver, pieces)

    def _deliver(self, pieces: list[bytes]) -> None:
        # One piece per pass of the event loop, so a reader wakes up between pieces.
        piece = pieces.pop(0)
        self.log.append(("read", piece))
        self.protocol.data_received(piece)
        if pieces:
            asyncio.get_running_loop().call_soon(self._deliver, pieces)

    def close(self) -> None:
        self.closed = True
        asyncio.get_running_loop().call_soon(self.protocol.connection_lost, None)

    def is_closing(self) -> bool:
        return self.closed
