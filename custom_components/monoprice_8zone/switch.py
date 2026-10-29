"""A Do Not Disturb switch for each zone. A zone with it on is left out of the amp's hardware page."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.monoprice_8zone.amp import DO_NOT_DISTURB
from custom_components.monoprice_8zone.coordinator import AmpConfigEntry, AmpCoordinator
from custom_components.monoprice_8zone.entity import ZoneEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: AmpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DoNotDisturbSwitch(coordinator, zone) for zone in coordinator.zones)


class DoNotDisturbSwitch(ZoneEntity, SwitchEntity):
    _attr_translation_key = "do_not_disturb"

    def __init__(self, coordinator: AmpCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "do_not_disturb")

    @property
    def is_on(self) -> bool:
        return self.status.do_not_disturb

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self.zone, DO_NOT_DISTURB, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_value(self.zone, DO_NOT_DISTURB, 0)
