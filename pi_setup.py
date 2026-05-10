#!/usr/bin/env python3
"""Busboy Pi setup script - runs all steps over SSH using paramiko."""

import paramiko
import time
import sys

HOST = "busboy.local"
USER = "pi"
PASSWORD = ""  # set before running

TRACKER_PY = r'''import time
from datetime import datetime
import requests
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in13_V4
import config

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"

def fetch_departures():
    params = {
        "outputFormat": "rapidJSON",
        "coordOutputFormat": "EPSG:4326",
        "mode": "direct",
        "type_dm": "stop",
        "name_dm": config.STOP_ID,
        "departureMonitorMacro": "true",
        "TfNSWDM": "true",
        "version": "10.2.1.42",
    }
    headers = {"Authorization": f"apikey {config.API_KEY}"}
    resp = requests.get(
        "https://api.transport.nsw.gov.au/v1/tp/departure_mon",
        params=params,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def parse_departures(data):
    events = data.get("stopEvents", [])
    results = []
    for ev in events:
        transport = ev.get("transportation", {})
        if transport.get("number") != config.ROUTE:
            continue
        dest = transport.get("destination", {}).get("name", "")
        if "Martin Place" not in dest:
            continue
        dep_time_str = ev.get("departureTimeEstimated") or ev.get("departureTimePlanned")
        if not dep_time_str:
            continue
        # Parse ISO8601: 2024-05-10T14:35:00+10:00
        try:
            dep_dt = datetime.fromisoformat(dep_time_str)
            results.append(dep_dt)
        except ValueError:
            continue
    results.sort()
    return results[:4]

def render(epd, departures, updated_at):
    font_large = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 14)
    font_med   = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", 12)
    font_small = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf", 10)

    # Landscape: width=epd.height, height=epd.width
    w, h = epd.height, epd.width
    image = Image.new("1", (w, h), 255)
    draw = ImageDraw.Draw(image)

    # Header
    draw.text((4, 2), f"{config.ROUTE} → Martin Place", font=font_large, fill=0)
    draw.line([(0, 20), (w, 20)], fill=0, width=1)

    now = datetime.now().astimezone()
    y = 24
    if not departures:
        draw.text((4, y), "No departures found", font=font_med, fill=0)
    else:
        for dep_dt in departures:
            minutes = int((dep_dt - now).total_seconds() / 60)
            due_str = "Due" if minutes <= 0 else f"{minutes} min"
            sched_str = dep_dt.strftime("%H:%M")
            draw.text((4, y), due_str, font=font_med, fill=0)
            draw.text((70, y), sched_str, font=font_med, fill=0)
            y += 18

    # Last updated bottom-right
    upd_str = f"Upd {updated_at.strftime('%H:%M')}"
    bbox = draw.textbbox((0, 0), upd_str, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text((w - tw - 4, h - 12), upd_str, font=font_small, fill=0)

    epd.init()
    epd.display(epd.getbuffer(image))
    epd.sleep()

def main():
    epd = epd2in13_V4.EPD()
    while True:
        try:
            data = fetch_departures()
            departures = parse_departures(data)
            render(epd, departures, datetime.now())
        except Exception as e:
            print(f"Error: {e}", flush=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
'''

FIND_STOP_PY = r'''import requests
import config

def search(name):
    params = {
        "outputFormat": "rapidJSON",
        "type_sf": "stop",
        "name_sf": name,
        "coordOutputFormat": "EPSG:4326",
        "TfNSWSF": "true",
        "version": "10.2.1.42",
    }
    headers = {"Authorization": f"apikey {config.API_KEY}"}
    resp = requests.get(
        "https://api.transport.nsw.gov.au/v1/tp/stop_finder",
        params=params,
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def print_results(data):
    locations = data.get("locations", [])
    if not locations:
        print("No results found.")
        return False
    for loc in locations:
        name = loc.get("name", "")
        stop_id = loc.get("id", "")
        coord = loc.get("coord", [])
        print(f"Name: {name} | ID: {stop_id} | Coord: {coord}")
    return True

def main():
    primary = "Homer St after Undercliffe Rd"
    print(f"Searching for: {primary}")
    data = search(primary)
    found = print_results(data)
    if not found:
        fallback = "Homer St Earlwood"
        print(f"Trying fallback: {fallback}")
        data = search(fallback)
        print_results(data)

if __name__ == "__main__":
    main()
'''

CONFIG_PY = '''API_KEY = "REPLACE_WITH_TFNSW_API_KEY"
STOP_ID = ""  # will be filled in after running find_stop.py
ROUTE = "423"
'''

SERVICE = '''[Unit]
Description=423 Bus Tracker
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/busticker/tracker.py
Restart=always
RestartSec=30
User=pi
WorkingDirectory=/home/pi/busticker

[Install]
WantedBy=multi-user.target
'''


