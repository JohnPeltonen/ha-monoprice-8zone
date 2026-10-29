"""Setup screens for the Monoprice 8-Zone Amplifier (44518): the port, then the zones and source names.
Also changing the port (reconfigure), and the zones and source names (options)."""

import logging
import os
from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
)

from custom_components.monoprice_8zone.amp import AmpTimeoutError, PortInUseError, PortNotFoundError, open_amp
from custom_components.monoprice_8zone.const import CONF_SOURCES, CONF_ZONES, DOMAIN, SOURCES, ZONES

logger = logging.getLogger(__name__)

TITLE = "Monoprice 44518"

PORT_SCHEMA = probatio.Schema({probatio.Required(CONF_PORT): SerialPortSelector()})

# No defaults: each screen fills this in with suggested values, so a source name that's cleared stays cleared.
ZONES_AND_SOURCES_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_ZONES): SelectSelector(
            SelectSelectorConfig(
                options=[SelectOptionDict(value=str(zone), label=f"Zone {zone}") for zone in ZONES],
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        ),
        **{probatio.Optional(f"source_{number}"): str for number in SOURCES},
    }
)


async def check_port(port: str) -> str | None:
    """Open the port and ask zone 1 for its status. Return an error key, or None if the amp answered."""
    try:
        amp = await open_amp(port)
        await amp.query_zone(1)
        await amp.close()
    except PortInUseError:
        return "port_in_use"
    except PortNotFoundError:
        return "port_not_found"
    except AmpTimeoutError:
        return "no_answer"
    except Exception:
        logger.exception("Unexpected error checking %s", port)
        return "unknown"
    return None


def same_device(port: str, other: str) -> bool:
    """True when both paths are the same device, for example /dev/ttyUSB0 and its /dev/serial/by-id/ link."""
    return port == other


def options_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """The entry's options from the zones and sources form. Blank source names are left out."""
    names = {str(number): user_input.get(f"source_{number}", "").strip() for number in SOURCES}
    return {
        CONF_ZONES: sorted(int(zone) for zone in user_input[CONF_ZONES]),
        CONF_SOURCES: {number: name for number, name in names.items() if name},
    }


class Monoprice8ZoneConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._port = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := await check_port(user_input[CONF_PORT])) is None:
                self._port = user_input[CONF_PORT]
                return await self.async_step_zones()
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(PORT_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_zones(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options = options_from_input(user_input)
            if options[CONF_ZONES]:
                return self.async_create_entry(title=TITLE, data={CONF_PORT: self._port}, options=options)
            errors[CONF_ZONES] = "no_zones"
        suggested = user_input if user_input is not None else {CONF_ZONES: [str(zone) for zone in ZONES]}
        return self.async_show_form(
            step_id="zones",
            data_schema=self.add_suggested_values_to_schema(ZONES_AND_SOURCES_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT]
            # The integration holds its port open, so checking the same device again would find it in use.
            if await self.hass.async_add_executor_job(same_device, port, entry.data[CONF_PORT]):
                error = None
            else:
                error = await check_port(port)
            if error is None:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PORT: port})
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(PORT_SCHEMA, user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> Monoprice8ZoneOptionsFlow:
        return Monoprice8ZoneOptionsFlow()


class Monoprice8ZoneOptionsFlow(OptionsFlowWithReload):
    """The zones and source names. HA reloads the integration when they change."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            options = options_from_input(user_input)
            if options[CONF_ZONES]:
                return self.async_create_entry(data=options)
            errors[CONF_ZONES] = "no_zones"
        current = self.config_entry.options
        suggested = user_input if user_input is not None else {
            CONF_ZONES: [str(zone) for zone in current[CONF_ZONES]],
            **{f"source_{number}": name for number, name in current[CONF_SOURCES].items()},
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(ZONES_AND_SOURCES_SCHEMA, suggested),
            errors=errors,
        )
