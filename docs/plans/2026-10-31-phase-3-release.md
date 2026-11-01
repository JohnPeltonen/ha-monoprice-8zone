# Phase 3: Off-Zone Errors, Volume at Turn-On, and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner chose native execution in CLAUDE.md: Claude builds every task in this session, and a very capable reviewer checks the plan before building and the code at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell the owner when a setting can't change because the zone is off, stop a zone from staying above its Maximum volume when HA turns it on, and release v0.1.0.

**Architecture:** Both changes go in `Amp` in `amp.py`, so they're tested locally. It already queries the zone after every set command, so it decides from the amp's own report instead of the last poll. `AmpCoordinator` passes the limit in and turns the new error into a translated message.

**Tech Stack:** Home Assistant 2026.10, `serialx`, plain pytest for `amp.py`, `pytest-homeassistant-custom-component` in GitHub Actions.

**Spec:** the owner's answers on 2026-10-31, [PROTOCOL.md](../../PROTOCOL.md) and [docs/design.md](../design.md).

**Budget:** 1 session / about 100,000 tokens, including two reviewer runs. For scale only: the owner waived the token stop on 2026-10-29.

## What the owner decided

- A setting changed on an off zone shows an error, something like "The Zone must be on to change its settings."
- A zone above its limit gets lowered when HA turns it on. The owner accepted that the old volume can be heard briefly.
- Trust the wiring and the README: which end of the balance scale is left stays unverified, and the adapter line stays FTDI FT232R.
- Tag `v0.1.0`.

## What the amp does (observed, in PROTOCOL.md)

- A zone that's off rejects volume, mute, bass, treble, balance and source with `Command Error.`. It accepts power and Do Not Disturb.
- So the volume can't be lowered before the zone turns on. It can only be lowered right after.
- Mute survives powering a zone off and on.

## Global Constraints

- `amp.py` keeps importing nothing from `homeassistant`.
- Entities hold no logic beyond mapping values. They call `AmpCoordinator` methods.
- `strings.json` and `translations/en.json` hold the same content.
- **The HA tests run only in GitHub Actions.** New tests are their own commit, pushed first, and that commit's message ends with "(they fail until the next commit)".
- Before every push, run `.venv/Scripts/python -m compileall -q custom_components tests` and `.venv/Scripts/python -m pytest -q`.
- Pushing to `main` is approved for this repo. Commit with explicit paths.
- Docs: no em dashes, "type" never "kind", no household names.

## Review Focus

1. **A setting changed on an off zone with Do Not Disturb on.** It shows the error, and Do Not Disturb isn't lifted for a command that can't work. Test: `test_set_value_on_an_off_zone_with_do_not_disturb_does_not_lift`.
2. **Turning on a zone with Do Not Disturb on, above its limit.** The zone comes on, lands at the limit, and Do Not Disturb is still on. Test: `test_turn_on_with_do_not_disturb_lowers_to_the_limit`.
3. **The last poll is out of date.** A keypad turned the zone on after the last poll, so HA's view says off. The command works, with no error, because the decision comes from the amp's reply to the query after the command. Test: `test_zone_turned_on_since_the_last_poll_takes_the_command`.
4. **An automation sets the volume on an off zone.** It now gets an error where it used to do nothing, and by default that stops the automation. This follows from the owner's call. It goes in the design doc. No test beyond `test_volume_on_an_off_zone_shows_the_error`.
5. **The amp already has the requested value on an off zone.** Nothing needs to change, so no error. Test: `test_set_value_on_an_off_zone_to_the_same_value`.

## Decisions this plan makes

