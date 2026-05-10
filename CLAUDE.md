# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Raspberry Pi Zero 2W bus tracker that displays real-time Sydney route 423 departure times on a Waveshare 2.13" e-ink display. The Pi is at `busboy.local` (user: `pi`).

All Pi-side code lives in `/home/pi/busticker/` and is managed remotely from this Windows machine via paramiko SSH/SFTP. There is no local copy of the Pi files in this repo — edits are written directly to the Pi over SFTP.

## Pi-side file layout

| File | Purpose |
|------|---------|
| `/home/pi/busticker/config.py` | API key, stop ID, route number |
| `/home/pi/busticker/tracker.py` | Main loop: fetch → parse → render |
| `/home/pi/busticker/find_stop.py` | CLI utility to look up stop IDs by name |
| `/etc/systemd/system/busticker.service` | systemd unit (autostart on boot) |
| `/home/pi/e-Paper/` | Waveshare library source (cloned from GitHub) |

## Common Pi commands (run via SSH)

```bash
sudo systemctl status busticker          # service health
sudo systemctl restart busticker         # deploy after editing tracker.py/config.py
sudo journalctl -u busticker -n 50 --no-pager  # recent logs
python3 /home/pi/busticker/find_stop.py  # look up a stop ID by name
```

## Deploying changes

Write updated file content to the Pi via SFTP, then restart the service:

```python
sftp = client.open_sftp()
with sftp.open('/home/pi/busticker/tracker.py', 'w') as f:
    f.write(content)
sftp.close()
# then: sudo systemctl restart busticker
```

## Architecture: tracker.py

Single-process polling loop (60s interval):
1. `fetch_departures(stop_id)` — calls TfNSW Departure Monitor API
2. `parse_departures(data, dest_filter)` — filters by route number + destination substring
3. For UTS arrivals: fetch `UTS_STOP_ID` separately, then `match_uts_arrival()` pairs each Earlwood departure to the first UTS departure 15–50 min later (trip IDs are non-unique across services, so time-window matching is used instead)
4. `render(epd, departures, uts_times, now)` — draws to e-ink and calls `epd.sleep()`

Display is 250×122 px landscape. Create image as `Image.new('1', (epd.height, epd.width), 255)` — note the axis swap. Full refresh every cycle (no partial update) to prevent ghosting.

## TfNSW API notes

- **Auth header**: `Authorization: apikey {API_KEY}` (JWT token, not a simple key)
- **Stop Finder**: `GET https://api.transport.nsw.gov.au/v1/tp/stop_finder`
  - Use `type_sf=any` — `type_sf=stop` returns error code -2000 ("stop invalid")
  - Filter response `locations` for `type == "stop"` to exclude streets/POIs
- **Departure Monitor**: `GET https://api.transport.nsw.gov.au/v1/tp/departure_mon`
  - Use `type_dm=stop` with the stop's `id` field (e.g. `G2206105`)
- Both endpoints require `outputFormat=rapidJSON` and `version=10.2.1.42`

## Stop IDs

| Stop | ID | Notes |
|------|----|-------|
| Homer St opp Undercliffe Rd, Earlwood | `G2206105` | **Inbound** (to Martin Place) — correct stop |
| Homer St after Undercliffe Rd, Earlwood | `G2206106` | Outbound (to Kingsgrove Depot) — wrong direction |
| UTS, Broadway, Ultimo | `G200723` | UTS arrival stop |

## SSH interaction from Windows

Use `paramiko`. The Pi has NOPASSWD sudo configured (`/etc/sudoers.d/pi-nopasswd`).

The → character (U+2192) is used in tracker.py display strings. When printing Pi output to the Windows console, encode with `.encode('ascii', errors='replace').decode()` to avoid `UnicodeEncodeError` on cp1252 terminals.

## Hardware

- Waveshare 2.13" e-Paper V4 (`epd2in13_V4`), connected via SPI
- SPI enabled via `raspi-config nonint do_spi 0`
- Waveshare library installed from `/home/pi/e-Paper/RaspberryPi_JetsonNano/python/setup.py` — the `Jetson.GPIO` dependency fails to install but is unused on Pi (RPi.GPIO is used instead); this is expected and harmless
