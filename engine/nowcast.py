"""Cleveland Fed inflation nowcasts: the expected core CPI and core PCE month-on-month figure before each release.

The Cleveland Fed publishes a daily nowcast of each month's inflation, free, with history since mid-2013
(https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting). Its month file is a list of charts,
one per target month; each holds the daily nowcasts and marks the day that month's CPI and PCE came out.
The engine uses the nowcast from the last day BEFORE each release as the expected figure, both to train the
model on past surprises and to measure a new release, so the two are always on the same footing.
"""
import datetime as dt
import json
import os
import re

import publicdata

URL = "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_month.json?sc_lang=en"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "nowcast.json")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MEASURES = {"core_cpi": ("cpi", "CPI"), "core_pce": ("pce", "PCE")}  # measure -> (engine kind, release marker)


def measure_of(name):
    n = name.lower()
    if "actual" in n or "core" not in n:
        return None
    return "core_cpi" if "cpi" in n else "core_pce" if "pce" in n else None


def _day(label, target):
    """'11/09' in the chart for target month 2026-10 -> 2026-11-09."""
    m, d = map(int, label.split("/"))
    y = target.year + (1 if m < target.month - 6 else 0) - (1 if m > target.month + 6 else 0)
    return dt.date(y, m, d)


def parse(charts):
    """-> (past, latest, daily)
    past:   {(kind, release date): nowcast the day before}, where the chart marks the release
    latest: {(kind, 'YYYY-MM' target month): latest nowcast}
    daily:  {(kind, 'YYYY-MM'): [(date, nowcast)]}, every day published, for releases the chart doesn't mark
            (the monthly charts stop before PCE comes out, so PCE is matched to its release date by the caller)"""
    past, latest, daily = {}, {}, {}
    for ch in charts:
        sub = ((ch.get("chart") or {}).get("subcaption") or "").strip()
        mm = re.fullmatch(r"(\d{4})-(\d{1,2})", sub)
        if not mm:
            continue
        target = dt.date(int(mm[1]), int(mm[2]), 1)
        cats = (ch.get("categories") or [{}])[0].get("category") or []
        days, releases = [], {}
        for c in cats:
            label = c.get("label", "")
            if c.get("vline"):
                rel = re.fullmatch(r"(CPI|PCE) ([A-Z][a-z]{2})", label)
                if rel and days and rel[2] == MON[target.month - 1]:
                    releases[rel[1]] = days[-1]  # the marker follows the release day's point
            elif re.fullmatch(r"\d{1,2}/\d{1,2}", label):
                days.append(_day(label, target))
        for ds in ch.get("dataset") or []:
            meas = measure_of(ds.get("seriesname", ""))
            if not meas:
                continue
            kind, marker = MEASURES[meas]
            vals = []
            for day, point in zip(days, ds.get("data") or []):
                try:
                    vals.append((day, float(point.get("value"))))
                except (TypeError, ValueError):
                    pass
            if not vals:
                continue
            daily[(kind, target.strftime("%Y-%m"))] = [(d.isoformat(), v) for d, v in vals]
            rel = releases.get(marker)
            if rel:
                before = [v for d, v in vals if d < rel]
                if before:
                    past[(kind, rel.isoformat())] = before[-1]
            latest[(kind, target.strftime("%Y-%m"))] = vals[-1][1]
    return past, latest, daily


def before(daily, kind, month, release_date):
    """The last nowcast for `month` published before `release_date`, or None."""
    vals = [v for d, v in daily.get((kind, month), []) if d < release_date]
    return vals[-1] if vals else None


def load(log=print):
    """Fetch and parse, falling back to the last good copy in engine/cache/nowcast.json."""
    try:
        charts = json.loads(publicdata.download(URL, max_bytes=40 * 1024 * 1024))
        past, latest, daily = parse(charts)
        if len(past) < 50:
            raise ValueError(f"only {len(past)} past nowcasts parsed")
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as fh:
            json.dump({"past": {f"{k}|{d}": v for (k, d), v in sorted(past.items())},
                       "latest": {f"{k}|{m}": v for (k, m), v in sorted(latest.items())},
                       "daily": {f"{k}|{m}": v for (k, m), v in sorted(daily.items())}}, fh, separators=(",", ":"))
        return past, latest, daily
    except Exception as e:
        log(f"nowcast: Cleveland Fed file unavailable ({e}); using the cached copy")
    try:
        c = json.load(open(CACHE))
        split = lambda d: {tuple(k.split("|")): v for k, v in d.items()}
        return split(c.get("past", {})), split(c.get("latest", {})), {k: [tuple(x) for x in v] for k, v in split(c.get("daily", {})).items()}
    except (OSError, ValueError):
        return {}, {}, {}
