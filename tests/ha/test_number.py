import pytest
from homeassistant.const import EntityCategory
from pytest_homeassistant_custom_component.common import flush_store

MAXIMUM_VOLUME = "number.zone_1_maximum_volume"


async def set_limit(hass, percent):
    await hass.services.async_call("number", "set_value", {"entity_id": MAXIMUM_VOLUME, "value": percent}, blocking=True)
    await hass.async_block_till_done()


async def test_values_are_centered_on_zero(hass, amp, set_up):
    amp.zones[1].update(BS=0, TR=14, BL=20)
    await set_up()
    assert float(hass.states.get("number.zone_1_bass").state) == -7
    assert float(hass.states.get("number.zone_1_treble").state) == 7
    assert float(hass.states.get("number.zone_1_balance").state) == 10


@pytest.mark.parametrize(
    ("entity_id", "value", "command"),
    [
        ("number.zone_1_bass", 3, b"<11BS10\r"),
        ("number.zone_1_bass", 2.6, b"<11BS10\r"),
        ("number.zone_1_treble", -7, b"<11TR00\r"),
        ("number.zone_1_balance", -10, b"<11BL00\r"),
        ("number.zone_1_balance", 10, b"<11BL20\r"),
    ],
)
async def test_set_number(hass, amp, set_up, entity_id, value, command):
    await set_up()
    amp.writes.clear()
    await hass.services.async_call("number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True)
    assert amp.writes == [command, b"?11\r"]


async def test_numbers_are_configuration_entities(hass, set_up, entity_registry):
    await set_up()
    for name in ("bass", "treble", "balance"):
        assert entity_registry.async_get(f"number.zone_1_{name}").entity_category is EntityCategory.CONFIG


async def test_maximum_volume_starts_at_100(hass, set_up, entity_registry):
    await set_up()
    assert float(hass.states.get(MAXIMUM_VOLUME).state) == 100
    assert entity_registry.async_get(MAXIMUM_VOLUME).entity_category is EntityCategory.CONFIG


async def test_setting_the_limit_does_not_touch_the_amp(hass, amp, set_up):
    await set_up()
    amp.writes.clear()
    await set_limit(hass, 50)
    assert amp.writes == []
    assert len(amp.connections) == 1  # no reload
    assert float(hass.states.get(MAXIMUM_VOLUME).state) == 50


async def test_limit_is_saved(hass, entry, set_up, hass_storage):
    await set_up()
    await set_limit(hass, 50)
    await set_limit(hass, 60)
    await flush_store(hass.config_entries._store)
    entries = hass_storage["core.config_entries"]["data"]["entries"]
    saved = next(item for item in entries if item["entry_id"] == entry.entry_id)
    assert saved["options"]["max_volumes"] == {"1": 60}


async def test_silent_zone_numbers_are_unavailable(hass, amp, set_up):
    amp.silent_zones = {3}
    await set_up()
    for name in ("bass", "treble", "balance"):
        assert hass.states.get(f"number.zone_3_{name}").state == "unavailable"
