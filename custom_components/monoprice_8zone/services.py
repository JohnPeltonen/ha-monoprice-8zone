"""The send_command action, for testing the amp from Developer Tools."""

import probatio
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from custom_components.monoprice_8zone.const import DOMAIN

SEND_COMMAND_SCHEMA = probatio.Schema({probatio.Required("command"): cv.string})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def send_command(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
        return {"reply": await entries[0].runtime_data.async_send_raw(call.data["command"])}

    hass.services.async_register(
        DOMAIN, "send_command", send_command, schema=SEND_COMMAND_SCHEMA, supports_response=SupportsResponse.ONLY
    )
