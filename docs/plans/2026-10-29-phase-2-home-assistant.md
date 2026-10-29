# Phase 2: The Home Assistant Side Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner chose native execution: Claude builds every task in this session, and a very capable reviewer checks the plan before building and the code at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 1 amp code into a working Home Assistant integration (setup and unload, polling, a device per zone with its media player, switch and sliders, the setup screens, and the `send_command` action), tested in GitHub Actions. First, close the three amp test gaps the Phase 1 review left.

**Architecture:** `__init__.py` opens the port with `open_amp`, hands the `Amp` to one `AmpCoordinator` (a `DataUpdateCoordinator`) and sets up three platforms. The coordinator owns everything HA does with the amp: the 30-second poll, set commands followed by a state update, raw commands, and turning amp errors into HA errors (reloading the integration when the port fails). Entities are thin: each reads its zone's `ZoneStatus` from the coordinator and calls coordinator methods. The HA tests drive the real `Amp` code through a simulated 44518 that answers commands byte for byte and locks its port the way `serialx` does.

**Tech Stack:** Home Assistant 2026.10 (`probatio` forms, `SerialPortSelector`, `DataUpdateCoordinator`, `OptionsFlowWithReload`), `pytest-homeassistant-custom-component` 0.13.371, GitHub Actions.

**Spec:** [docs/design.md](../design.md). Protocol facts: [PROTOCOL.md](../../PROTOCOL.md). Phase 1: [2026-10-29-phase-1-amp-code.md](2026-10-29-phase-1-amp-code.md).

**Budget:** 1 session / tokens not tracked (the owner waived the token stop on 2026-10-29). For scale: this phase has the same two reviewer runs as Phase 1, which used about 250,000 tokens each.

## Global Constraints

- Home Assistant 2026.10.0 or newer, Python 3.14. The HA tests pin `pytest-homeassistant-custom-component==0.13.371`, which pins `homeassistant==2026.10.0`, the minimum in `hacs.json`.
- HA's tests never install integration requirements, so `requirements_test_ha.txt` also pins the ones this integration and `usb` need: `serialx==1.11.0` and `aiousbwatcher==1.1.2`.
- Imports are absolute: `from custom_components.monoprice_8zone.const import DOMAIN`. No relative imports. HA code and HA tests import the amp module as `custom_components.monoprice_8zone.amp`, never as `amp`.
- `amp.py` keeps importing nothing from `homeassistant`. This phase doesn't change it.
- Forms use `probatio`, never `voluptuous`.
- HA 2026.10 deprecations to avoid: `DeviceInfo(via_device=...)` (use `via_device_id`, from `dr.async_get_device_id_by_identifier`), and `device_registry.async_get_device` (use `async_get_device_by_identifier`; called from a test, the old one raises).
- hassfest wants manifest keys in the order domain, name, then alphabetical, and each `exceptions` entry in the strings files as `{"message": "..."}`.
- Domain `monoprice_8zone`. One config entry per HA install (`"single_config_entry": true`). Zones 1 to 8 only.
- Entities hold no amp logic. They call `AmpCoordinator` methods, which own the error handling.
- `strings.json` and `translations/en.json` hold the same content. HA reads only `translations/en.json` for a custom integration; hassfest checks both.
- UI text and docs: no em dashes; "type", never "kind". hassfest also rejects HTML tags, URLs, and leading or trailing spaces in UI text.
- Code style: snake_case, PascalCase classes, UPPER_CASE constants, `logger = logging.getLogger(__name__)` with %-style formatting, `T | None`, minimal docstrings.
- **The HA tests run only in GitHub Actions.** So in every task with HA tests, the new tests are their own commit, pushed first. That commit's message ends with "(they fail until the next commit)". Don't wait for its run: write the implementation while CI runs, then push it as the next commit. Afterwards, check both runs. The tests-only run's "Home Assistant tests" job must fail on exactly the new tests, for the expected reason, and the implementation run must pass both workflows. The owner approved these red runs in the public Actions history on 2026-10-29.
- If a new test never failed for the expected reason (for example it errored on a fixture mistake that was then fixed), prove it before the task is done: push a commit that breaks the implementation on purpose, see that test fail, then push the revert. Ledger it.
- Before every push, run `.venv/Scripts/python -m compileall -q custom_components tests` (catches syntax errors without HA) and `.venv/Scripts/python -m pytest -q`.
- Pushing to `main` is approved for this repo (CLAUDE.md, Working agreements). Commit with explicit paths.

## Review Focus

