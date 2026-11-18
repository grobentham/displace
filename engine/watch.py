"""Data watchdog: flags a major release whose figure still hasn't been published hours after it came out.

Writes engine/MISSING (the workflow opens a GitHub issue from it) or removes it when everything is in.
A missing figure means a source changed or broke, which no other check would notice, because the calendar
itself still passes every quality check."""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NY = ZoneInfo("America/New_York")
WATCHED = ("cpi", "nfp", "retail", "pce", "gdp", "ppi", "claims")
GRACE = dt.timedelta(hours=3)
LOOKBACK = dt.timedelta(days=7)


def missing(events, kind_of, now):
    out = []
    for e in events:
        if kind_of(e) not in WATCHED or not e.get("time") or e.get("actual"):
            continue
        h, m = map(int, e["time"].split(":"))
        at = dt.datetime.combine(dt.date.fromisoformat(e["date"]), dt.time(h, m), NY)
        if now - LOOKBACK < at < now - GRACE:
            out.append(e)
    return out


def main():
    sys.path.insert(0, HERE)
    import engine as E
    now = E.NOW
    with open(os.path.join(ROOT, "site", "data", "calendar", "events.json")) as fh:
        events = json.load(fh).get("events", [])
    gone = missing(events, E.kind_of, now)
    path = os.path.join(HERE, "MISSING")
    if gone:
        with open(path, "w") as fh:
            fh.write("These releases came out more than three hours ago but the engine has no figure for them yet. "
                     "A data source has probably changed or is down. Check the latest engine run log.\n\n")
            for e in gone:
                fh.write(f"- {e['title']} ({e['date']} {e['time']} NY, source: {e.get('src', '?')})\n")
        print(f"watch: {len(gone)} release(s) missing figures")
    elif os.path.exists(path):
        os.remove(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
