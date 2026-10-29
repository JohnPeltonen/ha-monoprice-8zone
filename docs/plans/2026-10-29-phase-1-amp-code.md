# Phase 1: Amp Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner chose native execution: Claude builds every task in this session, and a very capable reviewer checks the plan before building and the code at the end. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the code that talks to the Monoprice 44518 (status queries, set commands, raw commands, opening and closing the port), with tests that run on Windows and in GitHub Actions.

**Architecture:** One module, `custom_components/monoprice_8zone/amp.py`, holds everything that talks to the amp. It imports nothing from `homeassistant` or from the rest of the integration. A small `asyncio.Protocol` collects incoming bytes in a buffer. An `Amp` class sends one command at a time behind an `asyncio.Lock` and reads the buffer until the reply is complete. Tests drive `Amp` through a fake transport that replays scripted replies.

**Tech Stack:** Python 3.14, `serialx` 1.11.0, `pytest`, `pytest-asyncio`, GitHub Actions, hassfest.

**Spec:** [docs/design.md](../design.md). Protocol facts: [PROTOCOL.md](../../PROTOCOL.md).

**Budget:** 1 session / tokens not tracked (the owner waived the token stop on 2026-10-29).

## Global Constraints

- Python 3.14. The manifest requires `serialx>=1.11.0`, because hassfest rejects an exact pin on a package HA itself uses. HA 2026.10's `usb` integration, a dependency, pins 1.11.0. `requirements_test.txt` pins `serialx==1.11.0`. No `pymonoprice`.
- Pushing to `main` is approved for this repo (CLAUDE.md, Working agreements).
- `amp.py` imports only the standard library and `serialx`: nothing from `homeassistant`, nothing from the rest of the integration.
- Serial settings: 9600 baud, 8 data bits, no parity, 1 stop bit, no flow control. Commands end with a carriage return (`\r`).
- Zones are numbered 1 to 8 in `amp.py`'s interface. On the wire they are 11 to 18. Nothing ever sends to zone 21 or higher.
- A status reply is a line matching `>(\d{2})(\d{20})` followed by `#`. An echo before it is skipped. The names after the digits are ignored.
- Timeouts: 1 second for a status reply; 0.5 seconds for the `#` after a set command; a raw command stops after 0.3 seconds of quiet or 2 seconds in total.
- Every command waits behind one `asyncio.Lock`.
- Every raw write and read is logged at debug level.
- Code style: snake_case, PascalCase classes, UPPER_CASE constants, absolute imports only, `logger = logging.getLogger(__name__)` with %-style formatting, `T | None`, minimal docstrings.
- Docs: no em dashes.

## Review Focus

1. **A reply arrives in small pieces.** Serial ports deliver a few bytes at a time. The reply should parse as if it came in one piece. Test: `test_query_zone_reply_in_pieces` (Task 3).
2. **The USB adapter is unplugged in the middle of a command.** This should fail as a port failure right away, not as a 1-second timeout that looks like a silent amp. Test: `test_port_failure_during_a_read` (Task 6).
3. **A slider and a poll send commands at the same moment.** The second command should wait until the first reply has been read. Test: `test_commands_wait_their_turn` (Task 3).
4. **The amp says nothing after a set command.** The zone should still be queried, after at most 0.5 seconds. Test: `test_set_value_without_hash_still_queries` (Task 4).
5. **A raw command with a line break inside it**, for example `?11\r19200` typed as a double-quoted string in Developer Tools. The amp would read `19200` as a second command and change its baud rate. It should be rejected before anything is sent. Test: `test_send_raw_rejects_other_commands` (Task 5).

## File Structure

