DND = "switch.zone_1_do_not_disturb"


async def test_do_not_disturb(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    assert hass.states.get(DND).state == "on"
    amp.writes.clear()
    await hass.services.async_call("switch", "turn_off", {"entity_id": DND}, blocking=True)
    assert amp.writes == [b"<11DT00\r", b"?11\r"]
    assert hass.states.get(DND).state == "off"


async def test_silent_zone_switch_is_unavailable(hass, amp, set_up):
    amp.silent_zones = {3}
    await set_up()
    assert hass.states.get("switch.zone_3_do_not_disturb").state == "unavailable"
