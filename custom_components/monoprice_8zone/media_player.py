"""A media player for each zone: power, volume, mute and source."""

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.monoprice_8zone.amp import MUTE, POWER, SOURCE, VOLUME
from custom_components.monoprice_8zone.const import CONF_SOURCES, DOMAIN
from custom_components.monoprice_8zone.coordinator import AmpConfigEntry, AmpCoordinator
from custom_components.monoprice_8zone.entity import ZoneEntity

# HA runs one action at a time per platform, so a second volume press reads the volume the first one set.
PARALLEL_UPDATES = 1

MAX_VOLUME = 38


async def async_setup_entry(
    hass: HomeAssistant, entry: AmpConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    sources = {int(number): name for number, name in entry.options[CONF_SOURCES].items()}
    coordinator = entry.runtime_data
    async_add_entities(ZoneMediaPlayer(coordinator, zone, sources) for zone in coordinator.zones)


class ZoneMediaPlayer(ZoneEntity, MediaPlayerEntity):
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, coordinator: AmpCoordinator, zone: int, sources: dict[int, str]) -> None:
        super().__init__(coordinator, zone, None)
        self._sources = sources
        self._attr_source_list = [sources[number] for number in sorted(sources)]

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self.status.power else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float:
        return self.status.volume / MAX_VOLUME

    @property
    def is_volume_muted(self) -> bool:
        return self.status.mute

    @property
    def source(self) -> str:
        return self._sources.get(self.status.source, f"Source {self.status.source}")

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_value(self.zone, POWER, 1)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_value(self.zone, POWER, 0)

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_set_value(self.zone, VOLUME, round(volume * MAX_VOLUME))

    async def async_volume_up(self) -> None:
        await self.coordinator.async_set_value(self.zone, VOLUME, min(self.status.volume + 1, MAX_VOLUME))

    async def async_volume_down(self) -> None:
        await self.coordinator.async_set_value(self.zone, VOLUME, max(self.status.volume - 1, 0))

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_set_value(self.zone, MUTE, int(mute))

    async def async_select_source(self, source: str) -> None:
        number = next((number for number, name in self._sources.items() if name == source), None)
        if number is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_source",
                translation_placeholders={"source": source},
            )
        await self.coordinator.async_set_value(self.zone, SOURCE, number)
