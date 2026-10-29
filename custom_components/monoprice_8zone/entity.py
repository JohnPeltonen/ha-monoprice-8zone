"""The base of every zone entity."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.monoprice_8zone.amp import ZoneStatus
from custom_components.monoprice_8zone.const import DOMAIN
from custom_components.monoprice_8zone.coordinator import AmpCoordinator


def zone_device_identifier(entry_id: str, zone: int) -> str:
    return f"{entry_id}_zone_{zone}"


class ZoneEntity(CoordinatorEntity[AmpCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AmpCoordinator, zone: int, key: str | None) -> None:
        super().__init__(coordinator)
        self.zone = zone
        entry_id = coordinator.config_entry.entry_id
        identifier = zone_device_identifier(entry_id, zone)
        self._attr_unique_id = f"{identifier}_{key}" if key else identifier
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=f"Zone {zone}",
            manufacturer="Monoprice",
            model="44518",
            via_device_id=dr.async_get_device_id_by_identifier(
                coordinator.hass, (DOMAIN, entry_id), config_entry_id=entry_id
            ),
        )

    @property
    def available(self) -> bool:
        # A zone that didn't answer the last poll is unavailable on its own.
        return super().available and self.coordinator.data.get(self.zone) is not None

    @property
    def status(self) -> ZoneStatus:
        return self.coordinator.data[self.zone]
