import sys
from pathlib import Path

import pytest

# The package's __init__.py imports homeassistant from Phase 2 on, so tests load amp.py on its own.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "custom_components" / "monoprice_8zone"))

from amp import Amp, AmpProtocol
from fake_amp import FakeTransport


@pytest.fixture
def make_amp():
    def make(*replies: bytes | list[bytes] | None) -> tuple[Amp, FakeTransport]:
        protocol = AmpProtocol()
        transport = FakeTransport(protocol, list(replies))
        protocol.connection_made(transport)
        return Amp(transport, protocol), transport

    return make
