import time
from datetime import datetime
import requests
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in13_V4
import config

FONT_DIR    = "/usr/share/fonts/truetype/dejavu/"
UTS_STOP_ID = "G200723"
UTS_MIN_TRAVEL = 15
UTS_MAX_TRAVEL = 50

# Column x positions (px), tuned to measured font metrics
COL_MIN  =   4   # minutes-until  bold12  max 29px wide
COL_TIME =  40   # departure time reg12   35px wide
COL_LIVE =  82   # LIVE badge             28px wide
COL_DLY  = 114   # delay text    bold9    ~25px wide
ROW_H    =  22   # px per departure row


def fetch(stop_id):
    params = {
        "outputFormat": "rapidJSON",
        "coordOutputFormat": "EPSG:4326",
        "mode": "direct",
        "type_dm": "stop",
        "name_dm": stop_id,
        "departureMonitorMacro": "true",
        "TfNSWDM": "true",
        "version": "10.2.1.42",
    }
    r = requests.get(
        "https://api.transport.nsw.gov.au/v1/tp/departure_mon",
        params=params,
        headers={"Authorization": f"apikey {config.API_KEY}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def parse(data, dest_filter):
    results = []
    for ev in data.get("stopEvents", []):
        t = ev.get("transportation", {})
        if t.get("number") != config.ROUTE:
            continue
        if dest_filter not in t.get("destination", {}).get("name", ""):
            continue
        planned_s = ev.get("departureTimePlanned")
        if not planned_s:
            continue
        try:
            planned_dt  = datetime.fromisoformat(planned_s)
            est_s       = ev.get("departureTimeEstimated")
            dep_dt      = datetime.fromisoformat(est_s) if est_s else planned_dt
            is_live     = ev.get("isRealtimeControlled") is True
            results.append({"dep": dep_dt, "planned": planned_dt, "live": is_live})
        except ValueError:
            continue
    results.sort(key=lambda x: x["dep"])
    return results


def match_uts(dep_dt, uts_times):
    for u in uts_times:
        diff = (u - dep_dt).total_seconds() / 60
        if UTS_MIN_TRAVEL <= diff <= UTS_MAX_TRAVEL:
            return u
    return None


def badge(draw, x, y, text, font):
    """Inverted (white-on-black) pill badge. Returns right edge x."""
    bb  = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px, py = 3, 2
    x2 = x + tw + px * 2
    y2 = y + th + py * 2
    draw.rectangle([x, y, x2, y2], fill=0)
    draw.text((x + px, y + py), text, font=font, fill=255)
    return x2


def render(epd, departures, uts_times, now):
    fb = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 14)  # header
    mb = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf", 12)  # minutes
    mr = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf",      12)  # times
    sr = ImageFont.truetype(FONT_DIR + "DejaVuSans.ttf",      10)  # UTS / date
    sb = ImageFont.truetype(FONT_DIR + "DejaVuSans-Bold.ttf",  9)  # badge / delay

    w, h = epd.height, epd.width   # 250 x 122  (landscape)
    img  = Image.new("1", (w, h), 255)
    d    = ImageDraw.Draw(img)

    # ── Header ─────────────────────────────────────────────────────
    title    = f"{config.ROUTE} → Martin Place"
    time_str = now.strftime("%H:%M")
    tw = d.textbbox((0, 0), time_str, font=fb)[2]
    d.text((4, 2),          title,    font=fb, fill=0)
    d.text((w - tw - 4, 2), time_str, font=fb, fill=0)

    d.text((4, 18), now.strftime("%a %-d %b %Y"), font=sr, fill=0)

    # Solid divider
    d.line([(0, 29), (w, 29)], fill=0, width=1)

    # ── Rows ────────────────────────────────────────────────────────
    y = 32

    if not departures:
        d.text((4, y + 6), "No departures found", font=mr, fill=0)
    else:
        for dep in departures[:4]:
            dep_dt  = dep["dep"]
            plan_dt = dep["planned"]
            is_live = dep["live"]
            mins    = int((dep_dt - now).total_seconds() / 60)
            delay   = round((dep_dt - plan_dt).total_seconds() / 60)

            due_str  = "Due" if mins <= 0 else f"{mins}m"
            time_str = dep_dt.astimezone().strftime("%H:%M")

            # Minutes-until  (bold, left)
            d.text((COL_MIN,  y + 6), due_str,  font=mb, fill=0)
            # Departure time (regular)
            d.text((COL_TIME, y + 6), time_str, font=mr, fill=0)

            # LIVE badge + delay
            if is_live:
                rx = badge(d, COL_LIVE, y + 5, "LIVE", sb)
                if delay >= 2:
                    d.text((rx + 3, y + 7), f"+{delay}m", font=sb, fill=0)
                elif delay <= -1:
                    d.text((rx + 3, y + 7), f"{delay}m",  font=sb, fill=0)

            # UTS arrival  (right-aligned)
            uts = match_uts(dep_dt, uts_times)
            if uts:
                uts_str = f"→UTS {uts.astimezone().strftime('%H:%M')}"
                uts_w   = d.textbbox((0, 0), uts_str, font=sr)[2]
                d.text((w - uts_w - 4, y + 7), uts_str, font=sr, fill=0)

            # Row separator (light — only between rows, not after last)
            if y + ROW_H < h - 2:
                d.line([(COL_TIME, y + ROW_H - 1), (w, y + ROW_H - 1)], fill=0, width=1)

            y += ROW_H

    epd.init()
    epd.display(epd.getbuffer(img))
    epd.sleep()


def main():
    epd = epd2in13_V4.EPD()
    while True:
        try:
            now       = datetime.now().astimezone()
            deps      = parse(fetch(config.STOP_ID), "Martin Place")[:4]
            uts_times = [e["dep"] for e in parse(fetch(UTS_STOP_ID), "Martin Place")]
            render(epd, deps, uts_times, now)
        except Exception as e:
            print(f"Error: {e}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
