import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.monoprice_8zone.const import DOMAIN


async def send(hass, command):
    return await hass.services.async_call(
        DOMAIN, "send_command", {"command": command}, blocking=True, return_response=True
    )


async def test_send_command_returns_the_reply(hass, amp, set_up):
    await set_up()
    amp.writes.clear()
    assert await send(hass, "?11") == {"reply": ">1100010000100707100200 Zone1    Source02\\r\\n#"}
    assert amp.writes == [b"?11\r"]


async def test_send_command_when_the_amp_is_silent(hass, amp, set_up):
    await set_up()
    amp.silent_zones = {1}
    assert await send(hass, "<11MU01") == {"reply": ""}


async def test_send_command_rejects_other_commands(hass, amp, set_up):
    await set_up()
    amp.writes.clear()
    with pytest.raises(ServiceValidationError) as caught:
        await send(hass, "19200")
    assert caught.value.translation_key == "bad_command"
    assert amp.writes == []


async def test_send_command_needs_the_integration_loaded(hass, entry, set_up):
    await set_up()
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as caught:
        await send(hass, "?11")
    assert caught.value.translation_key == "not_loaded"
