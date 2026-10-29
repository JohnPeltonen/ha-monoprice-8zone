import asyncio
from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.monoprice_8zone.const import CONF_ZONES, DOMAIN, SCAN_INTERVAL, ZONES

ZONE_1 = "media_player.zone_1"


async def call(hass, service, **data):
    await hass.services.async_call("media_player", service, {"entity_id": ZONE_1, **data}, blocking=True)


async def test_zone_devices_link_to_the_amp(hass, entry, set_up, device_registry):
    await set_up()
    amp_device = device_registry.async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
    zone_1 = device_registry.async_get_device_by_identifier((DOMAIN, f"{entry.entry_id}_zone_1"), entry.entry_id)
    assert (amp_device.name, amp_device.model) == ("Monoprice 44518", "44518")
    assert zone_1.name == "Zone 1"
    assert zone_1.via_device_id == amp_device.id
    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 9


async def test_disabled_zone_is_removed(hass, entry, set_up, device_registry, entity_registry):
    await set_up()
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_ZONES: [1, 2]})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert device_registry.async_get_device_by_identifier((DOMAIN, f"{entry.entry_id}_zone_3"), entry.entry_id) is None
    assert entity_registry.async_get("media_player.zone_3") is None
    assert hass.states.get("media_player.zone_2").state == "on"


async def test_media_player_state(hass, amp, set_up):
    amp.zones[2]["PR"] = 0
    await set_up()
    state = hass.states.get(ZONE_1)
    assert state.state == "on"
    assert state.attributes["volume_level"] == pytest.approx(10 / 38)
    assert state.attributes["is_volume_muted"] is False
    assert state.attributes["source"] == "Sonos"
    assert state.attributes["source_list"] == ["Sonos", "TV"]
    assert hass.states.get("media_player.zone_2").state == "off"


async def test_unnamed_source_shows_as_source_n(hass, amp, set_up):
    amp.zones[1]["CH"] = 3
    await set_up()
    assert hass.states.get(ZONE_1).attributes["source"] == "Source 3"


@pytest.mark.parametrize(
    ("service", "data", "command"),
    [
        ("turn_off", {}, b"<11PR00\r"),
        ("turn_on", {}, b"<11PR01\r"),
        ("volume_set", {"volume_level": 0.5}, b"<11VO19\r"),
        ("volume_up", {}, b"<11VO11\r"),
        ("volume_down", {}, b"<11VO09\r"),
        ("volume_mute", {"is_volume_muted": True}, b"<11MU01\r"),
        ("select_source", {"source": "TV"}, b"<11CH05\r"),
    ],
)
async def test_media_player_commands(hass, amp, set_up, service, data, command):
    await set_up()
    amp.writes.clear()
    await call(hass, service, **data)
    assert amp.writes == [command, b"?11\r"]


async def test_set_volume_shows_right_away(hass, set_up):
    await set_up()
    await call(hass, "volume_set", volume_level=0.5)
    assert hass.states.get(ZONE_1).attributes["volume_level"] == pytest.approx(19 / 38)


async def test_volume_up_twice_quickly_moves_two_steps(hass, amp, set_up):
    await set_up()
    await asyncio.gather(call(hass, "volume_up"), call(hass, "volume_up"))
    assert amp.zones[1]["VO"] == 12


async def test_volume_up_stops_at_the_top(hass, amp, set_up):
    amp.zones[1]["VO"] = 38
    await set_up()
    await call(hass, "volume_up")
    assert amp.zones[1]["VO"] == 38


async def test_select_unknown_source_is_rejected(hass, amp, set_up):
    await set_up()
    amp.writes.clear()
    with pytest.raises(ServiceValidationError) as caught:
        await call(hass, "select_source", source="Radio")
    # HA's "action not found" is a ServiceValidationError too, so check which one this is.
    assert caught.value.translation_key == "unknown_source"
    assert amp.writes == []


async def test_silent_zone_is_unavailable(hass, amp, set_up):
    amp.silent_zones = {3}
    await set_up()
    assert hass.states.get("media_player.zone_3").state == "unavailable"
    assert hass.states.get(ZONE_1).state == "on"


async def test_command_when_the_amp_does_not_answer(hass, amp, set_up):
    await set_up()
    amp.silent_zones = {1}
    with pytest.raises(HomeAssistantError) as caught:
        await call(hass, "volume_up")
    assert caught.value.translation_key == "no_answer"


async def test_every_zone_unavailable_when_none_answer(hass, amp, set_up):
    await set_up()
    amp.silent_zones = set(ZONES)
    async_fire_time_changed(hass, dt_util.utcnow() + SCAN_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ZONE_1).state == "unavailable"
