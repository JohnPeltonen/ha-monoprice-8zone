# Commands on a Do Not Disturb Zone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner chose native execution in CLAUDE.md: Claude builds every task in this session, and a very capable reviewer checks the plan before building and the code at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every control work on a zone with Do Not Disturb on. The amp ignores those commands, so the integration turns Do Not Disturb off for a moment, sends the command again, and turns it back on.

**Architecture:** All of it lives in `Amp.set_value` in `amp.py`, under the one lock every command already holds, so polls and other commands can't run in between. `coordinator.py` and the entities don't change. `send_command` stays raw.

**Tech Stack:** Python 3.14, `pytest` for the amp tests on Windows, `pytest-homeassistant-custom-component` for the HA tests in GitHub Actions.

**Spec:** [docs/design.md](../design.md). Protocol facts: [PROTOCOL.md](../../PROTOCOL.md). Earlier plans: [Phase 1](2026-10-29-phase-1-amp-code.md), [Phase 2](2026-10-29-phase-2-home-assistant.md).

**Budget:** 1 session / about 100,000 tokens, including two small reviewer runs. For scale only: the owner waived the token stop on 2026-10-29.

## What the real amp did (2026-10-31)

The owner and Claude tested one zone on the 44518, through the integration:

| Do Not Disturb | Action | Result |
|---|---|---|
| Turned on while the zone played | none | The music kept playing. |
| On | Set volume from 14 to 12 | The status still said 14, and the amp didn't respond to the slider either. |
| On | Turn off, turn on | The status still said on, and the music kept playing. |
| Off | Set volume to 12, turn off, turn on, set volume to 13 | The status followed each command. |

Mute, source, bass, treble and balance haven't been tried with Do Not Disturb on.

The owner chose this workaround over a message telling people to turn Do Not Disturb off first. They accepted two costs: Do Not Disturb is off for up to about a second per command, so a doorbell press in that moment plays in that zone; and a serial failure in that moment can leave it off, which the switch then shows.

## Global Constraints

- `amp.py` keeps importing nothing from `homeassistant`.
- The amp tests load the module as `amp`. The HA tests import `custom_components.monoprice_8zone.*`, never `amp`.
- **The HA tests run only in GitHub Actions.** New tests are their own commit, pushed first, and that commit's message ends with "(they fail until the next commit)". Don't wait for its run. Afterwards, check both runs. The owner approved these red runs on 2026-10-29.
- Before every push, run `.venv/Scripts/python -m compileall -q custom_components tests` and `.venv/Scripts/python -m pytest -q`.
- Pushing to `main` is approved for this repo. Commit with explicit paths: `git commit <paths> -F -`, never `git add` and a later commit. Another Claude session may share this checkout, so run `git status` first and leave anything that isn't this plan's.
- Docs: no em dashes, "type" never "kind", no household names.
- Code style: `logger` with %-style formatting, minimal comments, no helpers beyond the one named here.

## Review Focus

1. **A tap on power or the volume slider on a zone with Do Not Disturb on.** The command takes effect, Do Not Disturb ends up on, and HA shows the final status. Tests: `test_ignored_command_lifts_do_not_disturb`, `test_ignored_power_command_lifts_do_not_disturb`, `test_power_with_do_not_disturb_on`, `test_volume_with_do_not_disturb_on`.
2. **A poll while Do Not Disturb is lifted.** The switch must not flicker off, and the poll must not read the lifted state. Test: `test_query_waits_until_do_not_disturb_is_back_on`.
3. **Turning the Do Not Disturb switch off.** It must stay off, even if the amp's status is late to show it. Lifting around Do Not Disturb's own command would turn it back on. Test: `test_do_not_disturb_commands_are_never_retried`.
4. **The amp sends no `#` for an ignored command.** The `#` hardware check hasn't run. The sequence must still finish, just slower. Test: `test_lifting_works_without_hash`.
5. **The command is cancelled or the port fails while Do Not Disturb is lifted.** A cancelled command must still turn it back on, and a port failure must still reach the coordinator as `PortFailedError`, so the integration reloads. Tests: `test_do_not_disturb_goes_back_on_when_cancelled`, `test_port_failure_while_do_not_disturb_is_lifted`.

## Decisions this plan makes

Task 1 adds the ones a user can see to design.md.

