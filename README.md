# Monoprice 8-Zone Amplifier (44518) for Home Assistant

A Home Assistant custom integration for the Monoprice 44518 8-zone whole-home audio amplifier, controlled over RS-232.

## Read this first

I built this for my own amp, and it's provided as-is. I'm not maintaining it, answering questions, or reviewing pull requests. If it helps you, great. If it doesn't quite fit your setup, fork it and make it yours.

Pretty much 100% vibe coded. I, for one, have embraced our AI overloards.

What it's been run on: one 44518 set to MASTER (no linked slave amps), Home Assistant 2026.10, and an FTDI FT232R USB-to-serial adapter.

## Status

Work in progress. The integration code isn't written yet. [PROTOCOL.md](PROTOCOL.md) documents what the 44518 actually sends over serial, and right now that's the most useful thing in this repo.

## Why not the built-in Monoprice integration?

Home Assistant's built-in "Monoprice 6-Zone Amplifier" integration can't read the 44518. The 6-zone amp echoes each command back before it replies, and the library HA uses waits for that echo. The 44518 doesn't echo, so every status read times out and the zones sit at Unknown. The built-in integration also stops at six zones and doesn't release the serial port when you reload it. Details are in [PROTOCOL.md](PROTOCOL.md).

## What it will do

- A media player for each zone (1 to 8): power, volume, mute and source
- A Do Not Disturb switch for each zone, which keeps that zone out of the amp's hardware PA page (handy for a doorbell chime you don't want playing on the deck)
- Source names you choose; unnamed sources stay out of the source list
- Change the serial port without deleting and re-adding the integration

## Install (once there's code)

- **HACS:** HACS > three-dot menu > Custom repositories > add this repo's URL with type Integration, then install it.
- **Manual:** copy `custom_components/monoprice_8zone` into your Home Assistant `config/custom_components/` folder.

Then restart Home Assistant fully (a reload isn't enough the first time) and add the integration under Settings > Devices & services.

If you were using the built-in Monoprice integration, delete it first. Only one integration can hold the serial port at a time.

Tip: pick the `/dev/serial/by-id/...` path for your adapter, not `/dev/ttyUSB0`. The numbered names can swap between USB devices when the server reboots.

## License

MIT. See [LICENSE](LICENSE).
