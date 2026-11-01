# Maximum Volume per Zone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner chose native execution in CLAUDE.md: Claude builds every task in this session, and a very capable reviewer checks the plan before building and the code at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each zone a Maximum volume setting, so an accidental swipe of the volume slider can't go past it. The volume slider's 100% means the zone's maximum.

**Architecture:** The limit is stored per zone in the config entry's options. `AmpCoordinator` reads and changes it. A new number entity on each zone's device page calls the coordinator, and the media player scales its volume through the coordinator's limit. `amp.py` doesn't change.

**Tech Stack:** Home Assistant 2026.10 (`NumberEntity`, `async_update_entry`), `pytest-homeassistant-custom-component` in GitHub Actions.

**Spec:** the owner's request on 2026-10-31, and [docs/design.md](../design.md).

**Budget:** 1 session / about 150,000 tokens, including two reviewer runs. For scale only: the owner waived the token stop on 2026-10-29.

## What the owner asked for

- A maximum volume per zone that comes with the integration, enforced at least through the UI.
- "The volume slider should represent 0 to 100% of the allowed maximum. So, if the allowed maximum is only 50% (or 19 steps), then 100% on the volume slider represents 19 steps on the amp."

## Global Constraints

- `amp.py` keeps importing nothing from `homeassistant`. This plan doesn't change it.
- Entities hold no logic beyond mapping values. They call `AmpCoordinator` methods.
- `strings.json` and `translations/en.json` hold the same content.
- **The HA tests run only in GitHub Actions.** New tests are their own commit, pushed first, and that commit's message ends with "(they fail until the next commit)". Afterwards, check both runs. The owner approved these red runs on 2026-10-29.
- Before every push, run `.venv/Scripts/python -m compileall -q custom_components tests` and `.venv/Scripts/python -m pytest -q`.
- Pushing to `main` is approved for this repo. Commit with explicit paths. Another Claude session may share this checkout, so run `git status` first and leave anything that isn't this plan's.
- Docs: no em dashes, "type" never "kind", no household names.

## Review Focus

1. **A swipe to the top of the slider.** The amp goes to the zone's limit, never higher. Test: `test_slider_top_is_the_limit`.
2. **A keypad or remote already took the zone above the limit.** The slider shows 100%, no command is sent by itself, and the next volume change lands at or below the limit, including volume down. Test: `test_zone_above_the_limit`.
3. **Setting the limit.** It must not reload the integration, which would close the port and interrupt other zones, and must not send anything to the amp. The media player updates at once. Test: `test_setting_the_limit_does_not_touch_the_amp`.
4. **A restart or reload, or saving the Zones and sources screen.** The limit must survive all of them. A lost limit silently means full volume. Tests: `test_limit_is_saved`, `test_limit_survives_a_reload`, `test_options_keep_the_limits`.
5. **Do Not Disturb.** A limited volume command on a zone with it on still goes through the lift. Test: `test_limit_with_do_not_disturb_on`.

## Decisions this plan makes

Task 1 adds these to design.md.

1. **The slider scales to the limit (the owner's call).** Everything that uses HA's volume percentage scales too, so an automation or voice command asking for 50% gets 50% of the limit.
2. **The setting is a percentage of the amp's full volume (Claude's call),** from 5% to 100% in steps of 1, starting at 100%. A zone's limit in amp steps is `round(percent / 100 * 38)`. The floor keeps the limit from reaching 0 steps.
3. **Stored in the entry's options (Claude's call),** under `max_volumes`, keyed by zone number as a string. Options are there before any entity starts, so there's no moment at startup without a limit, which restoring the entity's last state would allow. Zones without a key are at 100%, so existing installs change nothing.
4. **Lowering the limit doesn't change what's playing (Claude's call; the owner saw this and didn't change it).** A zone above its limit stays there and shows 100% until its next volume change.
5. **From above the limit, volume up and down both start at the limit.** Up goes to the limit, and down goes one step below it, so the slider moves right away instead of sitting at 100% for several presses. That's a sudden drop, in the safe direction (Claude's call).
6. **Not limited:** wall keypads and IR remotes, which reach the amp directly, and `send_command`, which stays raw.
7. **The setting follows its zone's availability.** If the zone doesn't answer, the Maximum volume slider greys out with the zone's other controls. The stored limit still applies.

