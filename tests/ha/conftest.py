from collections.abc import Awaitable, Callable

import pytest
import serialx
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.monoprice_8zone import amp as amp_module
from custom_components.monoprice_8zone.const import CONF_SOURCES, CONF_ZONES, DOMAIN
from simulated_amp import SimulatedAmp


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load the integration from custom_components."""


@pytest.fixture
def amp(monkeypatch: pytest.MonkeyPatch) -> SimulatedAmp:
    """The amp at the other end of whatever port the integration opens."""
    simulated = SimulatedAmp()
    monkeypatch.setattr(serialx, "create_serial_connection", simulated.create_serial_connection)
    # Short timeouts, so a silent zone doesn't slow the tests down.
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    monkeypatch.setattr(amp_module, "SET_REPLY_TIMEOUT", 0.05)
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    monkeypatch.setattr(amp_module, "RAW_TIMEOUT", 0.2)
    return simulated


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Monoprice 44518",
        data={CONF_PORT: "/dev/ttyUSB0"},
        options={CONF_ZONES: [1, 2, 3, 4, 5, 6, 7, 8], CONF_SOURCES: {"2": "Sonos", "5": "TV"}},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def set_up(hass: HomeAssistant, amp: SimulatedAmp, entry: MockConfigEntry) -> Callable[[], Awaitable[None]]:
    """Set the entry up. A test can change the amp first, then call this."""

    async def set_up() -> None:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return set_up
