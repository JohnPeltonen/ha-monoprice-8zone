import asyncio
import errno
from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.monoprice_8zone.amp import VOLUME
from custom_components.monoprice_8zone.const import CONF_ZONES, SCAN_INTERVAL, ZONES

NEXT_POLL = SCAN_INTERVAL + timedelta(seconds=1)


async def test_setup_polls_every_enabled_zone(hass, amp, entry, set_up):
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_ZONES: [1, 3]})
    await set_up()
    assert entry.state is ConfigEntryState.LOADED
    assert amp.connections[0].port == "/dev/ttyUSB0"
    assert amp.writes == [b"?11\r", b"?13\r"]


async def test_silent_zone_does_not_fail_the_poll(hass, amp, entry, set_up):
    amp.silent_zones = {3}
    await set_up()
    assert entry.runtime_data.data[3] is None
    assert entry.runtime_data.data[1].zone == 1


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (OSError(errno.EBUSY, "locked"), "port_in_use"),
        (FileNotFoundError(errno.ENOENT, "missing"), "port_not_found"),
    ],
)
async def test_setup_port_errors_retry(hass, amp, entry, error, reason):
    amp.open_error = error
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == reason


async def test_setup_retries_and_closes_the_port_when_no_zone_answers(hass, amp, entry):
    amp.silent_zones = set(ZONES)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "no_answer"
    assert amp.connections[0].closed


async def test_unload_closes_the_port(hass, amp, entry, set_up):
    await set_up()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert amp.connections[0].closed


async def test_reload_reopens_the_port(hass, amp, entry, set_up):
    await set_up()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    # The simulated lock refuses a second open, so this also proves unload closed the first.
    assert entry.state is ConfigEntryState.LOADED
    assert [connection.closed for connection in amp.connections] == [True, False]


async def test_command_after_close_says_reloading(hass, amp, entry, set_up):
    await set_up()
    await entry.runtime_data.amp.close()
    with pytest.raises(HomeAssistantError) as caught:
        await entry.runtime_data.async_set_value(1, VOLUME, 5)
    assert caught.value.translation_key == "closed"


async def test_set_during_a_poll_is_kept(hass, amp, entry, set_up):
    await set_up()
    coordinator = entry.runtime_data
    amp.writes.clear()
    poll = hass.async_create_task(coordinator.async_refresh())
    await asyncio.sleep(0)  # the poll has sent ?11 and holds the lock
    await coordinator.async_set_value(1, VOLUME, 11)
    await poll
    assert amp.writes[:4] == [b"?11\r", b"<11VO11\r", b"?11\r", b"?12\r"]  # the set ran mid-poll
    assert coordinator.data[1].volume == 11  # not the 10 the poll read before the set


# The poll and the setup retry run as background tasks, so these tests wait for those too.
async def test_polls_every_30_seconds(hass, amp, entry, set_up):
    await set_up()
    amp.zones[1]["VO"] = 20
    async_fire_time_changed(hass, dt_util.utcnow() + NEXT_POLL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.runtime_data.data[1].volume == 20


async def test_port_failure_reloads_and_waits_for_the_port(hass, amp, entry, set_up):
    await set_up()
    amp.connections[0].unplug()
    amp.open_error = FileNotFoundError(errno.ENOENT, "missing")
    async_fire_time_changed(hass, dt_util.utcnow() + NEXT_POLL)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "port_not_found"
    amp.open_error = None  # plugged back in
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
