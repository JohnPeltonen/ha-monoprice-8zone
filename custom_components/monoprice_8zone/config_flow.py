"""Config flow for the Monoprice 8-Zone Amplifier (44518)."""

from homeassistant.config_entries import ConfigFlow

from custom_components.monoprice_8zone.const import DOMAIN


class Monoprice8ZoneConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
