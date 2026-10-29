# Monoprice 44518 RS-232 notes

What one 44518 (firmware unknown, set to MASTER) actually did over serial in October 2026, plus why Home Assistant's built-in integration fails on it. "Observed" means seen on this amp. "Unverified" means it comes from the 6-zone (10761) protocol and hasn't been checked on the 44518 yet.

## Connection

- RS-232, 9600 baud, 8 data bits, no parity, 1 stop bit, no flow control. Commands end with a carriage return (CR, `\r`). Observed.
- A straight-through serial cable worked, through an FTDI FT232R USB adapter. Observed.
- Turn off XON/XOFF in your terminal program. PuTTY enables it by default.
- Careful: sending a bare baud rate followed by CR (for example `19200`) changes the amp's baud rate. A power cycle resets it to 9600. Unverified on the 44518.

## Zone IDs

- Master amp zones are `11` to `18`. The amp's rear MASTER/SLAVE switch must be on MASTER. Observed for 11 and 15.
- Linked slave amps would be `21` to `28` and `31` to `38`. Unverified.
- `10` addresses every zone on the master. Unverified.

## Status query

Send `?11` + CR. The 44518 replies with **no echo of the command**. These are the raw bytes as captured:

```
>1100010000100707100200 Zone1    Source02\r\n#
```

After the `>` come 11 two-digit fields, followed by the zone name and the current source name:

| Field | Value here | Meaning | Range |
|---|---|---|---|
| zone | 11 | zone ID | 11-18 |
| PA | 00 | page active | 00/01 |
| PR | 01 | power | 00 off, 01 on |
| MU | 00 | mute | 00/01 |
| DT | 00 | Do Not Disturb | 00/01 |
| VO | 10 | volume | 00-38 |
| TR | 07 | treble | 00-14, 07 flat |
| BS | 07 | bass | 00-14, 07 flat |
| BL | 10 | balance | 00-20, 10 center |
| CH | 02 | source | 01-06 |
| LS | 00 | keypad connected | 00/01 |

The ranges come from the 6-zone protocol docs and match what we saw.

Two differences from the 6-zone amp:

1. **No echo.** The 6-zone amp sends your command back before the reply. The 44518 doesn't.
2. **Names on the end.** The 44518 adds the zone name and source name after the digits.

`?10` should return one line per master zone. Unverified.

## Single-field query

`?xxPP` + CR returns one field. Example: `?15DT` returned `>15DT01`. Observed.

## Set commands

`<xxPPuu` + CR, where `xx` is the zone, `PP` the field and `uu` the two-digit value.

| Command | Effect | Status |
|---|---|---|
| `<11PR01` | zone 11 power on | observed |
| `<11CH02` | zone 11 to source 2 | observed |
| `<11VO10` | zone 11 volume 10 | observed |
| `<15DT01` | zone 15 Do Not Disturb on | observed |
| `<xxMUuu` | mute | unverified |
| `<xxTRuu`, `<xxBSuu`, `<xxBLuu` | treble, bass, balance | unverified |

What the 44518 sends back after a set command hasn't been captured yet.

## PA (paging) and Do Not Disturb

- 12V on the SYSTEM "PA" 3.5mm jack pages Source 1 to every zone, at each zone's own volume. A doorbell chime controller with a 12V trigger output (for example a Niles DBI-2) can drive it directly with a plain 3.5mm cable. Observed wiring; full chime test pending.
- Zones with Do Not Disturb on are left out of the page. DND survived an amp power cycle. Observed.
- Reports from 6-zone owners say paging can only be triggered by 12V, not RS-232.

## Why Home Assistant's built-in integration fails on the 44518

Built-in integration: `homeassistant/components/monoprice`, library `pymonoprice` 0.6.1 (uses `serialx`), checked on HA 2026.10.

1. **It waits for an echo that never comes.** For a status query, `pymonoprice` reads until it has seen the `\r\n#` line ending twice: once for the echo and once for the reply. The 44518 sends only the reply, so every read times out after 2 seconds (`TimeoutError: Connection timed out!`). Zones show Unknown and commands appear to do nothing.
2. **The trailing names are harmless.** `pymonoprice`'s pattern still matches the digits with the names on the end.
3. **Reload breaks the port.** Unloading the integration never closes the serial port. `serialx` takes an exclusive lock when it opens a port, so a reload fails with `OSError: [Errno 16] ... already locked by another process`. A full Home Assistant restart clears it.
4. **Confusing errors.** Setup only catches `serialx.SerialException`. A port held by another integration raises a plain `OSError`, which shows up as "Unexpected error". The first-run timeouts also leave the slave-amp zones (21-24) enabled and polled.
5. **Six zones only.** Zones are fixed at 11-16, 21-26 and 31-36, so there's nothing for zones 17 and 18.
