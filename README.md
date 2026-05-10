# Busboy

A Raspberry Pi Zero 2W bus tracker that displays real-time Sydney bus departure times on a Waveshare 2.13" e-ink display.

## Hardware required

- Raspberry Pi Zero 2W (with Raspberry Pi OS installed)
- Waveshare 2.13" e-Paper HAT V4

## Setup

### 1. Fill in your Pi's SSH details

At the top of `pi_setup.py`:

```python
HOST = "your-pi.local"   # or IP address
USER = "pi"
PASSWORD = "yourpassword"
```

### 2. Run the setup script

```bash
pip install paramiko
python pi_setup.py
```

This will SSH into the Pi and automatically:
- Enable SPI
- Install all dependencies
- Clone the Waveshare e-Paper library
- Create `/home/pi/busticker/` with all scripts
- Set up and start the `busticker` systemd service

### 3. Get a TfNSW API key

Register at [opendata.transport.nsw.gov.au](https://opendata.transport.nsw.gov.au) and create an app with access to the **Trip Planner APIs**.

### 4. Configure your route

SSH into the Pi and edit `/home/pi/busticker/config.py`:

```python
API_KEY = "your-api-key-here"
STOP_ID = ""      # find this in step 5
ROUTE   = "423"   # change to your route number
```

### 5. Find your stop ID

```bash
python3 /home/pi/busticker/find_stop.py
```

This searches for stops by name. Edit the search terms at the bottom of `find_stop.py` to match your street. Copy the ID (e.g. `G2206105`) into `config.py`.

> **Tip:** Make sure you pick the stop on the correct side of the road — stops on opposite sides have different IDs and serve opposite directions.

### 6. Update tracker.py for your route

`tracker.py` has two values hardcoded for the original route that you'll need to change for a different destination:

```python
# In main(), change "Martin Place" to your route's destination:
departures = parse_departures(data, "Martin Place")
uts_times  = parse_departures(uts_data, "Martin Place")

# Change UTS_STOP_ID to a stop ID along your route you want arrival times for:
UTS_STOP_ID = "G200723"   # UTS, Broadway, Ultimo
```

Use `find_stop.py` to look up the arrival stop ID.

### 7. Restart the service

```bash
sudo systemctl restart busticker
sudo journalctl -u busticker -n 20 --no-pager
```

## Display layout

```
423 → Martin Place         17:05
Sun 10 May 2026
─────────────────────────────────
Due    17:05   →UTS 17:33
8min   17:13   →UTS 17:41
23min  17:28   →UTS 17:56
38min  17:43   →UTS 18:11
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No departures found" | Wrong stop ID or wrong side of road | Re-run `find_stop.py`, check both stop IDs |
| `401 Client Error` | Invalid or missing API key | Check `API_KEY` in `config.py` |
| Service crashes on import | `waveshare_epd` not installed | Re-run `pi_setup.py` or manually run `setup.py install` in `/home/pi/e-Paper/RaspberryPi_JetsonNano/python/` |
| `→UTS --:--` shown | No matching arrival found in 15–50 min window | Adjust `UTS_MIN_TRAVEL` / `UTS_MAX_TRAVEL` in `tracker.py` |
