"""Bass, treble, balance and maximum volume sliders for each zone, as configuration entities."""

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.monoprice_8zone.amp import BALANCE, BASS, TREBLE
from custom_components.monoprice_8zone.coordinator import AmpConfigEntry, AmpCoordinator
from custom_components.monoprice_8zone.entity import ZoneEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ZoneNumberDescription(NumberEntityDescription):
    field: str
    # The amp's value is HA's value plus this, so 0 in HA is flat (or centered) on the amp.
    offset: int


NUMBERS = (
    ZoneNumberDescription(
        key="bass", translation_key="bass", field=BASS, offset=7, native_min_value=-7, native_max_value=7
    ),
    ZoneNumberDescription(
        key="treble", translation_key="treble", field=TREBLE, offset=7, native_min_value=-7, native_max_value=7
    ),
    # Negative is left. Which end of the amp's scale is left gets confirmed in a hardware check.
    ZoneNumberDescription(
        key="balance", translation_key="balance", field=BALANCE, offset=10, native_min_value=-10, native_max_value=10
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AmpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        ZoneNumber(coordinator, zone, description) for zone in coordinator.zones for description in NUMBERS
    )
    async_add_entities(MaximumVolumeNumber(coordinator, zone) for zone in coordinator.zones)


class ZoneNumber(ZoneEntity, NumberEntity):
    entity_description: ZoneNumberDescription
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AmpCoordinator, zone: int, description: ZoneNumberDescription) -> None:
        super().__init__(coordinator, zone, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int:
        return getattr(self.status, self.entity_description.key) - self.entity_description.offset

    async def async_set_native_value(self, value: float) -> None:
        amp_value = round(value) + self.entity_description.offset
        await self.coordinator.async_set_value(self.zone, self.entity_description.field, amp_value)


class MaximumVolumeNumber(ZoneEntity, NumberEntity):
    """The most the zone's volume slider can ask for, as a percentage of the amp's full volume."""

    _attr_translation_key = "max_volume"
    _attr_native_min_value = 5
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AmpCoordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "max_volume")

    @property
    def native_value(self) -> int:
        return self.coordinator.max_volume_percent(self.zone)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.async_set_max_volume(self.zone, round(value))