---

### Task 1: The limit, its setting, and the scaled slider

**Files:**
- Modify: `const.py`, `coordinator.py`, `media_player.py`, `number.py`, `config_flow.py`, `strings.json`, `translations/en.json` in `custom_components/monoprice_8zone/`
- Modify: `README.md`, `docs/design.md`, `CLAUDE.md`
- Test: `tests/ha/test_media_player.py`, `tests/ha/test_number.py`, `tests/ha/test_config_flow.py`

**Interfaces:**
- Produces: in `const.py`, `CONF_MAX_VOLUMES = "max_volumes"` and `MAX_VOLUME = 38` (moved from `media_player.py`).
- Produces: `AmpCoordinator.max_volume_percent(zone: int) -> int`, `AmpCoordinator.volume_limit(zone: int) -> int` (amp steps), and `AmpCoordinator.async_set_max_volume(zone: int, percent: int) -> None`.

- [ ] **Step 1: Add the tests**

In `tests/ha/test_media_player.py`, with a helper that calls `number.set_value` on `number.zone_1_maximum_volume`:

```python
async def test_slider_top_is_the_limit(hass, amp, set_up):
    await set_up()
    await set_limit(hass, 50)
    amp.writes.clear()
    await call(hass, "volume_set", volume_level=1.0)
    assert amp.writes == [b"<11VO19\r", b"?11\r"]
    assert hass.states.get(ZONE_1).attributes["volume_level"] == 1.0


async def test_slider_scales_to_the_limit(hass, amp, set_up):
    await set_up()
    await set_limit(hass, 50)
    assert hass.states.get(ZONE_1).attributes["volume_level"] == pytest.approx(10 / 19)
    await call(hass, "volume_set", volume_level=0.2)
    assert amp.zones[1]["VO"] == 4


async def test_volume_up_stops_at_the_limit(hass, amp, set_up):
    amp.zones[1]["VO"] = 19
    await set_up()
    await set_limit(hass, 50)
    await call(hass, "volume_up")
    assert amp.zones[1]["VO"] == 19


@pytest.mark.parametrize(("service", "volume"), [("volume_down", 18), ("volume_up", 19)])
async def test_zone_above_the_limit(hass, amp, set_up, service, volume):
    amp.zones[1]["VO"] = 30
    await set_up()
    amp.writes.clear()
    await set_limit(hass, 50)
    assert amp.writes == []
    assert amp.zones[1]["VO"] == 30
    assert hass.states.get(ZONE_1).attributes["volume_level"] == 1.0
    await call(hass, service)
    assert amp.zones[1]["VO"] == volume


async def test_limit_belongs_to_one_zone(hass, amp, set_up):
    await set_up()
    await set_limit(hass, 50)
    await hass.services.async_call(
        "media_player", "volume_set", {"entity_id": "media_player.zone_2", "volume_level": 1.0}, blocking=True
    )
    assert amp.zones[2]["VO"] == 38
    await call(hass, "volume_set", volume_level=1.0)
    assert amp.zones[1]["VO"] == 19


async def test_limit_with_do_not_disturb_on(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    await set_limit(hass, 50)
    await call(hass, "volume_set", volume_level=1.0)
    assert amp.zones[1]["VO"] == 19
    assert amp.zones[1]["DT"] == 1


async def test_limit_survives_a_reload(hass, amp, entry, set_up):
    await set_up()
    await set_limit(hass, 50)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get("number.zone_1_maximum_volume").state) == 50
    await call(hass, "volume_set", volume_level=1.0)
    assert amp.zones[1]["VO"] == 19
```

In `tests/ha/test_number.py`:

```python
async def test_maximum_volume_starts_at_100(hass, set_up, entity_registry):
    await set_up()
    assert float(hass.states.get("number.zone_1_maximum_volume").state) == 100
    entity = entity_registry.async_get("number.zone_1_maximum_volume")
    assert entity.entity_category is EntityCategory.CONFIG


async def test_setting_the_limit_does_not_touch_the_amp(hass, amp, set_up):
    await set_up()
    amp.writes.clear()
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.zone_1_maximum_volume", "value": 50}, blocking=True
    )
    await hass.async_block_till_done()
    assert amp.writes == []
    assert len(amp.connections) == 1  # no reload
    assert float(hass.states.get("number.zone_1_maximum_volume").state) == 50
```

