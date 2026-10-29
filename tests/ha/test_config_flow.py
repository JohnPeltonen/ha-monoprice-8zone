import errno
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
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
