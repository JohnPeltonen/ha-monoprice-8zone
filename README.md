# Monoprice 8-Zone Amplifier (44518) for Home Assistant

A Home Assistant custom integration for the Monoprice 44518 8-zone whole-home audio amplifier, controlled over RS-232.

## Read this first

I built this for my own amp, and it's provided as-is. I'm not maintaining it, answering questions, or reviewing pull requests. If it helps you, great. If it doesn't quite fit your setup, fork it and make it yours.

Pretty much 100% vibe coded. I, for one, have embraced our AI overlords.

What it's been run on: one 44518 set to MASTER (no linked slave amps), Home Assistant 2026.10, and an FTDI FT232R USB-to-serial adapter.

## Status

The integration is written, and its tests pass in GitHub Actions. It hasn't run on my amp yet: the hardware checks come next, and version 0.1.0 comes after them. [PROTOCOL.md](PROTOCOL.md) documents what the 44518 actually sends over serial.

## Why not the built-in Monoprice integration?

Home Assistant's built-in "Monoprice 6-Zone Amplifier" integration can't read the 44518. The 6-zone amp echoes each command back before it replies, and the library HA uses waits for that echo. The 44518 doesn't echo, so every status read times out and the zones sit at Unknown. The built-in integration also stops at six zones and doesn't release the serial port when you reload it. Details are in [PROTOCOL.md](PROTOCOL.md).

## What it does

- A media player for each zone (1 to 8): power, volume (a slider and up/down buttons), mute and source
- A Do Not Disturb switch for each zone, which keeps that zone out of the amp's hardware PA page (handy for a doorbell chime you don't want playing on the deck)
- Bass, treble and balance sliders for each zone, on the zone's device page
- Source names you choose; unnamed sources stay out of the source list
- Change the serial port without deleting and re-adding the integration
- Reload works, because the integration closes the serial port when it unloads
- A `monoprice_8zone.send_command` action that sends a raw command and shows the amp's reply, for testing from Developer Tools

## Install

- **HACS:** HACS > three-dot menu > Custom repositories > add this repo's URL with type Integration, then install it.
- **Manual:** copy `custom_components/monoprice_8zone` into your Home Assistant `config/custom_components/` folder.

Then restart Home Assistant fully (a reload isn't enough the first time) and add the integration under Settings > Devices & services. Setup asks for the serial port and checks that the amp answers. Then it asks which zones you use and what to call your sources.

If you were using the built-in Monoprice integration, delete it first. Only one integration can hold the serial port at a time.

Tip: pick the `/dev/serial/by-id/...` path for your adapter, not `/dev/ttyUSB0`. The numbered names can swap between USB devices when the server reboots.

## Development

The code that talks to the amp (`custom_components/monoprice_8zone/amp.py`) imports nothing from Home Assistant, so its tests run with plain pytest anywhere, Windows included:

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements_test.txt
.venv/Scripts/python -m pytest
```

On Linux or macOS, use `.venv/bin/python`. The Home Assistant tests in `tests/ha/` need Home Assistant itself, which doesn't run on Windows, so they run only in GitHub Actions. pytest leaves them out when Home Assistant isn't installed.

## License

MIT. See [LICENSE](LICENSE).
