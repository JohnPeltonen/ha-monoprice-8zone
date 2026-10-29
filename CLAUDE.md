# Building this repo

A Home Assistant custom integration for one Monoprice 44518 8-zone amp over RS-232. Read [PROTOCOL.md](PROTOCOL.md) first: it records what the amp actually sends and why HA's built-in `monoprice` integration fails on it. Then read [docs/design.md](docs/design.md): the full design, and who decided what.

## Scope

- Published as-is and unmaintained. Build for the 44518 and keep it small. This isn't a general Monoprice library.
- The read code must tolerate an echo (cheap, and it helps people who fork this for 4- or 6-zone amps). Don't build or test anything else for other models.
- Zones 11 to 18 on the MASTER amp only. Never query slave zones (21 and up).

## Names

- Domain: `monoprice_8zone`. Never `monoprice` (that's the built-in integration).
- Display name: "Monoprice 8-Zone Amplifier (44518)".
- When naming a category field, use `type` (or `<thing>_type`), never `kind`.

## Target

- Home Assistant 2026.10, Python 3.14.
- Serial: `serialx>=1.11.0` in the manifest. hassfest rejects an exact pin on a package HA itself uses, and HA 2026.10's `usb` integration pins 1.11.0. Tests pin `serialx==1.11.0`. Don't depend on `pymonoprice`.
- List `usb` under `dependencies` in the manifest. `SerialPortSelector` gets its list of ports from it.
- Forms use `probatio`, which replaced `voluptuous` in HA 2026.10.

## Requirements

- **Reads:** write the command, then read until a line matching `>(\d{2})(\d{20})` is followed by `#`, or until an idle gap or an overall timeout. Ignore an echoed command if one shows up. Ignore the trailing zone and source names. A set command gets a single `#` back (the owner's recollection, not captured yet).
- **Connection:** one serial connection per config entry, every command behind one `asyncio.Lock`, opened on setup and **explicitly closed on unload**, so Reload works.
- **Errors:** turn a port lock (`OSError` errno 16), a missing port and timeouts into clear config-flow errors, and into `ConfigEntryNotReady` during setup.
- **Config flow:** pick the port with `SerialPortSelector`; zones (1-8) to enable; source names for 1-6, where unnamed sources stay out of the source list (Source 1 is often a doorbell chime). Add a **reconfigure** step so the port can change without deleting the entry. Use an options flow for zones and source names.
- **Polling:** one `DataUpdateCoordinator` polls every enabled zone (a `?10` bulk query if the hardware check shows it works, otherwise one query per zone). Never query slave zones.
- **Entities:** one device per zone, each linked to one device for the amp.
  - `media_player` per zone: on/off, volume (00-38 mapped to 0.0-1.0, plus volume step), mute, source select.
  - `switch` per zone: Do Not Disturb (`DT`).
  - `number` per zone: bass, treble and balance, as configuration entities.
  - No page-active (`PA`) sensor in v1.
- **After a set command,** refresh that zone's state. The amp doesn't send it back.

## Repo layout

- `custom_components/monoprice_8zone/` holds everything (manifest, `__init__.py`, config flow, coordinator, platforms, `strings.json` and `translations/en.json`).
- `manifest.json`: `documentation` and `issue_tracker` both point to the repo URL; `version` is semver; `codeowners` is `["@JohnPeltonen"]`; `iot_class` is `local_polling`; `config_flow` is true.
- `hacs.json` is already in the root. Keep the `homeassistant` minimum version accurate.
- Add `.github/workflows/hassfest.yaml` (uses `home-assistant/actions/hassfest`) once the integration exists. Releases: tag `vX.Y.Z` to match the manifest version.

## Diagnostics (needed for testing on real hardware)

- A `monoprice_8zone.send_command` action that sends a raw command string and returns the amp's raw reply as action response data. This lets the owner run the hardware checks below from Developer Tools > Actions, without unplugging the cable or using PuTTY.
- Log every raw write and read at debug level.

## Tests

- pytest with `pytest-homeassistant-custom-component`.
- **The owner develops on native Windows, without WSL, and Home Assistant doesn't run on native Windows.** So:
  - Keep the protocol layer (transport, framing, reply parser, command builders) free of `homeassistant` imports, so its tests run locally with plain `pytest` on Windows. This is the fast loop.
  - Everything that imports `homeassistant` (config flow, setup/unload, entities) is tested only in GitHub Actions. Don't try to install or run Home Assistant locally.
  - First task: add `.github/workflows/tests.yaml` (ubuntu-latest, Python 3.14, runs on push and pull request) and `hassfest.yaml`.
  - After pushing, check results with `gh run watch` and `gh run view --log-failed`, and fix failures before moving on.
- A fake serial transport that replays the captured 44518 reply from PROTOCOL.md; one variant with an echo; one with a timeout.
- Cover the config flow (including the port-lock error), setup and unload (the port gets closed), and the reply parser.

## Hardware checks still to run (needs the owner at the amp)

1. Confirm that a set command gets a single `#` back.
2. Whether `?10` returns all eight zones.
3. The replies for zones 17 and 18.
4. Whether the set commands for mute, bass, treble and balance work, and which end of the balance scale is left.

Write the results into PROTOCOL.md (change "unverified" to "observed").

## Working agreements (approved by the owner on 2026-10-29)

- **Pushing:** Claude may push to `main` in this repo, because the HA tests only run in GitHub Actions. This is an exception to the owner's usual rule.
- **Plans:** one phase per plan. Claude builds each phase directly, without handing each task to a separate agent. A very capable reviewer agent reviews each plan before building starts, and reviews the code at the end of each phase. Work doesn't stop at a token limit.
- **Names:** the owner's name and GitHub handle are fine where GitHub or HA needs them (LICENSE, `codeowners`, commit author). Keep other household members' names out of the repo.
- **Notes:** anything useful to other people goes in PROTOCOL.md, docs/design.md or this file. Notes personal to the owner go in `.claude/docs/memory/`, which is gitignored.

## Writing style for docs in this repo

- No em dashes. Use a comma or a period.
- Plain, first-person voice in the README ("I built this for my own amp").
