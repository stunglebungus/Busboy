# Claude Setup Prompt

Copy everything below this line and paste it into Claude Code to have Claude set up Busboy on your Pi automatically.

---

I want to set up the Busboy bus tracker on my Raspberry Pi. Clone the repo from https://github.com/stunglebungus/Busboy and run `pi_setup.py` to install everything on my Pi.

Here are my details:
- Pi SSH host: [e.g. busboy.local or IP address]
- Pi username: [e.g. pi]
- Pi password: [your password]
- TfNSW API key: [from opendata.transport.nsw.gov.au]
- My bus route number: [e.g. 370]
- My stop: [describe it in plain English, e.g. "King St after Newtown Station"]
- I want arrival times at: [a stop further along the route, e.g. "Railway Square"]

Once the setup script has finished, do the following steps in order:

1. Use the TfNSW Stop Finder API (with `type_sf=any`, filtering results for `type == "stop"`) to find the stop ID for my stop. Show me the results and confirm the right one with me before proceeding — make sure we pick the stop on the correct side of the road for my direction of travel.

2. Use the same API to find the stop ID for my arrival stop.

3. Update `/home/pi/busticker/config.py` on the Pi with my API key, stop ID, and route number.

4. Update `/home/pi/busticker/tracker.py` on the Pi:
   - Change `UTS_STOP_ID` to my arrival stop ID
   - Change the two `"Martin Place"` destination strings in `main()` to match my route's destination (check what the API returns as the destination name — don't guess)

5. Restart the service and check the logs to confirm it's pulling departures successfully.

**Important context for Claude:**
- All SSH/SFTP is done via paramiko (install with `pip install paramiko` if needed)
- `sudo` over SSH requires the Pi password piped via `echo PASSWORD | sudo -S` or NOPASSWD configured first
- The TfNSW Stop Finder API requires `type_sf=any` — `type_sf=stop` returns an error
- All route services share the same trip ID, so arrival stop matching is done by time window (15–50 min after departure), not by trip ID
- The TfNSW API returns times in UTC (`Z` suffix). Always call `.astimezone()` before `.strftime()` on parsed departure times — skipping this causes times to display ~10h behind local time
- Services with `isRealtimeControlled: true` show a LIVE badge and real estimated times; others show scheduled times only
- The tracker only logs errors — no output in `journalctl` means it's working correctly
- When printing Pi output to the Windows terminal, encode with `.encode('ascii', errors='replace').decode()` to handle the → character