1. **The USB adapter is unplugged while HA is running, and plugged back in later.** At the next poll the integration reloads itself; setup keeps retrying while the port is missing; when the port is back it recovers on its own, with no HA restart. Test: `test_port_failure_reloads_and_waits_for_the_port` (Task 3).
2. **A reload or a port change while the integration holds the port.** The integration must never report "port in use" against its own connection. The simulated amp refuses a second open of a device that's already open, as serialx's lock does. Tests: `test_reload_reopens_the_port` (Task 2), `test_reconfigure_same_device_skips_the_check` (Task 6).
3. **Two quick taps on volume up, or a tap in the middle of a poll.** Each tap moves one step from the latest volume, so two taps move two steps, and a poll that was already running doesn't put the old volume back. Tests: `test_volume_up_twice_quickly_moves_two_steps` (Task 3), `test_set_during_a_poll_is_kept` (Task 2).
4. **One zone stops answering**, for example zone 7 or 8 before the hardware check. Only that zone's entities go unavailable, and the other zones keep working. A command sent to that zone before a poll notices says the amp didn't answer; after that, HA sends it no commands. Tests: `test_silent_zone_is_unavailable` and `test_command_when_the_amp_does_not_answer` (Task 3).
5. **The setup check fails after the port opened** (the amp didn't answer), and the owner fixes the cable and submits again. The second try works, because the first try closed the port. Test: `test_user_flow_recovers_after_no_answer` (Task 5).

## Decisions this plan makes

Calls beyond design.md. Task 8 adds the ones a user can see to design.md, marked (Claude's call).

1. **Where the settings live.** The entry's `data` holds the port. Its `options` hold the zones and source names from the first setup on, so the options screen edits the same place.
2. **Quick taps.** Every platform sets `PARALLEL_UPDATES = 1`. HA then runs one action at a time per platform (`Entity.async_request_call`), so a second volume press reads the volume the first one set. This settles the "rapid presses" item in Phase 1's Later list without touching `amp.py`.
3. **Closing the port.** Setup calls `entry.async_on_unload(amp.close)` right after the port opens. HA runs it on unload, after the entities are gone, and after any failed setup. One line covers "close on unload" and "close when setup fails after the port opened" (a Phase 1 review recommendation).
4. **Reload on port failure** happens only when the entry is loaded. During setup, `ConfigEntryNotReady` already makes HA retry.
5. **A source name that isn't in the list** (from an automation, for example) gets a validation error that names it. HA's media player doesn't check this itself.
6. **A command that arrives while the integration reloads** says "The integration is reloading. Try again in a moment." instead of a generic error.
7. **At least one zone** must be enabled, at setup and in the options.
8. **Names.** The entry's title is "Monoprice 44518". The zone checkboxes read "Zone 1" to "Zone 8". The media players use device class `receiver`, as the built-in integration does.
9. **Two CI jobs.** The amp tests and the HA tests run in separate jobs. Once the HA test plugin is installed it applies its checks (for example, no leftover tasks or timers) to every test in the run, and the amp tests weren't written for those.
10. **No `AmpClosedError`** (an optional item in Phase 1's Later list). The coordinator catches `PortFailedError` and `AmpTimeoutError` by name and treats any other `AmpError` as "closed".
11. **Tests pin HA 2026.10.0**, the minimum `hacs.json` declares, rather than the latest patch (2026.10.4).
12. **A set command that runs in the middle of a poll wins** over the poll's older reading of that zone. `query_zones` takes the lock once per zone, so a tap can run between two zones' queries, and the poll's result for the tapped zone predates the tap. The coordinator keeps the statuses that set commands return while a poll runs, and lays them over the poll's results. (Found by the plan review.)

## File Structure

| File | What it holds |
|---|---|
| `custom_components/monoprice_8zone/__init__.py` | Setup and unload, the amp device, removing disabled zones' devices, registering the action. |
| `custom_components/monoprice_8zone/const.py` | `DOMAIN`, option keys, zone and source numbers, the poll interval. |
| `custom_components/monoprice_8zone/coordinator.py` | `AmpCoordinator` and the `AmpConfigEntry` type. |
| `custom_components/monoprice_8zone/entity.py` | `ZoneEntity`, the base of every zone entity. |
| `custom_components/monoprice_8zone/media_player.py`, `switch.py`, `number.py` | The platforms. |
| `custom_components/monoprice_8zone/config_flow.py` | The setup screens, reconfigure, and options. |
| `custom_components/monoprice_8zone/services.py`, `services.yaml` | The `send_command` action. |
| `custom_components/monoprice_8zone/strings.json`, `translations/en.json` | All UI text. |
| `custom_components/monoprice_8zone/manifest.json` | Gains `config_flow` and `single_config_entry`. |
| `requirements_test_ha.txt` | Packages for the HA tests (CI only). |
| `pyproject.toml` | Gains `pythonpath = ["."]`: HA finds the integration by importing `custom_components`, so the repo root must be on the path. |
| `tests/conftest.py` | Leaves out `tests/ha` when HA isn't installed, so a bare `pytest` works on Windows. |
| `tests/test_translations.py` | Checks that `strings.json` and `translations/en.json` match. Runs on Windows. |
| `tests/ha/simulated_amp.py` | `SimulatedAmp`: a 44518 that answers commands and locks its port. |
| `tests/ha/conftest.py` | Fixtures `amp`, `entry` and `set_up`. |
| `tests/ha/test_*.py` | One file per area. No HA test file shares a name with an amp test file. |
| `.github/workflows/tests.yaml` | Two jobs: "Amp tests" and "Home Assistant tests". |

Local command, from the repo root on Windows: `.venv/Scripts/python -m pytest -v` (the amp tests and the translations test).

Checking CI after a push. With `-v`, the HA test plugin turns on debug logging for everything, so read the logs through `grep`:

```bash
gh run list --commit <sha> --json databaseId,workflowName,status,conclusion
gh run watch <id> --exit-status
gh run view <id> --log | grep -E "(PASSED|FAILED|ERROR) tests/| passed| failed"
gh run view <id> --log-failed | grep -E "(FAILED|ERROR) tests/|Error|assert"
```

UI text used across tasks (Task 2 adds the `exceptions` section, later tasks add theirs):

| Key | Text |
|---|---|
| `port_in_use` | The port is in use. If the built-in Monoprice integration is set up, delete it first. |
| `port_not_found` | The port doesn't exist. Check that the USB adapter is plugged in. |
| `no_answer` | The amp didn't answer. Check that it's powered on, the cable is connected, and the rear switch is set to MASTER. |
| `port_failed` | The serial port stopped working. The integration is reconnecting. |
| `closed` | The integration is reloading. Try again in a moment. |

---

### Task 1: Close the amp test gaps from the Phase 1 review

**Files:**
- Modify: `tests/amp/test_commands.py`, `tests/amp/test_connection.py`. No production code changes.

- [x] **Step 1: Add the guard tests**

In `test_commands.py`, time the call in `test_set_value_without_hash_still_queries` (it already shortens `SET_REPLY_TIMEOUT` to 0.05 s):

```python
    loop = asyncio.get_running_loop()
    started = loop.time()
    status = await amp.set_value(1, VOLUME, 20)
    assert loop.time() - started < 0.5  # waited SET_REPLY_TIMEOUT, not the 1-second STATUS_TIMEOUT
```

Add:

```python
async def test_send_raw_collects_past_a_hash(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, _ = make_amp([ZONE_1, ZONE_2])  # like the reply to ?10: one zone after another
    assert await amp.send_raw("?10") == ZONE_1 + ZONE_2


async def test_send_raw_waits_for_a_slow_first_byte(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, transport = make_amp(None)
    asyncio.get_running_loop().call_later(0.2, transport.protocol.data_received, ZONE_1)
    assert await amp.send_raw("?11") == ZONE_1
```

In `test_connection.py`, `fake_opener` records `(url, baudrate, kwargs)`, and `test_open_amp_opens_the_port_at_9600` asserts `calls == [("/dev/ttyUSB0", 9600, {})]`: `open_amp` passes nothing that would override serialx's defaults (8N1, no flow control, exclusive use).

- [x] **Step 2: Run the tests**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 57 passed. These tests guard code that already works.

- [x] **Step 3: Prove each test catches its regression**

The code is already correct, so each test's failing run comes from a deliberate break, applied and undone with the Phase 1 `mutate.py` in the scratchpad. Each break must fail the named test:

| Break | Test that must fail |
|---|---|
| `set_value` waits `STATUS_TIMEOUT` for the `#` | `test_set_value_without_hash_still_queries` |
| `send_raw` gives up after `RAW_QUIET_GAP` even before the first byte | `test_send_raw_waits_for_a_slow_first_byte` |
| `send_raw` stops at the first `#` | `test_send_raw_collects_past_a_hash` |
| `open_amp` passes `xonxoff=True` | `test_open_amp_opens_the_port_at_9600` |
| `open_amp` passes `exclusive=False` | `test_open_amp_opens_the_port_at_9600` |

Expected: all five killed, and `amp.py` restored byte for byte.

- [x] **Step 4: Commit and push**

```bash
git commit tests/amp -m "Close the amp test gaps from the Phase 1 review"
git push origin main
```

Expected: both workflows pass.

---

### Task 2: HA test setup, setup and unload

**Files:**
- Create: `custom_components/monoprice_8zone/const.py`, `coordinator.py`, `strings.json`, `translations/en.json`; `requirements_test_ha.txt`; `tests/conftest.py`, `tests/test_translations.py`; `tests/ha/simulated_amp.py`, `tests/ha/conftest.py`, `tests/ha/test_init.py`
- Modify: `custom_components/monoprice_8zone/__init__.py`, `manifest.json`; `pyproject.toml`; `.github/workflows/tests.yaml`

**Interfaces:**
- Consumes, from `amp.py`: `open_amp`, `Amp.query_zones`, `Amp.set_value`, `Amp.close`, `ZoneStatus`, `AmpError`, `AmpTimeoutError`, `PortFailedError`, `PortInUseError`, `PortNotFoundError`, and the timeout constants.
- Produces:
  - `const.py`: `DOMAIN = "monoprice_8zone"`, `CONF_ZONES = "zones"`, `CONF_SOURCES = "sources"`, `ZONES = (1, 2, 3, 4, 5, 6, 7, 8)`, `SOURCES = (1, 2, 3, 4, 5, 6)`, `SCAN_INTERVAL = timedelta(seconds=30)`.
  - The config entry: `data = {CONF_PORT: str}`, and `options = {CONF_ZONES: list[int], CONF_SOURCES: dict[str, str]}`. Zones are sorted. Sources map a source number, as a string such as `"2"`, to its name, and hold named sources only.
  - `coordinator.py`: `type AmpConfigEntry = ConfigEntry[AmpCoordinator]`, and `class AmpCoordinator(DataUpdateCoordinator[dict[int, ZoneStatus | None]])` with `__init__(self, hass: HomeAssistant, entry: AmpConfigEntry, amp: Amp) -> None`, attributes `amp: Amp` and `zones: list[int]`, and `async def async_set_value(self, zone: int, field: str, value: int) -> None`.
  - Exception translation keys: `port_in_use`, `port_not_found`, `no_answer`, `port_failed`, `closed`.
  - In the tests: `SimulatedAmp`, `SimulatedConnection`, and the fixtures `amp`, `entry` and `set_up`, as below.

`tests/ha/simulated_amp.py`:
- `SimulatedAmp()` keeps the state of zones 1 to 8, each a dict keyed by PROTOCOL.md's field names, starting at the captured values: `{"PA": 0, "PR": 1, "MU": 0, "DT": 0, "VO": 10, "TR": 7, "BS": 7, "BL": 10, "CH": 2, "LS": 0}`. Attributes: `zones`; `silent_zones: set[int]`, zones that answer nothing; `open_error: OSError | None`, raised by every open while it's set; `connections: list[SimulatedConnection]`; `writes: list[bytes]`, every write on every connection.
- `async def create_serial_connection(self, loop, protocol_factory, url, baudrate, **kwargs)` has serialx's signature. It raises `open_error` if that's set. It raises `OSError(errno.EBUSY, ...)` if a connection to the same device (`os.path.realpath(url)`) is still open, as serialx's lock does. Otherwise it creates a `SimulatedConnection`, calls `protocol.connection_made`, and returns `(connection, protocol)`.
- Replies. `?1z\r` gets `>1z`, the ten fields as two digits each in PROTOCOL.md's order, then ` Zonez    Source0c\r\n#`, where `c` is the zone's source. For zone 1 at the starting values that is exactly the PROTOCOL.md capture. `<1zPPuu\r` sets the field and gets `#`. A silent zone gets nothing.
- `SimulatedConnection(asyncio.Transport)` has `port` (the URL as given), `device` (its realpath) and `closed`. `write()` records the bytes and delivers the reply with `loop.call_soon`. `close()`, unless already closed, sets `closed` and calls `protocol.connection_lost(None)` soon. `unplug()` sets `closed` and calls `protocol.connection_lost(OSError(errno.EIO, "device disconnected"))`.

`tests/ha/conftest.py`:
- An autouse fixture that requests `enable_custom_integrations`.
- `amp`: a `SimulatedAmp`. It patches `serialx.create_serial_connection` with the amp's method, and shortens `STATUS_TIMEOUT` and `SET_REPLY_TIMEOUT` to 0.05 s, `RAW_QUIET_GAP` to 0.05 s and `RAW_TIMEOUT` to 0.2 s in `custom_components.monoprice_8zone.amp`.
- `entry`: a `MockConfigEntry`, already added to hass, with title "Monoprice 44518", `data={CONF_PORT: "/dev/ttyUSB0"}` and `options={CONF_ZONES: [1, 2, 3, 4, 5, 6, 7, 8], CONF_SOURCES: {"2": "Sonos", "5": "TV"}}`.
- `set_up`: returns `async def set_up() -> None`, which sets the entry up, asserts that worked, and waits for HA to finish (`hass.async_block_till_done()`). It requests `amp` and `entry`, so a test can change the amp before calling it.

- [x] **Step 1: Split CI and add the HA test setup**

- `requirements_test_ha.txt`: `pytest-homeassistant-custom-component==0.13.371`, `serialx==1.11.0`, `aiousbwatcher==1.1.2`, with a comment on why each is there.
- `pyproject.toml`: add `pythonpath = ["."]` with the reason as a comment.
- `tests/conftest.py`: `collect_ignore = ["ha"]` when `importlib.util.find_spec("homeassistant")` is `None`.
- `.github/workflows/tests.yaml`: two jobs, same triggers. Each: `actions/checkout@v7`, then `actions/setup-python@v7` with Python 3.14, `cache: pip` and its requirements file as `cache-dependency-path`. "Amp tests" runs `pip install -r requirements_test.txt` and `pytest -v`. "Home Assistant tests" runs `pip install -r requirements_test_ha.txt` and `pytest tests/ha -v`.
- `tests/ha/simulated_amp.py` and `tests/ha/conftest.py`, as above.

- [x] **Step 2: Write the failing tests**

`tests/test_translations.py`:

```python
def test_translations_match_strings():
    folder = Path(__file__).resolve().parents[1] / "custom_components" / "monoprice_8zone"
    strings = json.loads((folder / "strings.json").read_text(encoding="utf-8"))
    assert json.loads((folder / "translations" / "en.json").read_text(encoding="utf-8")) == strings
```

`tests/ha/test_init.py`:

```python
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
```

The two tests that need the 30-second timer are in Task 3: the coordinator only starts its timer once an entity listens to it.

- [x] **Step 3: Run what runs locally**

Run: `.venv/Scripts/python -m compileall -q custom_components tests`, then `.venv/Scripts/python -m pytest -v`
Expected: no output from `compileall`. `test_translations_match_strings` FAILS with `FileNotFoundError` (no `strings.json` yet); the 57 amp tests pass; `tests/ha` is left out.

- [x] **Step 4: Commit and push the tests**

```bash
git commit requirements_test_ha.txt pyproject.toml .github/workflows/tests.yaml tests -m "Add the HA test setup and the setup and unload tests (they fail until the next commit)"
git push origin main
```

Don't wait for the run. Expected, checked in Step 7: "Amp tests" fails only on `test_translations_match_strings`; "Home Assistant tests" fails because `custom_components.monoprice_8zone.const` doesn't exist; hassfest passes.

- [x] **Step 5: Implement setup, unload and the coordinator**

- `manifest.json`: add `"single_config_entry": true` between `requirements` and `version`.
- `const.py` as in Interfaces.
- `AmpCoordinator`:
  - `super().__init__(hass, logger, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)`; `zones` comes from `entry.options[CONF_ZONES]`.
  - `_async_update_data` empties a dict of statuses set during the poll, then calls `await self.amp.query_zones(self.zones)` and returns its result with that dict laid over it (`statuses | set_during_poll`). An `AmpError` becomes `UpdateFailed(translation_domain=DOMAIN, translation_key=...)`. HA copies that key onto the `ConfigEntryNotReady` it raises when the first poll fails.
  - `async_set_value` calls `amp.set_value`. An `AmpError` becomes `HomeAssistantError` with the same keys. On success it records the status in the set-during-poll dict and calls `self.async_set_updated_data({**self.data, zone: status})`.
  - One private method turns an `AmpError` into its key: `PortFailedError` is `port_failed`, and if the entry is `ConfigEntryState.LOADED` it also calls `hass.config_entries.async_schedule_reload(entry.entry_id)`; `AmpTimeoutError` is `no_answer`; any other `AmpError` is `closed`.
- `__init__.py`:
  - `async_setup_entry(hass, entry: AmpConfigEntry) -> bool`: `amp = await open_amp(entry.data[CONF_PORT])`. `PortInUseError` becomes `ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="port_in_use")`, and `PortNotFoundError` becomes `port_not_found`. Then `entry.async_on_unload(amp.close)`, the coordinator, `await coordinator.async_config_entry_first_refresh()`, `entry.runtime_data = coordinator`, and `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)`. `PLATFORMS` is empty in this task.
  - `async_unload_entry` returns `await hass.config_entries.async_unload_platforms(entry, PLATFORMS)`. The port closes through `async_on_unload`, after the platforms are gone.
- `strings.json` and `translations/en.json`: an `exceptions` section with the five keys and texts in the table above, each as `{"message": text}`.

- [x] **Step 6: Verify and push**

Run: `compileall` and `pytest` as in Step 3.
Expected: 58 passed.

```bash
git commit custom_components -m "Set up and unload the integration, and poll the zones"
git push origin main
```

- [x] **Step 7: Check both runs**

Expected: the tests-only run failed as Step 4 says. This run passes both workflows, with every test in `tests/ha/test_init.py` passing.

---

### Task 3: Zone devices and the media player

**Files:**
- Create: `custom_components/monoprice_8zone/entity.py`, `media_player.py`; `tests/ha/test_media_player.py`
- Modify: `custom_components/monoprice_8zone/__init__.py`, `strings.json`, `translations/en.json`; `tests/ha/test_init.py` (the two tests that need the poll timer)

**Interfaces:**
- Consumes: `AmpCoordinator`, `AmpConfigEntry`, `CONF_SOURCES`, `CONF_ZONES`, `DOMAIN` (Task 2).
- Produces:
  - `entity.py`: `def zone_device_identifier(entry_id: str, zone: int) -> str`, which returns `f"{entry_id}_zone_{zone}"`, and `class ZoneEntity(CoordinatorEntity[AmpCoordinator])` with:
    - `__init__(self, coordinator: AmpCoordinator, zone: int, key: str | None) -> None`;
    - attribute `zone`, and a `status -> ZoneStatus` property;
    - `available` that is also `False` while the zone's status is `None`;
    - `_attr_has_entity_name = True`;
    - unique ID: the zone device identifier, plus `_<key>` when `key` is given;
    - device info: identifiers `{(DOMAIN, zone_device_identifier(entry_id, zone))}`, name `Zone N`, manufacturer "Monoprice", model "44518", and `via_device_id=dr.async_get_device_id_by_identifier(coordinator.hass, (DOMAIN, entry_id), config_entry_id=entry_id)`. The amp device exists by then, because setup creates it before the platforms.
  - The amp device, created in `async_setup_entry` before the platforms: identifiers `{(DOMAIN, entry.entry_id)}`, name "Monoprice 44518", manufacturer "Monoprice", model "44518". Right after, every device of this entry that is neither the amp nor an enabled zone is removed with `device_registry.async_remove_device`, and HA removes its entities with it.
  - `media_player.py`: `PARALLEL_UPDATES = 1`, and `class ZoneMediaPlayer(ZoneEntity, MediaPlayerEntity)`. Entity IDs: `media_player.zone_1` to `media_player.zone_8`.
  - Exception key `unknown_source`, text: "{source} isn't one of the named sources."

The media player:
- `_attr_name = None`, so it takes the zone device's name. Device class `receiver`. Features: turn on, turn off, volume set, volume step, volume mute, select source.
- State `on` or `off` from `power`. `volume_level` is `volume / 38`. `is_volume_muted` comes from `mute`.
- `source_list`: the named sources, in order 1 to 6. `source`: the zone's source name, or `Source N` if that source has no name.
- `volume_set` sends `round(volume_level * 38)`. `volume_up` and `volume_down` send one amp step from the current `volume`, kept within 0 to 38. `volume_mute`, `turn_on`, `turn_off` and `select_source` send `MU`, `PR` and `CH`. A source name that isn't in the list raises `ServiceValidationError` with `unknown_source`.
- Each action is one `await self.coordinator.async_set_value(self.zone, field, value)`.

- [x] **Step 1: Write the failing tests** in `tests/ha/test_media_player.py`

```python
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
    with pytest.raises(ServiceValidationError):
        await call(hass, "select_source", source="Radio")
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
```

Add to `tests/ha/test_init.py`. The poll and the setup retry run as background tasks, so the tests wait for those too:

```python
NEXT_POLL = SCAN_INTERVAL + timedelta(seconds=1)


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
```

- [x] **Step 2: Commit and push the tests**

Run `compileall` and `pytest` first (Global Constraints).

```bash
git commit tests/ha -m "Add the media player tests (they fail until the next commit)"
git push origin main
```

Don't wait for the run. Expected, checked in Step 4: the new tests fail (no `media_player.zone_1`, no devices, and no poll timer without an entity); the Task 2 tests still pass.

- [x] **Step 3: Implement** `entity.py`, `media_player.py`, the amp device and the removal of disabled zones' devices in `__init__.py`, `Platform.MEDIA_PLAYER` in `PLATFORMS`, and the `unknown_source` text in both strings files.

- [x] **Step 4: Verify and push, then check both runs**

```bash
git commit custom_components -m "Add a device for each zone, and its media player"
git push origin main
```

Expected: the tests-only run failed as Step 2 says; this run passes both workflows.

---

### Task 4: Do Not Disturb, bass, treble and balance

**Files:**
- Create: `custom_components/monoprice_8zone/switch.py`, `number.py`; `tests/ha/test_switch.py`, `tests/ha/test_number.py`
- Modify: `custom_components/monoprice_8zone/__init__.py` (`PLATFORMS`), `strings.json`, `translations/en.json`

**Interfaces:**
- Consumes: `ZoneEntity` (Task 3); `DO_NOT_DISTURB`, `BASS`, `TREBLE`, `BALANCE` from `amp.py`.
- Produces:
  - `switch.py`: `PARALLEL_UPDATES = 1`, and `class DoNotDisturbSwitch(ZoneEntity, SwitchEntity)` with key and translation key `do_not_disturb`. Entity IDs: `switch.zone_N_do_not_disturb`.
  - `number.py`: `PARALLEL_UPDATES = 1`; `@dataclass(frozen=True, kw_only=True) class ZoneNumberDescription(NumberEntityDescription)` with `field: str` (the amp field) and `offset: int` (amp value = HA value + offset); `NUMBERS`, the descriptions below; `class ZoneNumber(ZoneEntity, NumberEntity)`. Its value is the `ZoneStatus` attribute named by the description's key, minus the offset. Setting it sends `round(value) + offset`. Entity IDs: `number.zone_N_bass`, `number.zone_N_treble`, `number.zone_N_balance`.

| Key and translation key | Field | Offset | Range | Name |
|---|---|---|---|---|
| `bass` | `BS` | 7 | -7 to 7 | Bass |
| `treble` | `TR` | 7 | -7 to 7 | Treble |
| `balance` | `BL` | 10 | -10 to 10 | Balance |

All three: step 1, `NumberMode.SLIDER`, `entity_category=EntityCategory.CONFIG`. The switch's name is "Do Not Disturb". Names go in the `entity` section of both strings files.

- [x] **Step 1: Write the failing tests**

`tests/ha/test_switch.py`:

```python
DND = "switch.zone_1_do_not_disturb"


async def test_do_not_disturb(hass, amp, set_up):
    amp.zones[1]["DT"] = 1
    await set_up()
    assert hass.states.get(DND).state == "on"
    amp.writes.clear()
    await hass.services.async_call("switch", "turn_off", {"entity_id": DND}, blocking=True)
    assert amp.writes == [b"<11DT00\r", b"?11\r"]
    assert hass.states.get(DND).state == "off"
```

`tests/ha/test_number.py`:

```python
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
```

- [x] **Step 2: Commit and push the tests, without waiting for the run**

```bash
git commit tests/ha -m "Add the Do Not Disturb and slider tests (they fail until the next commit)"
git push origin main
```

Expected, checked in Step 4: the new tests fail (no such entities); the earlier ones pass.

- [x] **Step 3: Implement** `switch.py`, `number.py`, `Platform.NUMBER` and `Platform.SWITCH` in `PLATFORMS`, and the entity names.

- [x] **Step 4: Verify and push, then check both runs**

```bash
git commit custom_components -m "Add the Do Not Disturb switch and the bass, treble and balance sliders"
git push origin main
```

Expected: the tests-only run failed as Step 2 says; this run passes both workflows.

---

### Task 5: Setup screens: port, zones and sources

**Files:**
- Create: `custom_components/monoprice_8zone/config_flow.py`; `tests/ha/test_config_flow.py`
- Modify: `custom_components/monoprice_8zone/manifest.json` (`"config_flow": true`), `strings.json`, `translations/en.json`

**Interfaces:**
- Consumes: `open_amp`, `Amp.query_zone`, `Amp.close` and the errors from `amp.py`; `CONF_ZONES`, `CONF_SOURCES`, `ZONES`, `SOURCES`, `DOMAIN` (Task 2).
- Produces, in `config_flow.py`:
  - `async def check_port(port: str) -> str | None`: opens the port, asks zone 1 for its status, closes the port whatever happens, and returns an error key or `None`. `PortInUseError` is `port_in_use`, `PortNotFoundError` is `port_not_found`, `AmpTimeoutError` is `no_answer`, and anything else is `unknown`, logged with `logger.exception`.
  - `PORT_SCHEMA = probatio.Schema({probatio.Required(CONF_PORT): SerialPortSelector()})`.
  - `ZONES_AND_SOURCES_SCHEMA`: `probatio.Required(CONF_ZONES)` with a `SelectSelector` (`multiple=True`, `mode=SelectSelectorMode.LIST`, options `SelectOptionDict(value="1", label="Zone 1")` to 8), and `probatio.Optional(f"source_{n}"): str` for sources 1 to 6. No defaults: each screen fills the form with `add_suggested_values_to_schema`, so a name the owner clears stays cleared.
  - `def options_from_input(user_input: dict[str, Any]) -> dict[str, Any]`, which returns `{CONF_ZONES: sorted ints, CONF_SOURCES: {str(n): stripped name}}` and leaves out blank names.
  - `class Monoprice8ZoneConfigFlow(ConfigFlow, domain=DOMAIN)` with `VERSION = 1`:
    - `async_step_user`: the port form. A failed check shows the error on the form (`errors={"base": key}`). On success it keeps the port and goes to `zones`.
    - `async_step_zones`: starts with every zone checked and no source names. No zones checked shows `no_zones` on the zones field. Otherwise it creates the entry: title "Monoprice 44518", `data={CONF_PORT: port}`, `options=options_from_input(user_input)`.

UI text, in the `config` section of both strings files:

| Where | Text |
|---|---|
| `step.user.title` | Connect to the amp |
| `step.user.data.port` | Serial port |
| `step.user.data_description.port` | The USB-to-serial adapter connected to the amp. A /dev/serial/by-id/ path keeps working after a reboot. |
| `step.zones.title` | Zones and sources |
| `step.zones.description` | Choose the zones you use, and name the sources you play music from. A source without a name stays out of the source list. |
| `step.zones.data.zones` | Zones |
| `step.zones.data.source_1` to `source_6` | Source 1 to Source 6 |
| `error.port_in_use`, `error.port_not_found`, `error.no_answer` | The same texts as the exceptions |
| `error.unknown` | Something unexpected went wrong. The details are in the Home Assistant log. |
| `error.no_zones` | Choose at least one zone. |

HA supplies the "only one amp" abort text (`single_instance_allowed`) itself.

- [x] **Step 1: Write the failing tests** in `tests/ha/test_config_flow.py`

```python
def suggested(result) -> dict[str, Any]:
    """The values a form starts with."""
    return {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


async def start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_flow_creates_the_entry(hass, amp):
    result = await start(hass)
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "user")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert (result["type"], result["step_id"]) == (FlowResultType.FORM, "zones")
    assert suggested(result) == {CONF_ZONES: ["1", "2", "3", "4", "5", "6", "7", "8"]}
    with patch("custom_components.monoprice_8zone.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ZONES: ["5", "1", "2"], "source_2": "Sonos", "source_5": " TV ", "source_6": "  "},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Monoprice 44518"
    assert result["data"] == {CONF_PORT: "/dev/ttyUSB0"}
    assert result["options"] == {CONF_ZONES: [1, 2, 5], CONF_SOURCES: {"2": "Sonos", "5": "TV"}}
    assert amp.writes == [b"?11\r"]
    assert amp.connections[0].closed


@pytest.mark.parametrize(
    ("open_error", "silent_zones", "error"),
    [
        (OSError(errno.EBUSY, "locked"), set(), "port_in_use"),
        (FileNotFoundError(errno.ENOENT, "missing"), set(), "port_not_found"),
        (None, {1}, "no_answer"),
        (PermissionError(errno.EACCES, "denied"), set(), "unknown"),
    ],
)
async def test_user_flow_port_errors(hass, amp, open_error, silent_zones, error):
    amp.open_error = open_error
    amp.silent_zones = silent_zones
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert (result["step_id"], result["errors"]) == ("user", {"base": error})
    assert all(connection.closed for connection in amp.connections)


async def test_user_flow_recovers_after_no_answer(hass, amp):
    amp.silent_zones = {1}
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert result["errors"] == {"base": "no_answer"}
    amp.silent_zones = set()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    assert result["step_id"] == "zones"  # the simulated lock would refuse this if the first try left the port open


async def test_zones_step_needs_a_zone(hass, amp):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB0"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ZONES: []})
    assert (result["step_id"], result["errors"]) == ("zones", {CONF_ZONES: "no_zones"})


async def test_only_one_amp(hass, amp, entry):
    result = await start(hass)
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "single_instance_allowed")
```

- [x] **Step 2: Commit and push the tests, without waiting for the run**

```bash
git commit tests/ha -m "Add the setup screen tests (they fail until the next commit)"
git push origin main
```

Expected, checked in Step 4: the new tests fail (the integration has no config flow); the earlier ones pass.

- [x] **Step 3: Implement** `config_flow.py` as in Interfaces, `"config_flow": true` in the manifest between `codeowners` and `dependencies` (same commit as `config_flow.py`, or hassfest fails), and the `config` text in both strings files.

- [x] **Step 4: Verify and push, then check both runs**

```bash
git commit custom_components -m "Add the setup screens: port, zones and sources"
git push origin main
```

Expected: the tests-only run failed as Step 2 says; this run passes both workflows.

---

### Task 6: Reconfigure and options

**Files:**
- Modify: `custom_components/monoprice_8zone/config_flow.py`, `strings.json`, `translations/en.json`; `tests/ha/test_config_flow.py`

**Interfaces:**
- Consumes: `check_port`, `PORT_SCHEMA`, `ZONES_AND_SOURCES_SCHEMA`, `options_from_input` (Task 5).
- Produces:
  - `def same_device(port: str, other: str) -> bool`: true when both paths resolve to the same file (`os.path.realpath`). The flow runs it with `hass.async_add_executor_job`.
  - `Monoprice8ZoneConfigFlow.async_step_reconfigure`: the port form, filled with the current port. If the new port is the same device as the current one, the check is skipped (otherwise the integration's own lock would fail it). Otherwise `check_port`, with its errors on the form. Then `self.async_update_reload_and_abort(entry, data_updates={CONF_PORT: port})`.
  - `class Monoprice8ZoneOptionsFlow(OptionsFlowWithReload)` with `async_step_init`: the zones and sources form, filled with the current options; `no_zones` as in Task 5; `async_create_entry(data=options_from_input(user_input))`, after which HA reloads the entry. `Monoprice8ZoneConfigFlow.async_get_options_flow` returns it.
  - When either form is shown again with an error, it keeps what the owner entered.

UI text: `config.step.reconfigure.title` "Change the serial port", with the same `data` and `data_description` as the user step. `options.step.init` has the zones step's title, description and labels; `options.error.no_zones` as in Task 5. HA supplies the "reconfigure successful" text itself.

- [x] **Step 1: Write the failing tests** in `tests/ha/test_config_flow.py`

```python
@pytest.fixture
def linked_ports(tmp_path) -> tuple[str, str]:
    """A port and a second name for it, like /dev/ttyUSB0 and its /dev/serial/by-id/ link."""
    port = tmp_path / "ttyUSB0"
    port.touch()
    link = tmp_path / "usb-FTDI_FT232R_USB_UART-if00-port0"
    link.symlink_to(port)
    return str(port), str(link)


async def test_reconfigure_changes_the_port(hass, amp, entry, set_up):
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    assert suggested(result) == {CONF_PORT: "/dev/ttyUSB0"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB1"})
    await hass.async_block_till_done()
    assert (result["type"], result["reason"]) == (FlowResultType.ABORT, "reconfigure_successful")
    assert entry.data[CONF_PORT] == "/dev/ttyUSB1"
    assert entry.state is ConfigEntryState.LOADED
    # setup on the old port, the check on the new one, then the reload
    assert [(c.port, c.closed) for c in amp.connections] == [
        ("/dev/ttyUSB0", True), ("/dev/ttyUSB1", True), ("/dev/ttyUSB1", False),
    ]


async def test_reconfigure_same_device_skips_the_check(hass, amp, entry, set_up, linked_ports):
    port, link = linked_ports
    hass.config_entries.async_update_entry(entry, data={CONF_PORT: port})
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: link})
    await hass.async_block_till_done()
    # A check would have opened the same device again and hit the integration's own lock.
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == link
    assert len(amp.connections) == 2  # setup, then the reload


async def test_reconfigure_port_in_use(hass, amp, entry, set_up):
    await set_up()
    result = await entry.start_reconfigure_flow(hass)
    amp.open_error = OSError(errno.EBUSY, "locked")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PORT: "/dev/ttyUSB1"})
    assert (result["step_id"], result["errors"]) == ("reconfigure", {"base": "port_in_use"})
    assert entry.data[CONF_PORT] == "/dev/ttyUSB0"


async def test_options_change_zones_and_sources(hass, entry, set_up, entity_registry):
    await set_up()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert suggested(result) == {
        CONF_ZONES: ["1", "2", "3", "4", "5", "6", "7", "8"], "source_2": "Sonos", "source_5": "TV",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ZONES: ["1", "2"], "source_3": "Radio"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_ZONES: [1, 2], CONF_SOURCES: {"3": "Radio"}}
    assert entry.state is ConfigEntryState.LOADED
    assert entity_registry.async_get("media_player.zone_3") is None
    assert hass.states.get("media_player.zone_1").attributes["source_list"] == ["Radio"]


async def test_options_need_a_zone(hass, entry, set_up):
    await set_up()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ZONES: []})
    assert (result["step_id"], result["errors"]) == ("init", {CONF_ZONES: "no_zones"})
```

- [x] **Step 2: Commit and push the tests, without waiting for the run**

```bash
git commit tests/ha -m "Add the reconfigure and options tests (they fail until the next commit)"
git push origin main
```

Expected, checked in Step 4: the new tests fail (no reconfigure step, no options flow); the earlier ones pass.

- [x] **Step 3: Implement** the reconfigure step, the options flow and their text.

- [x] **Step 4: Verify and push, then check both runs**

```bash
git commit custom_components -m "Add reconfigure for the port, and options for zones and sources"
git push origin main
```

Expected: the tests-only run failed as Step 2 says; this run passes both workflows.

---

### Task 7: The send_command action

**Files:**
- Create: `custom_components/monoprice_8zone/services.py`, `services.yaml`; `tests/ha/test_send_command.py`
- Modify: `custom_components/monoprice_8zone/__init__.py`, `coordinator.py`, `strings.json`, `translations/en.json`

**Interfaces:**
- Consumes: `Amp.send_raw` (Phase 1); `AmpCoordinator` (Task 2).
- Produces:
  - `AmpCoordinator.async_send_raw(self, command: str) -> str`: a `ValueError` from `send_raw` becomes `ServiceValidationError(translation_domain=DOMAIN, translation_key="bad_command")`; an `AmpError` is handled as in `async_set_value`. It returns the reply decoded as ASCII with `errors="backslashreplace"`, with CR and LF written out as `\r` and `\n`.
  - `services.py`: `def async_setup_services(hass: HomeAssistant) -> None` registers `send_command` with the schema `probatio.Schema({probatio.Required("command"): cv.string})` and `supports_response=SupportsResponse.ONLY`. The handler takes the loaded entry from `hass.config_entries.async_loaded_entries(DOMAIN)`; with none it raises `ServiceValidationError` with `not_loaded`. It returns `{"reply": ...}`.
  - `__init__.py`: `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`, and `async_setup(hass, config) -> bool` calls `async_setup_services(hass)`. The action exists whether or not the entry is loaded.
  - `services.yaml`: `send_command` with one field, `command`: required, example `?11`, a text selector.

UI text: `services.send_command.name` "Send command"; `description` "Sends a raw command to the amp and returns the amp's raw reply. For testing the amp from Developer Tools."; `fields.command.name` "Command"; `fields.command.description` "The command without the carriage return, for example ?11 or <11MU01. Only commands that start with ? or < are sent." Exceptions: `not_loaded` "The integration isn't set up yet, or it's waiting for the amp."; `bad_command` "Send one command that starts with ? or <, for example ?11."

- [x] **Step 1: Write the failing tests** in `tests/ha/test_send_command.py`

```python
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
```

- [x] **Step 2: Commit and push the tests, without waiting for the run**

```bash
git commit tests/ha -m "Add the send_command tests (they fail until the next commit)"
git push origin main
```

Expected, checked in Step 4: the new tests fail with `ServiceNotFound`; the earlier ones pass.

- [x] **Step 3: Implement** `services.py`, `services.yaml`, `async_setup` and `CONFIG_SCHEMA`, `async_send_raw`, and the text.

- [x] **Step 4: Verify and push, then check both runs**

```bash
git commit custom_components -m "Add the send_command action"
git push origin main
```

Expected: the tests-only run failed as Step 2 says; this run passes both workflows.

---

### Task 8: Docs

**Files:**
- Modify: `README.md`, `docs/design.md`, `CLAUDE.md`

- [x] **Step 1: Update the docs**

- `README.md`, in the first-person voice it already has:
  - "Status": the integration is written and its tests pass in GitHub Actions; it hasn't run on my amp yet, and the hardware checks come next.
  - "What it will do" becomes "What it does", and gains the bass, treble and balance sliders and the `send_command` action.
  - "Install (once there's code)" becomes "Install".
  - A short "Development" section: the amp tests run on Windows with plain pytest (create a venv, `pip install -r requirements_test.txt`, `python -m pytest`); the HA tests run only in GitHub Actions.
- `docs/design.md`: the user-visible decisions from this plan, marked **(Claude's call)** where they belong (at least one zone; the error for a source name that isn't in the list; the "reloading" error; the entry title), and anything the build changed.
- `CLAUDE.md`, Tests section: the two CI jobs and what each runs, and the local command.

- [x] **Step 2: Verify and push**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 58 passed.

```bash
git commit README.md docs/design.md CLAUDE.md -m "Update the docs for the Home Assistant side"
git push origin main
```

Expected: both workflows pass.

---

### Task 9: Phase 2 review

- [x] **Step 1: Dispatch the reviewer**

A fresh reviewer on the most capable model gets the design doc, PROTOCOL.md, this plan with its Review Focus, the ledger's rulings, and the Phase 2 changes (from the commit that adds this plan to `HEAD`). It reports correctness bugs and mismatches with the spec, each with a file and line and a concrete failure. It gets the code, not Claude's opinion of it.

- [x] **Step 2: Fix confirmed findings**

Each fix starts with a failing test (for HA code: pushed and seen failing in CI). A finding that isn't in this plan and doesn't break a spec guarantee goes in the Later list, not into a fix round.

- [x] **Step 3: Re-review, within the fix-loop limits**

Up to two rounds of re-review on the same findings, then one round with a fresh reviewer, then park what's left with a ruling. Four rounds at most.

- [x] **Step 4: Verify**

Run: `.venv/Scripts/python -m pytest -v`, push, then watch both workflows with `gh run watch <run-id> --exit-status`.
Expected: all tests pass locally, and both workflows succeed.

- [x] **Step 5: Close out the plan**

Tick the checkboxes, add "What changed during the build", update the Later list, and commit the plan.

---

## What changed during the build

- **Task 2.** HA 2026.10 imports an integration's config flow module, and needs its flow class, to set up any config entry. So a minimal `config_flow.py` (the class with `VERSION = 1`) came in Task 2. The screens and the manifest's `config_flow` flag stayed in Task 5.
- **Task 3.** The first media player dropped a zone that was silent at startup, because HA reads `entity_picture`, and through it `state`, even while an entity is unavailable. `state` now returns `None` when the zone has no status.
- **Task 3.** `test_select_unknown_source_is_rejected` passed before the media player existed, because HA's "action not found" error is also a `ServiceValidationError`. It now checks the error's key, and that version was pushed as a second tests-only commit so its failure shows in CI.
- **Task 4.** Two extra tests check that a silent zone's switch and sliders show as unavailable.
- **Task 5.** `test_only_one_amp` passed before the setup screens existed, because Task 2 had already added `single_config_entry`. Ruled, not broken on purpose: without the flag, HA would show the port form instead of aborting.
- **Final review.** The "port in use" text now says to restart Home Assistant after deleting the built-in integration, which lets go of the port only on a restart.
- **Final review.** One commit broke the five behaviors the Review Focus tests guard (bcd7d57, reverted in 220f2cf). Each named test failed on its own break.

## Later

Things that came up but are outside this phase:

- Poll with `?10`, if the `?10` hardware check passes (design.md, Later).
- From the final review, all minor. The code works today; these would catch a regression or polish an edge:
  - No test protects the reset of the set-during-poll statuses at the start of each poll. The `?10` change will rewrite that function, so this test should come first.
  - After an unplug of more than about 11 minutes, HA's retry backoff can take up to 10 minutes to reconnect once the adapter is back (Reload connects at once). Worth a line in the docs. A fuller fix: reload a retrying entry when the `usb` integration reports a new serial port.
  - Each successful set restarts the 30-second poll timer, so changes more often than every 30 seconds delay polls until they stop.
  - No test checks that HA sends no commands to a zone it has marked unavailable.
  - `ZoneEntity.status` is typed `ZoneStatus` but can be `None`.

## Remaining phases

### Phase 3: Hardware checks and release

Install from `main`, run the four hardware checks with the owner, record the results in PROTOCOL.md, adjust the code, then tag `v0.1.0`.
