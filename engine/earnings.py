"""Earnings dates for the companies that matter most to the Nasdaq-100.

Two sources, no AI and no guessing:
  1. earnings_seed.json: dates a company has itself announced (hand-checked, with a link).
  2. Nasdaq's public earnings calendar, fetched for the next few weeks, for the watchlist only.
A company's own announcement always wins over the calendar. If the calendar can't be reached the
engine keeps whatever it had before; it never invents a date.
"""
import datetime as dt
import json
import os
import time
import urllib.request

from source_health import record

# ticker: (name, tier). "mega" = the heaviest Nasdaq-100 weights, "notable" = other big movers of the index.
WATCH = {
    "AAPL": ("Apple", "mega"), "MSFT": ("Microsoft", "mega"), "NVDA": ("NVIDIA", "mega"), "AMZN": ("Amazon", "mega"),
    "GOOGL": ("Alphabet", "mega"), "META": ("Meta", "mega"), "TSLA": ("Tesla", "mega"), "AVGO": ("Broadcom", "mega"),
    "NFLX": ("Netflix", "notable"), "COST": ("Costco", "notable"), "WMT": ("Walmart", "notable"), "AMD": ("AMD", "notable"),
    "ORCL": ("Oracle", "notable"), "ADBE": ("Adobe", "notable"), "CRM": ("Salesforce", "notable"), "MU": ("Micron", "notable"),
    "PLTR": ("Palantir", "notable"), "QCOM": ("Qualcomm", "notable"), "CSCO": ("Cisco", "notable"), "INTC": ("Intel", "notable"),
    "AMAT": ("Applied Materials", "notable"), "PANW": ("Palo Alto Networks", "notable"), "TXN": ("Texas Instruments", "notable"),
    "ASML": ("ASML", "notable"),
}
TIMES = {"BMO": "07:00", "AMC": "16:05"}
NOTE = {"BMO": "Results scheduled before the U.S. stock market opens.",
        "AMC": "Results scheduled after the U.S. stock market closes.",
        "": "Time not published yet."}
SRC_CO, SRC_NQ = "Company announcement", "Nasdaq earnings calendar"
URL = "https://api.nasdaq.com/api/calendar/earnings?date={d}"
HEAD = {"User-Agent": "Mozilla/5.0 (compatible; DisplaceEngine/1.0)", "Accept": "application/json"}


def fetch_day(day):
    """Rows of Nasdaq's calendar for one date, or None if it couldn't be read."""
    rows = None
    try:
        req = urllib.request.Request(URL.format(d=day.isoformat()), headers=HEAD)
        with urllib.request.urlopen(req, timeout=8) as r:
            body = json.load(r)
        data = (body or {}).get("data")
        if isinstance(data, dict) and "rows" in data:
            values = data["rows"]
            rows = [] if values is None else values if isinstance(values, list) else None
    except Exception:
        pass
    record("nasdaqCalendar", rows is not None)
    return rows


def session_of(raw):
    raw = (raw or "").lower()
    return "BMO" if "pre" in raw else "AMC" if ("after" in raw or "post" in raw) else ""


def event(tkr, day, sess, status, src, period="", url=""):
    name, tier = WATCH[tkr]
    e = {"id": f"{day.replace('-', '')}-earn-{tkr.lower()}", "date": day, "time": TIMES.get(sess, ""),
         "title": f"{name} ({tkr}) earnings" + (f" · {period}" if period else ""), "cur": "USD", "impact": "earnings",
         "src": src, "tier": tier, "status": status, "session": sess,
         "note": NOTE[sess] + (" Date confirmed by the company." if status == "confirmed" else " Date from the Nasdaq calendar. Check the company's investor relations page for changes.")}
    if url:
        e["url"] = url
    return e


def build(seed, today, days=35, fetch=fetch_day, pause=0.25, previous=()):
    """Return (events, ok). `previous` are the events from the last run, kept when the calendar is unreachable."""
    out, fetched = {}, set()
    failed_in_a_row = 0
    incomplete = False
    d = today
    for _ in range(days):
        if d.weekday() < 5:
            day = d.isoformat()
            rows = fetch(d)
            if rows is None:
                incomplete = True
                failed_in_a_row += 1
                if failed_in_a_row >= 3:
                    break
            else:
                failed_in_a_row = 0
                fetched.add(day)
                for r in rows:
                    t = (r.get("symbol") or "").upper()
                    if t in WATCH:
                        out[(t, day)] = event(t, day, session_of(r.get("time")), "scheduled", SRC_NQ, period=_period(r))
            if pause:
                time.sleep(pause)
        d += dt.timedelta(days=1)
    # Preserve prior dates on any day the provider could not refresh.
    end = (today + dt.timedelta(days=days)).isoformat()
    for e in previous:
        if e.get("status") != "confirmed" and today.isoformat() <= e["date"] < end and e["date"] not in fetched:
            out[(e["id"].split("-earn-")[1].upper(), e["date"])] = e
    for s in seed:
        t = s["t"].upper()
        if t not in WATCH:
            continue
        for k in [k for k in out if k[0] == t and abs((dt.date.fromisoformat(k[1]) - dt.date.fromisoformat(s["date"])).days) <= 4]:
            del out[k]
        out[(t, s["date"])] = event(t, s["date"], s.get("session", ""), "confirmed", SRC_CO, s.get("period", ""), s.get("url", ""))
        if s.get("time"):
            out[(t, s["date"])]["time"] = s["time"]
    keep_from = (today - dt.timedelta(days=10)).isoformat()
    ok = bool(fetched) and not incomplete
    return sorted((e for e in out.values() if e["date"] >= keep_from), key=lambda e: (e["date"], e["time"] or "99:99", e["title"])), ok


def _period(r):
    q = (r.get("fiscalQuarterEnding") or "").strip()
    return f"quarter ending {q.replace('/', ' ')}" if q else ""


def run(root, today, log=print):
    seed = json.load(open(os.path.join(root, "engine", "earnings_seed.json"), encoding="utf-8")).get("events", [])
    path = os.path.join(root, "site", "data", "calendar", "earnings.json")
    prev = []
    if os.path.exists(path):
        try:
            prev = json.load(open(path, encoding="utf-8")).get("events", [])
        except Exception:
            prev = []
    events, ok = build(seed, today, previous=prev)
    if not ok:
        log("earnings: Nasdaq calendar unavailable; kept earlier dates and company-confirmed dates")
    body = {"events": events}
    if prev != events or not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"updated": today.isoformat(), **body}, fh, indent=1, ensure_ascii=False)
        log(f"earnings: {len(events)} dates saved")
    return events
