# Design: Monoprice 8-Zone Amplifier (44518) for Home Assistant

This document describes what the integration does, why, and the decisions behind it. It's for two readers: someone with a 44518 deciding whether to use this, and someone adapting it for their own amp.

"I" in this document is the amp's owner, who set the requirements. Claude, an AI coding assistant, wrote this document and most of the code. Decisions marked **(Claude's call)** were made while writing this design. They're defaults, not requirements, and you can change them.

What the amp actually sends over serial is in [PROTOCOL.md](../PROTOCOL.md).

## Why this exists

I own one Monoprice 44518, an 8-zone whole-home audio amplifier, and I control it from Home Assistant (HA) over RS-232. HA has a built-in Monoprice integration, written for the 6-zone amp (model 10761). On the 44518 it fails in three ways:

1. **Every status read times out.** The 6-zone amp sends each command back (an "echo") before it replies, and the built-in integration waits for that echo. The 44518 doesn't send one, so the zones sit at Unknown.
2. **Zones 7 and 8 are missing.** It only knows six zones.
3. **Reload breaks the port.** It never closes the serial port, so reloading fails until HA restarts.

This integration fixes all three, for the 44518 only.

## What version 0.1.0 does

- Each of the 8 zones is its own device in HA, with:
  - a **media player**: power, volume (a slider and up/down buttons), mute and source;
  - a **Do Not Disturb switch**. A zone with Do Not Disturb on is left out of the amp's hardware page. (A 12V signal on the amp's PA jack plays Source 1 in every zone, for example for a doorbell chime.);
  - **bass, treble and balance** sliders. Balance also helps check speaker wiring.
- Sources get names you choose. A source without a name stays out of the source list.
- You can change the serial port without deleting the integration.
- Reload works, because unloading closes the port.
- Errors say what went wrong: the port is in use, the port doesn't exist, or the amp didn't answer.
- A `monoprice_8zone.send_command` action sends a raw command and returns the amp's raw reply. It's for testing the amp from HA's Developer Tools.

## Not in version 0.1.0

- **Other Monoprice models.** The read code tolerates an echo, which helps if you fork this for a 6-zone amp. Nothing else is built or tested for other models.
- **Linked amps.** Extra amps can be linked to the first one and set to SLAVE (their zones would be 21 to 28 and 31 to 38). This integration only ever talks to zones 11 to 18 on the MASTER amp.
- **A "page active" sensor.** HA checks the amp every 30 seconds, so it would miss most short pages, such as a doorbell chime. Watching the 12V page trigger directly would catch them. That's a separate project.
- **Music that follows each person around the house.** That's a later project: HA automations that use presence detection (for example Bluetooth beacons) to control these media players. It doesn't need anything added here.
- **The names stored in the amp.** The status reply ends with a zone name and a source name. The integration ignores both.
- **Changing the amp's baud rate.**
- **Support.** As the README says, this is published as-is.

## What would make it a failure

It has failed, even if every feature technically works, if:

- a tap on the dashboard stalls for seconds before the amp reacts (the built-in integration's main problem);
- Reload needs a full HA restart;
- a problem shows up as "Unexpected error" instead of saying what's wrong;
- it queries zones that don't exist;
- sources I don't play music from, like a doorbell-chime input, show up in the source list.

## Constraints

- **Home Assistant 2026.10 or newer, Python 3.14.**
- **Serial library:** `serialx` version 1.11.0, the same version HA 2026.10 requires. Not `pymonoprice`. `serialx` opens ports through asyncio (`serialx.open_serial_connection`) and locks the port for exclusive use by default.
- **Forms:** HA 2026.10 builds config-flow forms with `probatio`, which replaced `voluptuous`. HA's built-in integrations show the style.
- **The `usb` integration is a dependency** in `manifest.json`. The port picker (`SerialPortSelector`) gets its list of ports from it.
- **One amp per HA install.** Only one config entry (one configured copy of the integration) is allowed.
- **Domain `monoprice_8zone`.** Never `monoprice`, which is the built-in integration.
- **Tests without HA on Windows.** I develop on native Windows, where HA can't run. So the code that talks to the amp imports nothing from `homeassistant`, and its tests run with plain `pytest` on Windows. Everything that imports `homeassistant` is tested only in GitHub Actions.
  - Python runs a package's `__init__.py` before any module inside it, and this integration's `__init__.py` imports `homeassistant`. So the amp code lives in one module that imports nothing from the rest of the integration, and its tests load that module without loading the package. **(Claude's call)**

## How it talks to the amp

### Connection

- 9600 baud, 8 data bits, no parity, 1 stop bit, no flow control. Commands end with a carriage return (CR, `\r`).
- One serial connection per config entry. It's opened during setup and closed during unload.
- One command at a time. Every command, including polls, waits behind one `asyncio.Lock`. So commands sent close together, from a slider or an automation, reach the amp in order.
- Before each command, bytes already waiting from the amp are thrown away, so a late reply can't be mistaken for the next one. **(Claude's call)**
- Every raw write and read is logged at debug level.
- If the serial port itself fails while running (for example the USB adapter is unplugged), the integration reloads itself. Setup then fails with `ConfigEntryNotReady`, and HA keeps retrying on its own until the port is back. A timeout is not a port failure: it only means the amp didn't answer. **(Claude's call)**