Also in `tests/ha/test_number.py`, `test_limit_is_saved`: set zone 1's limit to 50, then to 60, call `flush_store(hass.config_entries._store)`, and assert that this entry in `hass_storage["core.config_entries"]` has `options["max_volumes"] == {"1": 60}`.

In `tests/ha/test_config_flow.py`, `test_options_keep_the_limits`: set zone 1's limit to 50, save the options flow with new source names as `test_options_change_zones_and_sources` does, then assert `entry.options["max_volumes"] == {"1": 50}`.

- [ ] **Step 2: Commit the tests and push**

Message: "Add tests for a maximum volume per zone (they fail until the next commit)". Don't wait for the run.

- [ ] **Step 3: Implement**

- `coordinator.py`: `max_volume_percent` reads `self.config_entry.options.get(CONF_MAX_VOLUMES, {}).get(str(zone), 100)`. `volume_limit` returns `round(percent / 100 * MAX_VOLUME)`. `async_set_max_volume` calls `hass.config_entries.async_update_entry` with a new options dict and a new `max_volumes` dict inside it, then `self.async_update_listeners()`. Never change the nested dict in place: HA saves only if the options compare different.
- `media_player.py`: `volume_level` is `min(self.status.volume / limit, 1.0)`. `async_set_volume_level` sends `round(volume * limit)`. `async_volume_up` sends `min(self.status.volume + 1, limit)`. `async_volume_down` sends `max(min(self.status.volume, limit) - 1, 0)`.
- `number.py`: `MaximumVolumeNumber(ZoneEntity, NumberEntity)`, key and translation key `max_volume`, `native_min_value=5`, `native_max_value=100`, `native_step=1`, `native_unit_of_measurement=PERCENTAGE`, `NumberMode.SLIDER`, `EntityCategory.CONFIG`. It reads `max_volume_percent` and sets with `async_set_max_volume(self.zone, round(value))`. Setup adds it beside `NUMBERS`, because it has no amp field or offset.
- `config_flow.py`: the options flow saves `{**self.config_entry.options, **options}`, so the limits survive.
- Both strings files: `entity.number.max_volume.name` is "Maximum volume".

- [ ] **Step 4: Update the docs**

- `README.md`, What it does: "A maximum volume for each zone, on the zone's device page. The zone's volume slider then runs from 0 to that maximum, so a stray swipe can't go past it. It doesn't limit wall keypads or IR remotes."
- `docs/design.md`: add the decisions above to the volume mapping and What version 0.1.0 does.
- `CLAUDE.md`, Entities: add `number` per zone for Maximum volume, stored in the entry's options, not sent to the amp.

- [ ] **Step 5: Run everything local, commit and push**

Run: `.venv/Scripts/python -m compileall -q custom_components tests` and `.venv/Scripts/python -m pytest -q`
Expected: all pass. Message: "Add a maximum volume for each zone".

- [ ] **Step 6: Check both runs**

Run: `gh run watch <run-id> --exit-status` for each.
Expected: in the tests-only run, "Amp tests" passes and "Home Assistant tests" fails on the new tests. They need the new entity, which doesn't exist yet. The implementation run passes every workflow.

### Task 2: Final review and the real amp

- [ ] **Step 1: Final review**

A very capable reviewer reads the diff, this plan and the Review Focus. Findings that break this plan's goal enter one fix pass, each with a failing test first. Anything else goes to Later.

- [ ] **Step 2: Try it on the amp**

The owner redownloads the integration in HACS and restarts Home Assistant. On one zone, the owner sets a limit and swipes the volume slider to the top.
Expected: the sound stops at the limit, the slider sits at 100%, and the limit is still there after another restart.

- [ ] **Step 3: Close out the plan**

Tick the checkboxes, add "What changed during the build", and commit the plan.

---

## Remaining phases

### Phase 3: Hardware checks and release

Run the four hardware checks with the owner, record the results in PROTOCOL.md, fix the "port in use" wording, update the README's status, then tag `v0.1.0`.