def run(client, cmd, timeout=300):
    print(f"\n>>> {cmd}")
    # Use a shell wrapper so sudo doesn't need a PTY; stream output line by line
    transport = client.get_transport()
    chan = transport.open_session()
    chan.settimeout(timeout)
    chan.exec_command(cmd)

    out_parts = []
    err_parts = []

    # Stream stdout/stderr until channel closes
    import select as _select
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            print("[TIMEOUT]")
            break
        ready, _, _ = _select.select([chan], [], [], min(remaining, 2.0))
        if ready:
            if chan.recv_ready():
                chunk = chan.recv(4096).decode(errors="replace")
                out_parts.append(chunk)
                # Print streamed output immediately
                for line in chunk.splitlines():
                    print(line)
            if chan.recv_stderr_ready():
                chunk = chan.recv_stderr(4096).decode(errors="replace")
                err_parts.append(chunk)
                for line in chunk.splitlines():
                    print("[stderr]", line)
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break

    out = "".join(out_parts)
    err = "".join(err_parts)
    rc = chan.recv_exit_status()
    chan.close()
    if rc != 0:
        print(f"[EXIT CODE {rc}]")
    return rc, out, err


def write_file(client, path, content):
    """Write content to a remote file via SFTP."""
    sftp = client.open_sftp()
    with sftp.open(path, "w") as f:
        f.write(content)
    sftp.close()
    print(f"Written: {path}")


def main():
    print(f"Connecting to {HOST} as {USER}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    print("Connected.\n")

    # Grant NOPASSWD sudo for this session so we don't need -S everywhere
    print("Configuring passwordless sudo for pi...")
    nopasswd_cmd = (
        f"echo '{PASSWORD}' | sudo -S bash -c "
        f"\"echo 'pi ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/pi-nopasswd && chmod 440 /etc/sudoers.d/pi-nopasswd\""
    )
    rc, _, _ = run(client, nopasswd_cmd)
    if rc != 0:
        print("WARNING: Could not configure passwordless sudo. Sudo commands may fail.")

    errors = []

    def step(label, cmd, timeout=300):
        print(f"\n{'='*60}")
        print(f"STEP: {label}")
        print('='*60)
        rc, out, err = run(client, cmd, timeout=timeout)
        if rc != 0:
            errors.append(f"{label}: exit code {rc}")
            print(f"[WARNING] Step failed with exit code {rc}")
        return rc

    # Step 1: Enable SPI
    step("Enable SPI", "sudo raspi-config nonint do_spi 0")

    # Step 2: Update system
    step("Update system", "sudo apt-get update && sudo apt-get upgrade -y", timeout=600)

    # Step 3: Install system dependencies
    step("Install system deps",
         "sudo apt-get install -y python3-pip python3-pil python3-numpy python3-venv "
         "libjpeg-dev zlib1g-dev fonts-dejavu git", timeout=300)

    # Step 4: Install spidev and requests
    step("Install spidev + requests",
         "sudo pip3 install spidev requests --break-system-packages", timeout=120)

    # Step 5: Clone Waveshare library
    rc, out, _ = run(client, "test -d /home/pi/e-Paper && echo exists")
    if "exists" in out:
        print("e-Paper directory already exists, skipping clone.")
    else:
        step("Clone Waveshare e-Paper",
             "git clone https://github.com/waveshare/e-Paper.git /home/pi/e-Paper", timeout=120)

    # Step 6: Install Waveshare Python library
    step("Install Waveshare Python lib",
         "cd /home/pi/e-Paper/RaspberryPi_JetsonNano/python && sudo python3 setup.py install",
         timeout=120)

    # Step 7: Create busticker directory
    step("Create busticker dir", "mkdir -p /home/pi/busticker")

    # Step 8: Create config.py
    print(f"\n{'='*60}\nSTEP: Create config.py\n{'='*60}")
    write_file(client, "/home/pi/busticker/config.py", CONFIG_PY)

    # Step 9: Create find_stop.py
    print(f"\n{'='*60}\nSTEP: Create find_stop.py\n{'='*60}")
    write_file(client, "/home/pi/busticker/find_stop.py", FIND_STOP_PY)

    # Step 10: Create tracker.py
    print(f"\n{'='*60}\nSTEP: Create tracker.py\n{'='*60}")
    write_file(client, "/home/pi/busticker/tracker.py", TRACKER_PY)

    # Step 11: Create systemd service
    print(f"\n{'='*60}\nSTEP: Create busticker.service\n{'='*60}")
    # Write to /tmp first, then sudo copy
    write_file(client, "/tmp/busticker.service", SERVICE)
    step("Install service file",
         "sudo cp /tmp/busticker.service /etc/systemd/system/busticker.service")

    # Step 12: Enable and start service
    step("Reload systemd", "sudo systemctl daemon-reload")
    step("Enable service", "sudo systemctl enable busticker")
    step("Start service", "sudo systemctl start busticker")

    # Step 13: Verify service
    print(f"\n{'='*60}\nSTEP: Verify service status\n{'='*60}")
    time.sleep(3)
    run(client, "sudo systemctl status busticker --no-pager -l")

    client.close()

    print(f"\n{'='*60}")
    if errors:
        print("SETUP COMPLETE WITH ERRORS:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("SETUP COMPLETE - no errors reported.")
    print('='*60)


if __name__ == "__main__":
    main()
