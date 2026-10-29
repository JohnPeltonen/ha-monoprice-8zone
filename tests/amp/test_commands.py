import logging

import pytest

import amp as amp_module
from amp import VOLUME
from fake_amp import ZONE_1_VOLUME_20


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
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.writes == [b"<11VO20\r", b"?11\r"]
    assert "No # after" in caplog.text


async def test_set_value_rejects_bad_values(make_amp):
    amp, transport = make_amp()
    with pytest.raises(ValueError):
        await amp.set_value(1, VOLUME, 39)
    assert transport.writes == []