1. **Try first, then lift (Claude's call).** A command goes out as it does today. Only if the status shows it didn't take, and Do Not Disturb is on, does the code lift. So a zone without Do Not Disturb sends exactly the same bytes as before, every command avoids an extra query, and any command the amp doesn't ignore causes no gap. This matters because only power and volume have been tried.
2. **Do Not Disturb's own commands never lift.** See Review Focus item 3.
3. **`send_command` stays raw.** It exists to show what the amp really does, and the hardware checks depend on that.
4. **A retry that also fails raises no error.** HA shows what the amp reports, as it does for any command today.
5. **The simulated amp ignores only `PR` and `VO`,** the two fields observed. It doesn't guess about the others.

## File Structure

| File | Change |
|---|---|
| `custom_components/monoprice_8zone/amp.py` | `STATUS_ATTRIBUTES`, `Amp._set_locked`, and the lifting in `Amp.set_value`. |
| `tests/amp/fake_amp.py` | Three status replies with Do Not Disturb on. |
| `tests/amp/test_commands.py` | The amp tests. |
| `tests/ha/simulated_amp.py` | Ignores `PR` and `VO` while `DT` is on. |
| `tests/ha/test_media_player.py`, `tests/ha/test_send_command.py` | The HA tests. |
| `PROTOCOL.md`, `docs/design.md`, `README.md`, `CLAUDE.md` | Record what the amp does and what the integration does about it. |

---

### Task 1: Lift Do Not Disturb around an ignored command

**Interfaces:**
- Consumes: `Amp._query_locked(zone: int) -> ZoneStatus`, `Amp._send(data: bytes) -> None`, `set_command(zone: int, field: str, value: int) -> bytes`.
- Produces: `Amp.set_value(zone: int, field: str, value: int) -> ZoneStatus`, with the same signature. `Amp._set_locked(command: bytes) -> None` writes a set command and waits for the `#`.

- [x] **Step 1: Add the replies to `tests/amp/fake_amp.py`**

```python
ZONE_1_DND = b">1100010001100707100200 Zone1    Source02\r\n#"
ZONE_1_DND_VOLUME_20 = b">1100010001200707100200 Zone1    Source02\r\n#"
ZONE_1_OFF_DND = b">1100000001100707100200 Zone1    Source02\r\n#"
```

- [x] **Step 2: Add the amp tests to `tests/amp/test_commands.py`**

Import `BALANCE`, `BASS`, `DO_NOT_DISTURB`, `MUTE`, `POWER`, `SOURCE` and `TREBLE` from `amp`, and the three new replies from `fake_amp`.

```python
LIFTED = [b"<11VO20\r", b"?11\r", b"<11DT00\r", b"<11VO20\r", b"<11DT01\r", b"?11\r"]


async def test_ignored_command_lifts_do_not_disturb(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", b"#", b"#", ZONE_1_DND_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert (status.volume, status.do_not_disturb) == (20, True)
    assert transport.writes == LIFTED


async def test_ignored_power_command_lifts_do_not_disturb(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_OFF_DND, b"#", b"#", b"#", ZONE_1_DND)
    status = await amp.set_value(1, POWER, 1)
    assert (status.power, status.do_not_disturb) == (True, True)
    assert transport.writes == [b"<11PR01\r", b"?11\r", b"<11DT00\r", b"<11PR01\r", b"<11DT01\r", b"?11\r"]


@pytest.mark.parametrize(
    ("field", "value"),
    [(VOLUME, 10), (POWER, 1), (MUTE, 0), (TREBLE, 7), (BASS, 7), (BALANCE, 10), (SOURCE, 2)],
)
async def test_command_that_took_leaves_do_not_disturb_alone(make_amp, field, value):
    amp, transport = make_amp(b"#", ZONE_1_DND)
    await amp.set_value(1, field, value)
    assert len(transport.writes) == 2  # the command and one query


async def test_do_not_disturb_commands_are_never_retried(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND)  # the status is late to show it off
    await amp.set_value(1, DO_NOT_DISTURB, 0)
    assert transport.writes == [b"<11DT00\r", b"?11\r"]


async def test_lifting_works_without_hash(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "SET_REPLY_TIMEOUT", 0.05)
    amp, transport = make_amp(None, ZONE_1_DND, None, None, None, ZONE_1_DND_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.writes == LIFTED


async def test_query_waits_until_do_not_disturb_is_back_on(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", b"#", b"#", ZONE_1_DND_VOLUME_20, ZONE_1_DND_VOLUME_20)
    await asyncio.gather(amp.set_value(1, VOLUME, 20), amp.query_zone(1))
    assert transport.writes == [*LIFTED, b"?11\r"]


@pytest.mark.parametrize(
    ("writes", "replies"),
    [
        (3, [b"#", ZONE_1_DND, None, b"#"]),  # still waiting for the # after Do Not Disturb goes off
        (4, [b"#", ZONE_1_DND, b"#", None, b"#"]),  # still waiting for the # after the second try
    ],
)
async def test_do_not_disturb_goes_back_on_when_cancelled(make_amp, writes, replies):
    amp, transport = make_amp(*replies)
    task = asyncio.create_task(amp.set_value(1, VOLUME, 20))
    while len(transport.writes) < writes and not task.done():  # before the change, the task just finishes
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.writes[-1] == b"<11DT01\r"


async def test_port_failure_while_do_not_disturb_is_lifted(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_DND, b"#", None)
    asyncio.get_running_loop().call_later(
        0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected")
    )
    with pytest.raises(PortFailedError):
        await amp.set_value(1, VOLUME, 20)
```

- [x] **Step 3: Run them**

Run: `.venv/Scripts/python -m pytest tests/amp/test_commands.py -q`
Expected: the lifting, query-waits, cancelled and port-failure tests fail, because `set_value` doesn't lift yet. `test_command_that_took_leaves_do_not_disturb_alone` and `test_do_not_disturb_commands_are_never_retried` pass already: they pin behavior the change must keep.

- [x] **Step 4: Teach the simulated amp and add the HA tests**

In `tests/ha/simulated_amp.py`, a set command for a field in `IGNORED_WITH_DO_NOT_DISTURB = {"PR", "VO"}` changes nothing while the zone's `DT` is 1. It still answers `#`.

In `tests/ha/test_media_player.py`:

```python
async def test_power_with_do_not_disturb_on(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    await call(hass, "turn_off")
    assert hass.states.get(ZONE_1).state == "off"
    assert hass.states.get("switch.zone_1_do_not_disturb").state == "on"


async def test_volume_with_do_not_disturb_on(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    amp.writes.clear()
    await call(hass, "volume_set", volume_level=0.5)
    assert amp.writes == [b"<11VO19\r", b"?11\r", b"<11DT00\r", b"<11VO19\r", b"<11DT01\r", b"?11\r"]
    assert hass.states.get(ZONE_1).attributes["volume_level"] == pytest.approx(19 / 38)
    assert hass.states.get("switch.zone_1_do_not_disturb").state == "on"
```

In `tests/ha/test_send_command.py`:

```python
async def test_send_command_does_not_lift_do_not_disturb(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    amp.writes.clear()
    await send(hass, "<11PR00")
    assert amp.writes == [b"<11PR00\r"]
    assert amp.zones[1]["PR"] == 1
```

- [x] **Step 5: Commit the tests and push**

Message: "Add tests for commands on a Do Not Disturb zone (they fail until the next commit)". Paths: the five test files. Note the run's id. Don't wait for it.

- [x] **Step 6: Implement in `amp.py`**

Add `STATUS_ATTRIBUTES: dict[str, str]` beside `FIELD_RANGES`, mapping `POWER`, `MUTE`, `VOLUME`, `TREBLE`, `BASS`, `BALANCE` and `SOURCE` to their `ZoneStatus` attribute names. Move the existing send-and-wait-for-`#` code into `_set_locked`. Then:

```python
async with self._lock:
    await self._set_locked(command)
    status = await self._query_locked(zone)
    if field == DO_NOT_DISTURB or not status.do_not_disturb or getattr(status, STATUS_ATTRIBUTES[field]) == value:
        return status
    # The amp ignores commands for a zone with Do Not Disturb on, so lift it for this one.
    logger.debug("%r had no effect with Do Not Disturb on, lifting it", command)
    try:
        await self._set_locked(set_command(zone, DO_NOT_DISTURB, 0))
        await self._set_locked(command)
    finally:
        await self._set_locked(set_command(zone, DO_NOT_DISTURB, 1))
    return await self._query_locked(zone)
```

`ZoneStatus.power` and `.mute` are bools, and they compare equal to 1 and 0, so no conversion is needed.

- [x] **Step 7: Run everything local**

Run: `.venv/Scripts/python -m compileall -q custom_components tests` and `.venv/Scripts/python -m pytest -v`
Expected: all pass, with no change to any existing test.

- [x] **Step 8: Update the docs**

`PROTOCOL.md`, PA section. Replace "Observed wiring; full chime test pending." with "Observed wiring, and a doorbell chime rang in several zones. Observed." Add after the Do Not Disturb line:

> - With Do Not Disturb on, a zone keeps playing, but the amp ignores its power and volume commands: its status doesn't change, and neither does the sound. With it off, the same commands work. Observed on one zone. Mute, source, bass, treble and balance haven't been tried.

`docs/design.md`, the Do Not Disturb bullet under "What version 0.1.0 does": add "Its controls still work. See Set commands." Under "Set commands", after the bullet about querying:

> - The amp ignores power and volume commands for a zone with Do Not Disturb on. So if the status shows a command didn't take and Do Not Disturb is on, the code turns Do Not Disturb off, sends the command again, turns Do Not Disturb back on, and queries again. It holds the lock throughout, so a poll can't see Do Not Disturb off. Do Not Disturb is off for up to about a second, and a doorbell press in that moment plays in that zone. **(The owner chose this workaround on 2026-10-31.** Trying the command first is Claude's call: a zone without Do Not Disturb sends what it always did, and a command the amp doesn't ignore causes no gap.)

`README.md`, the Do Not Disturb bullet: add "The amp ignores power and volume commands for a zone with it on, so the integration turns it off for a moment, sends the command, and turns it back on. A doorbell press in that moment would play in that zone."

`CLAUDE.md`, Requirements, after "After a set command":

> - **Do Not Disturb:** the amp ignores power and volume commands for a zone with it on. When a set command didn't take and Do Not Disturb is on, `Amp.set_value` turns it off, sends the command again and turns it back on, under one hold of the lock. `send_command` stays raw.

- [x] **Step 9: Commit the implementation and docs, and push**

Message: "Make commands work on a Do Not Disturb zone". Paths: `amp.py` and the four docs.

- [x] **Step 10: Check both runs**

Run: `gh run watch <run-id> --exit-status` for each.
Expected: in the tests-only run, "Amp tests" fails on the new amp tests from Step 3, and "Home Assistant tests" fails on `test_power_with_do_not_disturb_on` and `test_volume_with_do_not_disturb_on`. `test_send_command_does_not_lift_do_not_disturb` passes from the start: it pins behavior the change must keep. The implementation run passes every workflow.

### Task 2: Final review and the real amp

- [x] **Step 1: Final review**

A very capable reviewer reads the diff, this plan and the Review Focus. Findings that break this plan's goal enter one fix pass, each with a failing test first. Anything else goes to Later, or to an issue if the owner confirms one.

- [x] **Step 2: Try it on the amp**

The owner redownloads the integration in HACS, restarts Home Assistant, and turns Do Not Disturb on for a zone that's playing. Claude sends a volume change, off, and on through its Home Assistant connection and reads the state after each. The owner confirms that the sound followed and that the switch stayed on.
Expected: the state follows each command. Record the result in PROTOCOL.md.

Until this step, every observation came from commands sent seconds apart, and the lift sends them in quick succession. If the amp drops the retried command or the command that turns Do Not Disturb back on, first try a 100 ms pause after each of those Do Not Disturb commands. `send_command` can't show this problem: it waits at least 0.3 seconds after each command, so the same commands sent by hand would probably work.

- [x] **Step 3: Close out the plan**

Tick the checkboxes, add "What changed during the build", and commit the plan.

---

## What changed during the build

- **Plan review.** The cancelled-command test would have hung before the implementation existed, so its loop now also stops when the task ends. The command that turns Do Not Disturb off moved inside the `try`, with a second cancel test. Step 2 gained its imports and all seven fields.
- **Final review.** No code changes. `design.md` now says "power and volume controls", and that the workaround worked on one zone.
- **`test_send_command_does_not_lift_do_not_disturb`** passed from the start, as planned. Ruled, not broken on purpose: it pins behavior `send_raw` already had.
- **The real amp.** On one zone with Do Not Disturb on, the owner heard power on, a volume change and power off work, and the switch was still on afterwards with the zone off. Claude's reads through the Home Assistant connection followed each command. No pause between commands was needed.

## Later
From the plan review, minor:

- If Do Not Disturb doesn't come back on after a lift, nothing is logged. The switch shows it right away, because the final status comes from the amp. A warning in the log would make the cause easier to find.
- If the amp sends no `#`, each lifted command takes about 2 seconds, and other zones wait behind it. The `#` hardware check will show whether this can happen.

## Remaining phases

### Phase 3: Hardware checks and release

Run the four hardware checks with the owner, record the results in PROTOCOL.md, fix the "port in use" wording, update the README's status, then tag `v0.1.0`.