| File | What it holds |
|---|---|
| `custom_components/monoprice_8zone/manifest.json` | Integration manifest. No config flow yet; Phase 2 adds it. |
| `custom_components/monoprice_8zone/__init__.py` | A docstring only, for now. |
| `custom_components/monoprice_8zone/amp.py` | Everything that talks to the amp. |
| `pyproject.toml` | pytest settings only. |
| `requirements_test.txt` | Packages for the amp tests, on Windows and in CI. |
| `tests/amp/conftest.py` | Puts the integration folder on `sys.path`, and the `make_amp` fixture. |
| `tests/amp/fake_amp.py` | The captured replies shared by the tests (Task 1), and `FakeTransport`, which replays scripted replies (Task 3). |
| `tests/amp/test_replies.py` | Command builders and the reply parser. |
| `tests/amp/test_queries.py` | Status queries and polling. |
| `tests/amp/test_commands.py` | Set commands and raw commands. |
| `tests/amp/test_connection.py` | Opening, closing and port failures. |
| `.github/workflows/tests.yaml`, `.github/workflows/hassfest.yaml` | CI. |

Local test command, from the repo root on Windows: `.venv/Scripts/python -m pytest tests/amp -v`

Captured replies used across the tests, kept in `tests/amp/fake_amp.py` (the first is the capture in PROTOCOL.md; the others change its values):

```python
ZONE_1 = b">1100010000100707100200 Zone1    Source02\r\n#"
ZONE_1_VOLUME_20 = b">1100010000200707100200 Zone1    Source02\r\n#"
ZONE_2 = b">1200010000150707100100 Zone2    Source01\r\n#"
ZONE_5 = b">1500010000050707100100 Zone5    Source01\r\n#"
```

---

### Task 1: Skeleton, test setup, command builders and the reply parser

**Files:**
- Create: `custom_components/monoprice_8zone/manifest.json`, `custom_components/monoprice_8zone/__init__.py`, `custom_components/monoprice_8zone/amp.py`, `pyproject.toml`, `requirements_test.txt`, `tests/amp/conftest.py`, `tests/amp/fake_amp.py` (the four reply constants only)
- Test: `tests/amp/test_replies.py`

**Interfaces:**
- Produces, in `amp.py`:
  - Field codes: `POWER = "PR"`, `MUTE = "MU"`, `DO_NOT_DISTURB = "DT"`, `VOLUME = "VO"`, `TREBLE = "TR"`, `BASS = "BS"`, `BALANCE = "BL"`, `SOURCE = "CH"`.
  - `FIELD_RANGES: dict[str, tuple[int, int]]`: power, mute and Do Not Disturb 0 to 1; volume 0 to 38; treble and bass 0 to 14; balance 0 to 20; source 1 to 6.
  - `@dataclass(frozen=True) class ZoneStatus` with fields `zone: int` (1 to 8), `page: bool`, `power: bool`, `mute: bool`, `do_not_disturb: bool`, `volume: int`, `treble: int`, `bass: int`, `balance: int`, `source: int`, `keypad: bool`.
  - `status_command(zone: int) -> bytes`
  - `set_command(zone: int, field: str, value: int) -> bytes`
  - `find_status(data: bytes) -> ZoneStatus | None`

- [x] **Step 1: Create the skeleton**

`manifest.json`, with keys in hassfest's required order (domain, name, then alphabetical):

```json
{
  "domain": "monoprice_8zone",
  "name": "Monoprice 8-Zone Amplifier (44518)",
  "codeowners": ["@JohnPeltonen"],
  "dependencies": ["usb"],
  "documentation": "https://github.com/JohnPeltonen/ha-monoprice-8zone",
  "integration_type": "hub",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/JohnPeltonen/ha-monoprice-8zone",
  "requirements": ["serialx>=1.11.0"],
  "version": "0.1.0"
}
```

