"""Monoprice 8-Zone Amplifier (44518) integration."""

from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from custom_components.monoprice_8zone.amp import PortInUseError, PortNotFoundError, open_amp
from custom_components.monoprice_8zone.const import CONF_ZONES, DOMAIN
from custom_components.monoprice_8zone.coordinator import AmpConfigEntry, AmpCoordinator
from custom_components.monoprice_8zone.entity import zone_device_identifier

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.NUMBER, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: AmpConfigEntry) -> bool:
    try:
        amp = await open_amp(entry.data[CONF_PORT])
    except PortInUseError as exc:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="port_in_use") from exc
    except PortNotFoundError as exc:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="port_not_found") from exc
    # HA runs this on unload, after the entities are gone, and after any setup that fails from here on.
    entry.async_on_unload(amp.close)
    coordinator = AmpCoordinator(hass, entry, amp)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # The amp's own device ties the zone devices together. A zone turned off in the options loses
    # its device, and HA removes the device's entities with it.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Monoprice",
        model="44518",
        name="Monoprice 44518",
    )
    wanted = {(DOMAIN, entry.entry_id)} | {
        (DOMAIN, zone_device_identifier(entry.entry_id, zone)) for zone in entry.options[CONF_ZONES]
    }
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not device.identifiers & wanted:
            device_registry.async_remove_device(device.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AmpConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