### Status query

Send `?1z`, where `z` is the zone number 1 to 8 (so `?11` to `?18`). Read until a line matching `>(\d{2})(\d{20})` is followed by `#`.

- If the amp echoes the command first, the echo is skipped. (The 44518 doesn't echo. The 6-zone amp does.)
- The zone and source names after the digits are ignored.
- A reply for a different zone than the one asked about is an error. **(Claude's call)**
- No complete reply within 1 second is a timeout. A reply takes about 50 ms to arrive at 9600 baud. **(Claude's call)**

### Set commands

Send `<1zPPuu`: zone, two-letter field, two-digit value. For example, `<11VO10` sets zone 1 to volume 10. The fields are listed in PROTOCOL.md.

- I remember the 44518 answering a set command with a single `#` and nothing else, so the code reads until `#`. This hasn't been captured yet. The first hardware check confirms it.
- If no `#` arrives within 0.5 seconds, the code logs that at debug level and carries on. **(Claude's call)**
- Then the code queries that zone's status and updates HA, so HA shows what the amp actually did. The amp doesn't send the new status by itself.

### Polling

- Every 30 seconds, HA queries each enabled zone, one at a time. **(Claude's call.** In my house nothing changes the amp outside HA, so polling is a backup, for example after a power cut.)
- The all-zones query (`?10`) isn't used until a hardware check shows the 44518 returns all 8 zones.
- If a zone doesn't answer during a poll, that zone's entities show as unavailable until it answers again. The other zones carry on. **(Claude's call.** If one zone misbehaves, for example zone 7 or 8 before the hardware checks, the rest of the amp and the `send_command` action still work.)
- If no zone answers, the poll fails, and every entity shows as unavailable until a poll succeeds.

### Values

| Setting | Amp value | In HA |
|---|---|---|
| Volume | 00 to 38 | 0% to 100%. Setting a volume rounds to the nearest amp step. |
| Volume up/down | | One amp step per press. The built-in integration does the same. **(Claude's call)** |
| Bass, treble | 00 to 14, 07 is flat | -7 to +7, 0 is flat. **(Claude's call)** |
| Balance | 00 to 20, 10 is center | -10 to +10, 0 is center, negative is left. Which end of the amp's scale is left gets confirmed in a hardware check. **(Claude's call)** |

## What shows up in HA

### Devices

A device in HA groups the entities (controls and readings) that belong to one piece of hardware.

- One device for the amp, "Monoprice 44518". It has no entities of its own. It ties the zone devices together.
- One device for each enabled zone, named "Zone 1" to "Zone 8", linked to the amp device. Rename a zone device once (for example to "Kitchen") and all its entities follow. Each zone device can go in its own HA area (room).
- In HA the zones are 1 to 8. The amp's own zone IDs are 11 to 18.
- Unique IDs come from the config entry and the zone number, not the port, so changing the port doesn't affect devices or entities. **(Claude's call)**

### Entities for each zone

- **Media player**, named after its zone device.
  - State: on or off. The amp doesn't know whether music is playing.
  - Features: turn on, turn off, set volume, volume up/down, mute, select source.
  - Source list: the named sources, in order 1 to 6. If the zone is on a source without a name, the media player reports it as "Source N", which isn't in the list. **(Claude's call)**
- **Switch:** Do Not Disturb.
- **Numbers (sliders):** Bass, Treble, Balance. They're configuration entities, so they appear in the Configuration section of the device page, and HA doesn't add them to dashboards automatically. **(Claude's call)**

When a zone is turned off in the options, its device and entities are removed from HA. **(Claude's call)**

## Setup screens

### Adding the integration

1. **Port.** Pick the serial port from a list. The integration opens it and asks zone 1 for its status, to check that the amp answers.
2. **Zones and sources.** Choose the zones to enable. All 8 are checked to start. Name sources 1 to 6. All names start blank, and a blank name keeps that source out of the source list. **(Claude's call:** two screens, and blank names to start.)

Errors on the port screen:

| Problem | How it's detected | What the message says |
|---|---|---|
| Port in use | `OSError` with errno 16 (`EBUSY`). `serialx` locks the port, so this means another program or integration has it open, for example the built-in Monoprice integration. | The port is in use. If the built-in Monoprice integration is set up, delete it first. |
| Port not found | `OSError` such as `ENOENT` (no such file) | The port doesn't exist. Check that the USB adapter is plugged in. |
| No answer | Timeout | The amp didn't answer. Check that it's powered on, the cable is connected, and the rear switch is set to MASTER. |

Anything else shows a generic error and logs the details.

### Changing the port (reconfigure)

A Reconfigure screen lets you pick a different port. It runs the same check, then reloads the integration. Devices, entities and their settings stay the same.

If the new port is the same device the integration already has open (the same path, or a link to it such as a `/dev/serial/by-id/...` path), the check is skipped. Otherwise the integration's own lock on the port would make the check report the port as in use. **(Claude's call)**

### Options

Change the enabled zones and the source names. Saving reloads the integration.

### When HA starts

If the port is in use or missing, or none of the zones answer, setup raises `ConfigEntryNotReady` with the same explanation. HA retries on its own.

### Commands that fail

If the amp doesn't answer a command from the dashboard or an automation, HA shows an error saying the amp didn't answer.

## The `send_command` action

An action in HA is something you can run from Developer Tools, a script or an automation.

- **Input:** `command`, the text to send without the CR, for example `?11` or `<11MU01`. The integration adds the CR.
- **Only commands starting with `?` or `<` are accepted.** A bare number like `19200` would change the amp's baud rate, and only a power cycle undoes that. **(Claude's call)**
- **Reading:** it collects everything the amp sends until the amp has been quiet for 0.3 seconds, or until 2 seconds have passed. This works whatever the reply looks like. **(Claude's call)**
- **Output:** the reply as action response data, with CR and LF written out as `\r` and `\n` so they're visible. **(Claude's call)**
- It waits behind the same lock as every other command. If it changes a setting, HA shows the change at the next poll.

## Tests

### Amp code (plain `pytest`, on Windows and in GitHub Actions)

A fake serial connection replays:

- the captured 44518 status reply from PROTOCOL.md;
- the same reply with an echo in front (the 6-zone amp's behavior);
- no reply (timeout);
- a single `#` after a set command;
- stray bytes before a reply **(Claude's call)**;
- a reply for the wrong zone **(Claude's call)**.

The reply parser and the command builders are tested too.

### HA side (GitHub Actions only, with `pytest-homeassistant-custom-component`)

- Config flow: success, port in use, port not found, no answer; reconfigure; options.
- Setup and unload, including that unload closes the port.
- Entities: media player features and the volume mapping, Do Not Disturb, and the bass, treble and balance mapping.
- The `send_command` action's response.

### GitHub workflows

- `.github/workflows/tests.yaml`: ubuntu-latest, Python 3.14, on every push and pull request.
- `.github/workflows/hassfest.yaml`: HA's manifest checker (`home-assistant/actions/hassfest`).

## Hardware checks

These need the owner at the amp, after the integration is installed. Each one is run from Developer Tools > Actions with `send_command`. Results go in PROTOCOL.md, where "unverified" becomes "observed".

1. A set command, for example `<11VO10`, gets a single `#` back.
2. `?10` returns all 8 zones.
3. Zones 17 and 18 reply like the others.
4. The set commands for mute, bass, treble and balance work, and we learn which end of the balance scale is left. Balance also checks speaker wiring: slide it fully to one side, and only that side's speaker should play.

## Release

- `version` 0.1.0 in `manifest.json`, with a matching git tag `v0.1.0`.
- `hacs.json` keeps the minimum HA version accurate (2026.10.0).
- Installed through HACS as a custom repository.
- The hardware checks run on a version installed from `main`. The `v0.1.0` tag comes after them. **(Claude's call)**

## Later

- Poll with `?10`, if the `?10` check passes.
- A page sensor driven by the 12V trigger.
- Music that follows each person around the house.

## Who decided what

I (the owner) decided:

- the scope: one 44518 set to MASTER, zones 1 to 8, no linked amps, and no other models apart from tolerating an echo;
- the entities: media player, Do Not Disturb, bass, treble and balance, with no page sensor;
- one device per zone;
- a volume slider, plus buttons;
- `serialx`, not `pymonoprice`;
- named sources, with unnamed sources hidden;
- a reconfigure screen for the port, and options for zones and source names;
- the `send_command` action and debug logging;
- the test split: amp code on Windows, HA code in GitHub Actions.

Everything marked **(Claude's call)** above was decided by Claude.