- `__init__.py`: the docstring `"""Monoprice 8-Zone Amplifier (44518) integration."""` and nothing else.
- `amp.py`: a module docstring saying it talks to the amp and must not import `homeassistant`.
- `pyproject.toml`: `[tool.pytest.ini_options]` with `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"` and `testpaths = ["tests"]`.
- `requirements_test.txt`: `pytest`, `pytest-asyncio`, `serialx==1.11.0`, one per line.
- `tests/amp/conftest.py`: inserts `<repo>/custom_components/monoprice_8zone` at the front of `sys.path`, with a one-line comment saying why (the package's `__init__.py` imports `homeassistant` from Phase 2 on, so the tests load `amp.py` on its own).

- [x] **Step 2: Create the virtual environment**

Run: `py -3.14 -m venv .venv` then `.venv/Scripts/python -m pip install -r requirements_test.txt`
Expected: pytest, pytest-asyncio and serialx 1.11.0 install without errors.

- [x] **Step 3: Write the failing tests** in `tests/amp/test_replies.py`

```python
CAPTURED_STATUS = ZoneStatus(
    zone=1, page=False, power=True, mute=False, do_not_disturb=False,
    volume=10, treble=7, bass=7, balance=10, source=2, keypad=False,
)

def test_status_command():
    assert status_command(1) == b"?11\r"
    assert status_command(8) == b"?18\r"

@pytest.mark.parametrize("zone", [0, 9])
def test_status_command_rejects_other_zones(zone):
    with pytest.raises(ValueError):
        status_command(zone)

def test_set_command():
    assert set_command(1, VOLUME, 10) == b"<11VO10\r"
    assert set_command(5, DO_NOT_DISTURB, 1) == b"<15DT01\r"
    assert set_command(2, SOURCE, 6) == b"<12CH06\r"

@pytest.mark.parametrize(
    ("zone", "field", "value"),
    [(1, VOLUME, 39), (1, VOLUME, -1), (1, SOURCE, 0), (1, BALANCE, 21), (1, "XX", 1), (9, VOLUME, 10)],
)
def test_set_command_rejects_bad_input(zone, field, value):
    with pytest.raises(ValueError):
        set_command(zone, field, value)

def test_find_status_parses_captured_reply():
    assert find_status(ZONE_1) == CAPTURED_STATUS

def test_find_status_skips_an_echo():
    assert find_status(b"?11\r\r\n#" + ZONE_1) == CAPTURED_STATUS

def test_find_status_needs_the_closing_hash():
    assert find_status(ZONE_1[:-1]) is None

def test_find_status_ignores_slave_zones():
    assert find_status(b">2100010000100707100200\r\n#") is None

def test_find_status_ignores_odd_bytes_in_names():
    assert find_status(b">1100010000100707100200 K\xfcche\x00  Source02\r\n#") == CAPTURED_STATUS
```

- [x] **Step 4: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/amp/test_replies.py -v`
Expected: FAIL with `ImportError` (the names don't exist yet).

- [x] **Step 5: Implement the field codes, `ZoneStatus`, `status_command`, `set_command` and `find_status` in `amp.py`**

- `find_status` searches `data` with `rb">1([1-8])(\d{20})[^#]*#"`. The captured digit is the zone. The 20 digits split into ten two-digit fields in PROTOCOL.md's order: PA, PR, MU, DT, VO, TR, BS, BL, CH, LS. Zones 21 and up never match.
- The builders raise `ValueError` for a zone outside 1 to 8, an unknown field, or a value outside `FIELD_RANGES`.

- [x] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/amp -v`
Expected: all PASS.

- [x] **Step 7: Commit and push**

```bash
git add custom_components pyproject.toml requirements_test.txt tests
git commit custom_components pyproject.toml requirements_test.txt tests -m "Add amp command builders and reply parser"
git push origin main
```

---

### Task 2: GitHub workflows

**Files:**
- Create: `.github/workflows/tests.yaml`, `.github/workflows/hassfest.yaml`

**Interfaces:**
- Consumes: `requirements_test.txt`, `pyproject.toml` and `manifest.json` from Task 1.

- [x] **Step 1: Write `tests.yaml`**

```yaml
name: Tests

on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.14"
      - run: pip install -r requirements_test.txt
      - run: pytest -v
```

- [x] **Step 2: Write `hassfest.yaml`**

```yaml
name: Hassfest

on:
  push:
  pull_request:

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: home-assistant/actions/hassfest@master
```

- [x] **Step 3: Commit and push**

```bash
git add .github
git commit .github -m "Add test and hassfest workflows"
git push origin main
```

- [x] **Step 4: Watch both runs**

Run: `gh run list --limit 2`, then `gh run watch <run-id> --exit-status` for each run.
Expected: both succeed. On a failure, read `gh run view <run-id> --log-failed`, fix it, and push again. If the same failure survives three pushes, stop and report to the owner.

---

### Task 3: Status queries and polling

**Files:**
- Modify: `custom_components/monoprice_8zone/amp.py`, `tests/amp/conftest.py`, `tests/amp/fake_amp.py`
- Test: `tests/amp/test_queries.py`

**Interfaces:**
- Consumes: `find_status`, `status_command`, `ZoneStatus` (Task 1).
- Produces, in `amp.py`:
  - `STATUS_TIMEOUT = 1.0`. All timeout constants are read when a command runs, not bound as default arguments, so tests can shorten them with `monkeypatch`.
  - `class AmpError(Exception)`, and its subclasses `AmpTimeoutError`, `BadReplyError` and `PortFailedError`.
  - `class AmpProtocol(asyncio.Protocol)` with `buffer: bytearray`, `lost: bool` and `closed: asyncio.Future[None]`. `data_received` logs at debug, appends to `buffer` and wakes any waiting reader. `connection_lost` sets `lost`, resolves `closed` if it isn't already done, and wakes any waiting reader.
  - `class Amp` with `__init__(self, transport: asyncio.Transport, protocol: AmpProtocol) -> None`, `async def query_zone(self, zone: int) -> ZoneStatus` and `async def query_zones(self, zones: Iterable[int]) -> dict[int, ZoneStatus | None]`.
- Produces, in the tests:
  - `fake_amp.FakeTransport(protocol: asyncio.Protocol, replies: list[bytes | list[bytes] | None])`. Each `write()` appends the bytes to `writes` and to `log` as `("write", data)`, then delivers the next scripted reply with `loop.call_soon`: `bytes` as one piece, a `list[bytes]` one piece per event-loop pass (the callback that delivers a piece schedules the next one with `call_soon`, so the reader wakes between pieces), or `None` for silence. When the script runs out, it stays silent. Each delivered piece is appended to `log` as `("read", piece)`. `close()` sets `closed = True` and calls `protocol.connection_lost(None)` soon. It keeps the protocol as `protocol`.
  - Fixture `make_amp(*replies) -> tuple[Amp, FakeTransport]` in `conftest.py`.

- [x] **Step 1: Write `fake_amp.py` and the `make_amp` fixture**

- [x] **Step 2: Write the failing tests** in `tests/amp/test_queries.py`

```python
async def test_query_zone_returns_status(make_amp):
    amp, transport = make_amp(ZONE_1)
    status = await amp.query_zone(1)
    assert (status.zone, status.volume, status.source) == (1, 10, 2)
    assert transport.writes == [b"?11\r"]

async def test_query_zone_skips_an_echo(make_amp):
    amp, _ = make_amp(b"?11\r\r\n#" + ZONE_1)
    assert (await amp.query_zone(1)).volume == 10

async def test_query_zone_reply_in_pieces(make_amp):
    amp, _ = make_amp([b">1100", b"0100001007071002", b"00 Zone1    Sou", b"rce02\r\n", b"#"])
    assert (await amp.query_zone(1)).volume == 10

async def test_query_zone_times_out(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(None)
    with pytest.raises(AmpTimeoutError):
        await amp.query_zone(1)

async def test_query_zone_discards_stray_bytes(make_amp):
    amp, transport = make_amp(ZONE_1)
    transport.protocol.data_received(ZONE_5)  # a late reply to an earlier command
    assert (await amp.query_zone(1)).zone == 1

async def test_query_zone_wrong_zone_is_an_error(make_amp):
    amp, _ = make_amp(ZONE_5)
    with pytest.raises(BadReplyError):
        await amp.query_zone(1)

async def test_commands_wait_their_turn(make_amp):
    amp, transport = make_amp(ZONE_1, ZONE_2)
    await asyncio.gather(amp.query_zone(1), amp.query_zone(2))
    assert transport.log == [("write", b"?11\r"), ("read", ZONE_1), ("write", b"?12\r"), ("read", ZONE_2)]

async def test_query_zones_marks_silent_zones(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(ZONE_1, None)
    result = await amp.query_zones([1, 2])
    assert result[1].zone == 1
    assert result[2] is None

async def test_query_zones_fails_when_no_zone_answers(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "STATUS_TIMEOUT", 0.05)
    amp, _ = make_amp(None, None)
    with pytest.raises(AmpTimeoutError):
        await amp.query_zones([1, 2])
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/amp/test_queries.py -v`
Expected: FAIL with `ImportError`.

- [x] **Step 4: Implement `AmpProtocol`, the exceptions, `Amp.query_zone` and `Amp.query_zones`**

- Sending: inside the lock, raise `PortFailedError` if `protocol.lost`; clear `protocol.buffer` (stray bytes); log the bytes at debug; write.
- Reading: loop until a condition on `protocol.buffer` is true. Before each wait, raise `PortFailedError` if `protocol.lost`, and raise `AmpTimeoutError` if the deadline has passed. Clear the wake-up event and wait on it for the time left. Don't `await` between checking the condition and clearing the event.
- `query_zone` takes the lock and calls a private `_query_locked(zone)`, so `set_value` (Task 4) can query without taking the lock twice. `_query_locked` reads until `find_status(buffer)` returns a status. A status for another zone raises `BadReplyError`.
- `query_zones` calls `query_zone` for each zone, so other commands can run between zones. `AmpTimeoutError` and `BadReplyError` give `None` for that zone, logged at debug. If every zone asked about is `None`, it raises `AmpTimeoutError`. `PortFailedError` passes through.

- [x] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/amp -v`
Expected: all PASS.

- [x] **Step 6: Commit and push**

```bash
git add custom_components tests
git commit custom_components tests -m "Add status queries and polling to the amp code"
git push origin main
```

---

### Task 4: Set commands

**Files:**
- Modify: `custom_components/monoprice_8zone/amp.py`
- Test: `tests/amp/test_commands.py`

**Interfaces:**
- Consumes: `set_command`, field codes (Task 1); `Amp._query_locked`, the send and read helpers, `make_amp` (Task 3).
- Produces: `SET_REPLY_TIMEOUT = 0.5`; `async def Amp.set_value(self, zone: int, field: str, value: int) -> ZoneStatus`.

- [x] **Step 1: Write the failing tests** in `tests/amp/test_commands.py`

```python
async def test_set_value_waits_for_hash_then_queries(make_amp):
    amp, transport = make_amp(b"#", ZONE_1_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.log == [
        ("write", b"<11VO20\r"), ("read", b"#"), ("write", b"?11\r"), ("read", ZONE_1_VOLUME_20),
    ]

async def test_set_value_without_hash_still_queries(make_amp, monkeypatch, caplog):
    monkeypatch.setattr(amp_module, "SET_REPLY_TIMEOUT", 0.05)
    caplog.set_level(logging.DEBUG)
    amp, transport = make_amp(None, ZONE_1_VOLUME_20)
    status = await amp.set_value(1, VOLUME, 20)
    assert status.volume == 20
    assert transport.writes == [b"<11VO20\r", b"?11\r"]
    assert "No # after" in caplog.text

async def test_set_value_rejects_bad_values(make_amp):
    amp, transport = make_amp()
    with pytest.raises(ValueError):
        await amp.set_value(1, VOLUME, 39)
    assert transport.writes == []
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/amp/test_commands.py -v`
Expected: FAIL with `AttributeError` (no `set_value`).

- [x] **Step 3: Implement `Amp.set_value`**

Build the command before taking the lock, so bad input raises `ValueError` without touching the port. Inside the lock: send, then read until `#` is in the buffer. On `AmpTimeoutError`, log `"No # after %r"` at debug and carry on. Then return `_query_locked(zone)`.

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/amp -v`
Expected: all PASS.

- [x] **Step 5: Commit and push**

```bash
git add custom_components tests
git commit custom_components tests -m "Add set commands to the amp code"
git push origin main
```

---

### Task 5: Raw commands

**Files:**
- Modify: `custom_components/monoprice_8zone/amp.py`
- Test: `tests/amp/test_commands.py`

**Interfaces:**
- Consumes: the send helper, `PortFailedError`, `make_amp` (Task 3).
- Produces: `RAW_QUIET_GAP = 0.3`, `RAW_TIMEOUT = 2.0`; `async def Amp.send_raw(self, command: str) -> bytes`.

- [x] **Step 1: Write the failing tests** in `tests/amp/test_commands.py`

```python
async def test_send_raw_returns_everything_until_quiet(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_QUIET_GAP", 0.05)
    amp, transport = make_amp([ZONE_1[:-1], b"#"])
    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await amp.send_raw("?11") == ZONE_1
    assert loop.time() - started < 1.0  # stopped at the quiet gap, not the 2-second limit
    assert transport.writes == [b"?11\r"]

async def test_send_raw_returns_nothing_when_the_amp_is_silent(make_amp, monkeypatch):
    monkeypatch.setattr(amp_module, "RAW_TIMEOUT", 0.1)
    amp, _ = make_amp(None)
    assert await amp.send_raw("<11MU01") == b""

@pytest.mark.parametrize("command", ["19200", "", "?11é", "?11\r19200", "?11\n"])
async def test_send_raw_rejects_other_commands(make_amp, command):
    amp, transport = make_amp()
    with pytest.raises(ValueError):
        await amp.send_raw(command)
    assert transport.writes == []

async def test_send_raw_port_failure(make_amp):
    amp, transport = make_amp(None)
    asyncio.get_running_loop().call_later(
        0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected")
    )
    with pytest.raises(PortFailedError):
        await amp.send_raw("?11")
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/amp/test_commands.py -v`
Expected: the new tests FAIL with `AttributeError`.

- [x] **Step 3: Implement `Amp.send_raw`**

- Accept only commands whose first character is `?` or `<`, that are printable (`str.isprintable()`, so no CR, LF or other control characters), and that encode as ASCII. Anything else raises `ValueError` before the lock. (`UnicodeEncodeError` is a `ValueError`.)
- Inside the lock, send `command` plus `\r`. Then wait for new bytes. Before the first byte, the wait is limited only by the `RAW_TIMEOUT` deadline. After a byte has arrived, each wait is also limited to `RAW_QUIET_GAP`. Before each wait, raise `PortFailedError` if `protocol.lost`. Stop at the first wait that times out, and return everything in the buffer. Silence returns `b""`; it is not an error.

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/amp -v`
Expected: all PASS.

- [x] **Step 5: Commit and push**

```bash
git commit custom_components tests -m "Add raw commands to the amp code"
git push origin main
```

---

### Task 6: Opening, closing and port failures

**Files:**
- Modify: `custom_components/monoprice_8zone/amp.py`, `tests/amp/fake_amp.py`
- Test: `tests/amp/test_connection.py`

**Interfaces:**
- Consumes: `Amp`, `AmpProtocol`, `PortFailedError` (Task 3); `fake_amp.FakeTransport`.
- Produces: `BAUD_RATE = 9600`; `class PortInUseError(AmpError)`, `class PortNotFoundError(AmpError)`; `async def open_amp(port: str) -> Amp`; `async def Amp.close(self) -> None`. In the tests: `FakeTransport.write_error: OSError | None` (default `None`), raised by `write()` when set.

- [x] **Step 1: Write the failing tests** in `tests/amp/test_connection.py`

```python
def fake_opener(calls, replies):
    async def create_serial_connection(loop, protocol_factory, url, baudrate, **kwargs):
        calls.append((url, baudrate))
        protocol = protocol_factory()
        transport = FakeTransport(protocol, replies)
        protocol.connection_made(transport)
        return transport, protocol
    return create_serial_connection

async def test_open_amp_opens_the_port_at_9600(monkeypatch):
    calls = []
    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", fake_opener(calls, [ZONE_1]))
    amp = await open_amp("/dev/ttyUSB0")
    assert calls == [("/dev/ttyUSB0", 9600)]
    assert (await amp.query_zone(1)).zone == 1

@pytest.mark.parametrize(
    ("error_number", "error_type"),
    [(errno.EBUSY, PortInUseError), (errno.ENOENT, PortNotFoundError), (errno.ENODEV, PortNotFoundError), (errno.ENXIO, PortNotFoundError)],
)
async def test_open_amp_port_errors(monkeypatch, error_number, error_type):
    async def create_serial_connection(*args, **kwargs):
        raise OSError(error_number, "test")
    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", create_serial_connection)
    with pytest.raises(error_type):
        await open_amp("/dev/ttyUSB0")

async def test_open_amp_other_errors_pass_through(monkeypatch):
    async def create_serial_connection(*args, **kwargs):
        raise OSError(errno.EACCES, "test")
    monkeypatch.setattr(amp_module.serialx, "create_serial_connection", create_serial_connection)
    with pytest.raises(PermissionError):
        await open_amp("/dev/ttyUSB0")

async def test_close_closes_the_port(make_amp):
    amp, transport = make_amp()
    await amp.close()
    assert transport.closed
    assert transport.protocol.closed.done()

async def test_command_after_port_failure(make_amp):
    amp, transport = make_amp(ZONE_1)
    transport.protocol.connection_lost(OSError(errno.EIO, "device disconnected"))
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)
    assert transport.writes == []

async def test_port_failure_during_a_read(make_amp):
    amp, transport = make_amp(None)
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, transport.protocol.connection_lost, OSError(errno.EIO, "device disconnected"))
    started = loop.time()
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)
    assert loop.time() - started < 0.5  # well before the 1-second status timeout

async def test_write_failure_is_a_port_failure(make_amp):
    amp, transport = make_amp(ZONE_1)
    transport.write_error = OSError(errno.EIO, "device disconnected or in use by another process")
    with pytest.raises(PortFailedError):
        await amp.query_zone(1)

async def test_command_after_close_is_not_a_port_failure(make_amp):
    amp, _ = make_amp(ZONE_1)
    await amp.close()
    with pytest.raises(AmpError) as caught:
        await amp.query_zone(1)
    assert not isinstance(caught.value, PortFailedError)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/amp/test_connection.py -v`
Expected: FAIL with `ImportError`.

- [x] **Step 3: Implement `open_amp` and `Amp.close`**

- `open_amp` calls `serialx.create_serial_connection(asyncio.get_running_loop(), AmpProtocol, port, baudrate=BAUD_RATE)`. Its defaults are already no parity, 1 stop bit, no flow control and exclusive access. It turns `OSError` with `errno.EBUSY` into `PortInUseError`, and `errno.ENOENT`, `errno.ENODEV` or `errno.ENXIO` into `PortNotFoundError` (both `from exc`). Any other `OSError` passes through unchanged.
- `close` takes the lock, so it never closes in the middle of a command. It sets `self._closed`, calls `transport.close()` and waits for `protocol.closed`.
- The send helper checks `self._closed` first and raises a plain `AmpError("The connection is closed")`. A command that arrives after unload, such as the rest of a poll, then isn't mistaken for a port failure. `PortFailedError` stays reserved for real failures, because Phase 2 reloads the integration when it sees one.
- The send helper also turns an `OSError` from `transport.write()` into `PortFailedError(...) from exc`. serialx's `write()` raises when the port has just failed, before `connection_lost` arrives.

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/amp -v`
Expected: all PASS.

- [x] **Step 5: Commit and push**

```bash
git add custom_components tests
git commit custom_components tests -m "Add opening, closing and port errors to the amp code"
git push origin main
```

---

### Task 7: Phase 1 review

- [x] **Step 1: Dispatch the reviewer**

A fresh reviewer agent on the most capable model gets the design doc, PROTOCOL.md, this plan, and the Phase 1 changes (`git diff 960f65c..HEAD`). It reports correctness bugs and mismatches with the spec, each with a file and line and a concrete failure. It gets the code, not Claude's opinion of it.

- [x] **Step 2: Fix confirmed findings**

Each fix starts with a failing test. A finding that isn't in this plan and doesn't break a spec guarantee goes in the Later list, not into a fix round.

- [x] **Step 3: Re-review, within the fix-loop limits**

Up to two rounds of re-review on the same findings, then one round with a fresh reviewer, then park what's left with a ruling. Four rounds at most.

- [x] **Step 4: Verify**

Run: `.venv/Scripts/python -m pytest tests/amp -v`, push, then watch both workflows with `gh run watch <run-id> --exit-status`.
Expected: all tests PASS locally, and both workflows succeed.

- [x] **Step 5: Close out the plan**

Tick the checkboxes, update the Later list, and commit the plan.

---

## What changed during the build

- Task 1 added two field-order tests. The captured reply repeats values (treble and bass are both 7; page, mute and Do Not Disturb are all 0), so swapped fields passed every planned test.
- `find_status` takes `bytes | bytearray` and an optional zone. `AmpProtocol.wait_for_change(timeout) -> bool` holds the wake-up wait, so nothing can await between the check and the clear.
- The final review found that one late reply could fail the rest of a poll. A query now skips status lines about other zones, and `BadReplyError` is gone. design.md was updated to match.
- The final review also asked for two guard tests, now added. A port failure during a poll comes through as `PortFailedError`. `close()` waits for a command in progress.

## Later

Things that came up but are outside this phase:

- Add a short "Development" section to the README explaining how to run the amp tests locally.
- Phase 2: add a root `tests/conftest.py` that skips the HA tests when `homeassistant` isn't installed, so a bare `pytest` works on Windows.
- Phase 2: HA test files need names that don't repeat the amp tests' file names, because pytest's default import mode can't tell two `test_x.py` files apart.
- Phase 2: HA tests import `custom_components.monoprice_8zone.amp`, never `amp`. `tests/amp/conftest.py` puts the integration folder on `sys.path` for the whole test run, so the module could load twice, each copy with its own exception classes. For the same reason, don't name a platform file after a standard-library module, such as `select.py` or `calendar.py`.
- Phase 2: if setup or the config flow's port check fails after `open_amp` succeeded (for example when no zone answers), close the amp before raising. Otherwise the open connection keeps the port's lock, and every retry reports "port in use" against the integration's own connection.
- Phase 2: round volume and tone values before calling `set_value`. `set_command` truncates (`37.9` sends `37`).
- Phase 2: volume up/down on rapid presses works from state that hasn't refreshed yet.
- Phase 2, optional: an `AmpClosedError(AmpError)` subclass, so "closed on purpose" can be caught by name.
- Test gaps from the final review. The code is correct today; these tests would catch a regression:
  - `test_set_value_without_hash_still_queries` doesn't prove the 0.5-second limit.
  - `send_raw` collecting past a `#` has no test, and the `?10` hardware check depends on it. Neither does waiting up to `RAW_TIMEOUT` for the first byte.
  - No test checks `open_amp`'s serial settings (no XON/XOFF, exclusive access).

## Remaining phases

### Phase 2: The Home Assistant side

The config flow (port, zones and sources, reconfigure, options), setup and unload, the coordinator, the media player, switch and number entities, the `send_command` action, and the HA tests in GitHub Actions.

### Phase 3: Hardware checks and release

Install from `main`, run the four hardware checks with the owner, record the results in PROTOCOL.md, adjust the code, then tag `v0.1.0`.
