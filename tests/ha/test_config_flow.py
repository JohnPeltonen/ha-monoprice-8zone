import errno
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.monoprice_8zone.const import CONF_SOURCES, CONF_ZONES, DOMAIN


def suggested(result) -> dict[str, Any]:
    """The values a form starts with."""
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_flow_creates_the_entry(hass, amp):
    result = await start(hass)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "user")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "zones")
    assert suggested(result) == {CONF_ZONES: ["1", "2", "3", "4", "5", "6", "7", "8"]}
    with patch("custom_components.monoprice_8zone.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ZONES: ["5", "1", "2"], "source_2": "Sonos", "source_5": " TV ", "source_6": "  "},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Monoprice 44518"
    assert result["data"] == {CONF_PORT: "/dev/ttyUSB0"}
    assert result["options"] == {CONF_ZONES: [1, 2, 5], CONF_SOURCES: {"2": "Sonos", "5": "TV"}}
    assert amp.writes == [b"?11\r"]
    assert amp.connections[0].closed


@pytest.mark.parametrize(
    ("open_error", "silent_zones", "error"),
    [
        (OSError(errno.EBUSY, "locked"), set(), "port_in_use"),
        (FileNotFoundError(errno.ENOENT, "missing"), set(), "port_not_found"),
        (None, {1}, "no_answer"),
        (PermissionError(errno.EACCES, "denied"), set(), "unknown"),
    ],
)
async def test_user_flow_port_errors(hass, amp, open_error, silent_zones, error):
    amp.open_error = open_error
    amp.silent_zones = silent_zones
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert (result["step_id"], result["errors"]) == ("user", {"base": error})
    assert all(connection.closed for connection in amp.connections)


async def test_user_flow_recovers_after_no_answer(hass, amp):
    amp.silent_zones = {1}
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert result["errors"] == {"base": "no_answer"}
    amp.silent_zones = set()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert result["step_id"] == "zones"  # the simulated lock would refuse this if the first try left the port open


async def test_zones_step_needs_a_zone(hass, amp):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONES: []})
    assert (result["step_id"], result["errors"]) == ("zones", {CONF_ZONES: "no_zones"})


async def test_only_one_amp(hass, amp, entry):
    result = await start(hass)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "single_instance_allowed")


@pytest.fixture
def linked_ports(tmp_path) -> tuple[str, str]:
    """A port and a second name for it, like /dev/ttyUSB0 and its /dev/serial/by-id/ link."""
    port = tmp_path / "ttyUSB0"
    port.touch()
    link = tmp_path / "usb-FTDI_FT232R_USB_UART-if00-port0"
    link.symlink_to(port)
    return str(port), str(link)


async def test_reconfigure_changes_the_port(hass, amp, entry, set_up):
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    assert suggested(result) == {CONF_PORT: "/dev/ttyUSB0"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB1"})
    await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reconfigure_successful")
    assert entry.data[CONF_PORT] == "/dev/ttyUSB1"
    assert entry.state is ConfigEntryState.LOADED
    # setup on the old port, the check on the new one, then the reload
    assert [(c.port, c.closed) for c in amp.connections] == [
        ("/dev/ttyUSB0", True), ("/dev/ttyUSB1", True), ("/dev/ttyUSB1", False),
    ]


async def test_reconfigure_same_device_skips_the_check(hass, amp, entry, set_up, linked_ports):
    port, link = linked_ports
    hass.config_entries.async_update_entry(entry, data={CONF_PORT: port})
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: link})
    await hass.async_block_till_done()
    # A check would have opened the same device again and hit the integration's own lock.
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == link
    assert len(amp.connections) == 2  # setup, then the reload


async def test_reconfigure_port_in_use(hass, amp, entry, set_up):
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    amp.open_error = OSError(errno.EBUSY, "locked")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB1"})
    assert (result["step_id"], result["errors"]) == ("reconfigure", {"base": "port_in_use"})
    assert entry.data[CONF_PORT] == "/dev/ttyUSB0"


async def test_options_change_zones_and_sources(hass, entry, set_up, entity_registry):
    await set_up()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert suggested(result) == {
        CONF_ZONES: ["1", "2", "3", "4", "5", "6", "7", "8"], "source_2": "Sonos", "source_5": "TV",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ZONES: ["1", "2"], "source_3": "Radio"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_ZONES: [1, 2], CONF_SOURCES: {"3": "Radio"}}
    assert entry.state is ConfigEntryState.LOADED
    assert entity_registry.async_get("media_player.zone_3") is None
    assert hass.states.get("media_player.zone_1").attributes["source_list"] == ["Radio"]


async def test_options_need_a_zone(hass, entry, set_up):
    await set_up()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ZONES: []})
    assert (result["step_id"], result["errors"]) == ("init", {CONF_ZONES: "no_zones"})