1. **Every rejected field shows the error (Claude's call):** volume, volume up and down, mute, source, bass, treble and balance. The owner said "settings". One rule is simpler than deciding field by field.
2. **The message is "The zone must be on to change its settings." (Claude's call on the lowercase "zone").**
3. **The lowering only happens in HA's turn on (Claude's call).** A wall keypad reaches the amp directly, so a zone it turns on isn't lowered until its next volume change, as today.
4. **Turning on keeps the volume if it's at or below the limit.**
5. **Default-on volume isn't in this plan.** The owner mentioned it as a wish. It goes on the Later list unless the owner says otherwise.

---

### Task 1: The error and the lowering

**Files:**
- Modify: `amp.py`, `coordinator.py`, `media_player.py`, `strings.json`, `translations/en.json` in `custom_components/monoprice_8zone/`
- Modify: `PROTOCOL.md`, `README.md`, `docs/design.md`, `CLAUDE.md`
- Test: `tests/amp/fake_amp.py`, `tests/amp/test_commands.py`, `tests/ha/test_media_player.py`, `tests/ha/test_number.py`

**Interfaces:**
- Produces: `ZoneOffError(AmpError)` and `Amp.turn_on(zone: int, volume_limit: int) -> ZoneStatus` in `amp.py`.
- Produces: `AmpCoordinator.async_turn_on(zone: int) -> None`.

- [x] **Step 1: Add the tests**

In `tests/amp/test_commands.py`, with a new `ZONE_1_OFF` in `fake_amp.py` (power off, volume 10, Do Not Disturb off):

```python
async def test_set_value_on_an_off_zone(make_amp):
    amp, transport = make_amp(b"Command Error.\r\n#", ZONE_1_OFF)
    with pytest.raises(ZoneOffError):
        await amp.set_value(1, VOLUME, 20)
    assert writes(transport) == [b"<11VO20\r", b"?11\r"]


async def test_set_value_on_an_off_zone_to_the_same_value(make_amp):
    amp, transport = make_amp(b"Command Error.\r\n#", ZONE_1_OFF)
    status = await amp.set_value(1, VOLUME, 10)
    assert status.volume == 10


async def test_set_value_on_an_off_zone_with_do_not_disturb_does_not_lift(make_amp):
    amp, transport = make_amp(b"Command Error.\r\n#", ZONE_1_OFF_DND)
    with pytest.raises(ZoneOffError):
        await amp.set_value(1, VOLUME, 20)
    assert writes(transport) == [b"<11VO20\r", b"?11\r"]


async def test_stale_off_zone_still_takes_the_command(make_amp):
    amp, transport = make_amp(b">11VO20\r\n#", ZONE_1_VOLUME_20)
    assert (await amp.set_value(1, VOLUME, 20)).volume == 20


async def test_turn_on_lowers_to_the_limit(make_amp):
    amp, transport = make_amp(b">11PR01\r\n#", ZONE_1_VOLUME_20, b">11VO10\r\n#", ZONE_1)
    status = await amp.turn_on(1, 10)
    assert status.volume == 10
    assert writes(transport) == [b"<11PR01\r", b"?11\r", b"<11VO10\r", b"?11\r"]


async def test_turn_on_at_the_limit_keeps_the_volume(make_amp):
    amp, transport = make_amp(b">11PR01\r\n#", ZONE_1)
    await amp.turn_on(1, 10)
    assert writes(transport) == [b"<11PR01\r", b"?11\r"]


async def test_turn_on_with_do_not_disturb_lowers_to_the_limit(make_amp):
    # Each command is ignored, then lifted.
    ...
```

`test_turn_on_with_do_not_disturb_lowers_to_the_limit` replays both lifts with new status constants, and asserts the writes end with Do Not Disturb back on.

`writes(transport)` is a small helper in the test file that keeps only the writes.

In `tests/ha/test_media_player.py`:

```python
async def test_turn_on_lowers_to_the_limit(hass, amp, set_up):
    amp.zones[1]["PR"] = 0
    amp.zones[1]["VO"] = 30
    await set_up()
    await set_limit(hass, 50)
    amp.writes.clear()
    await call(hass, "turn_on")
    assert amp.writes == [b"<11PR01\r", b"?11\r", b"<11VO19\r", b"?11\r"]
    assert hass.states.get(ZONE_1).attributes["volume_level"] == 1.0


async def test_volume_on_an_off_zone_shows_the_error(hass, amp, set_up):
    amp.zones[1]["PR"] = 0
    await set_up()
    with pytest.raises(HomeAssistantError) as caught:
        await call(hass, "volume_set", volume_level=0.5)
    assert caught.value.translation_key == "zone_off"
```

In `tests/ha/test_number.py`, `test_bass_on_an_off_zone_shows_the_error`: the same, through `number.set_value`, and the state stays at 0.

- [x] **Step 2: Commit the tests and push**

Message: "Add tests for off zones and the volume at turn-on (they fail until the next commit)". Local amp tests fail here too, on the missing names.

- [x] **Step 3: Implement**

- `amp.py`: add `ZoneOffError(AmpError)`. In `set_value`, after the query and before the Do Not Disturb check, raise it when `field` is neither `POWER` nor `DO_NOT_DISTURB`, `status.power` is false, and the attribute doesn't already equal `value`. Add `turn_on`: `set_value(zone, POWER, 1)`, then `set_value(zone, VOLUME, volume_limit)` only if the returned status shows the zone on and above the limit, and return the latest status. A turn-on that didn't take must not show the off-zone error.
- `coordinator.py`: `_error_key` maps `ZoneOffError` to `zone_off`. `async_turn_on` calls `amp.turn_on(zone, self.volume_limit(zone))` and shows the status as `async_set_value` does.
- `media_player.py`: `async_turn_on` calls `coordinator.async_turn_on(self.zone)`.
- Both strings files: `exceptions.zone_off.message` is "The zone must be on to change its settings."

- [x] **Step 4: Update the docs**

- `PROTOCOL.md`: mute survives powering a zone off and on.
- `README.md`: in the maximum volume line, a zone above its maximum gets lowered right after HA turns it on, and in What it does, changing a setting on an off zone shows an error.
- `docs/design.md`: the decisions above, the automation effect in Review Focus 4, and default-on volume in Later.
- `CLAUDE.md`, Requirements: a zone that's off rejects most set commands, and `Amp.set_value` raises `ZoneOffError`.

- [x] **Step 5: Run everything local, commit and push**

Message: "Show an error for settings on an off zone, and lower a zone to its limit when it turns on".

- [x] **Step 6: Check both runs**

Expected: the tests-only run fails on the new tests, and the implementation run passes every workflow.

The plan review changed the tests from those above: `test_stale_off_zone_still_takes_the_command` became the HA test `test_zone_turned_on_since_the_last_poll_takes_the_command`, the `writes` helper was dropped because `transport.writes` exists, and `test_turn_on_that_did_not_take_sends_no_volume` and `test_do_not_disturb_works_on_an_off_zone` were added. New amp tests reach `ZoneOffError` through `amp_module` so the rest of the file still runs before the implementation.

### Task 2: Final review, the real amp and the release

- [x] **Step 1: Final review**

A very capable reviewer reads the diff, this plan and the Review Focus. Findings that break this plan's goal enter one fix pass, each with a failing test first. Anything else goes to Later.

- [x] **Step 2: Try it on the amp**

The owner redownloads the integration in HACS and restarts Home Assistant. Claude then runs these on one zone through the REST API: set bass with the zone off (expected: an error), set a low limit, then turn on a zone that's above it (expected: the zone lands at the limit), then put everything back.

- [x] **Step 3: Close out and tag**

Tick the checkboxes, add "What changed during the build", commit and push. Then tag `v0.1.0` on that commit and push the tag.

---

## What changed during the build

- **Plan review:** `Amp.turn_on` lowers the volume only if the status shows the zone on, so a turn-on that didn't take doesn't show the off-zone error. The test changes are listed under Task 1. The review's claim that `CLAUDE.md` still listed all four hardware checks was out of date.
- **A broken commit, fixed forward:** a script that reordered the strings crashed, and the same command went on to commit and push. So the commit "Show an error for settings on an off zone, and lower a zone to its limit when it turns on" left the new message out of `strings.json`, and its Amp tests job failed. The next commit fixed it. The new message sits last in both files.
- **Red run:** the tests-only commit failed on exactly the 6 new amp tests and 3 new HA tests that need the change. The fixed commit passed 85 amp tests, 76 HA tests and hassfest.
- **Final review:** no Critical or Important findings. Doc gaps are fixed in the close-out commit. Left as they are: the card can show the zone as on next to the error for up to 30 seconds after a keypad or remote turned it off, a timeout on the lowering step shows "no answer" while the card says off until the next poll, an action aimed at several zones errors if any one is off, and one assertion in `test_bass_on_an_off_zone_shows_the_error` can't fail.
- **Not judged:** what the amp reports during a 12V page. How the error looks in HA's own UI: the API returned the message, but no one has looked at the card.
- **On the real amp (2026-10-31), on one zone:** bass with the zone off returned "The zone must be on to change its settings" and changed nothing. With the amp at volume 9 and a limit of 5 steps, HA's turn on left the zone on at volume 5, with and without Do Not Disturb on, and Do Not Disturb stayed on. The whole action took 1.35 seconds, or 1.63 with Do Not Disturb on. Nobody listened, so how long the old volume is audible hasn't been measured. A full backup was taken first.
- **Release:** a GitHub Release goes with the tag, because HACS may not show a bare tag as a version. That's from memory, not checked.
