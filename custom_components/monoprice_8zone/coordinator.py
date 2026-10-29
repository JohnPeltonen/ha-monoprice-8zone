"""Polls the amp, and sends it the commands that come from HA."""

import logging

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.monoprice_8zone.amp import Amp, AmpError, AmpTimeoutError, PortFailedError, ZoneStatus
from custom_components.monoprice_8zone.const import CONF_ZONES, DOMAIN, SCAN_INTERVAL

logger = logging.getLogger(__name__)

type AmpConfigEntry = ConfigEntry[AmpCoordinator]


class AmpCoordinator(DataUpdateCoordinator[dict[int, ZoneStatus | None]]):
    """Everything HA does with the amp. A zone that didn't answer the last poll is None."""

    config_entry: AmpConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AmpConfigEntry, amp: Amp) -> None:
        super().__init__(hass, logger, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.amp = amp
        self.zones: list[int] = entry.options[CONF_ZONES]
        # A poll takes the lock one zone at a time, so a set command can run in the middle of it.
        # The status it returns is newer than the poll's reading of that zone.
        self._set_during_poll: dict[int, ZoneStatus] = {}

    async def _async_update_data(self) -> dict[int, ZoneStatus | None]:
        self._set_during_poll = {}
        try:
            statuses = await self.amp.query_zones(self.zones)
        except AmpError as exc:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key=self._error_key(exc)) from exc
        return statuses | self._set_during_poll

    async def async_set_value(self, zone: int, field: str, value: int) -> None:
        """Change one setting, then show the zone's status as the amp reports it."""
        try:
            status = await self.amp.set_value(zone, field, value)
        except AmpError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=self._error_key(exc)) from exc
        self._set_during_poll[zone] = status
        self.async_set_updated_data({**self.data, zone: status})

    async def async_send_raw(self, command: str) -> str:
        """Send one raw command and return the amp's reply, with CR and LF written out so they show."""
        try:
            reply = await self.amp.send_raw(command)
        except ValueError as exc:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="bad_command") from exc
        except AmpError as exc:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=self._error_key(exc)) from exc
        return reply.decode("ascii", errors="backslashreplace").replace("\r", "\\r").replace("\n", "\\n")

    def _error_key(self, exc: AmpError) -> str:
        """Name the error for the UI. A port failure also reloads the integration, which reopens the port."""
        if isinstance(exc, PortFailedError):
            # During setup, ConfigEntryNotReady already makes HA retry.
            if self.config_entry.state is ConfigEntryState.LOADED:
                self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            return "port_failed"
        if isinstance(exc, AmpTimeoutError):
            return "no_answer"
        return "closed"
