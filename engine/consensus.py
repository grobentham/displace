"""Consensus forecasts filled in automatically from ForexFactory's free weekly calendar feed.

The feed (https://nfs.faireconomy.media/ff_calendar_thisweek.json) lists this week's releases with the
market consensus. Each run copies the consensus onto the matching calendar event (same New York date and
time, matching report), unless a forecast was entered by hand in engine/forecasts.json, which always wins.
Every consensus seen is also kept in engine/cache/consensus.json, so a consensus history builds up over time.
"""
import datetime as dt
import json
import os
import re

import publicdata

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, "cache", "consensus.json")
SOURCE = "ForexFactory consensus"

# engine kind -> ForexFactory title pattern for the headline figure the calendar shows
TITLES = {
    "cpi": r"^Core CPI m/m$", "ppi": r"^PPI m/m$", "pce": r"^Core PCE Price Index m/m$",
    "nfp": r"^Non-Farm Employment Change$", "retail": r"^Retail Sales m/m$", "claims": r"^Unemployment Claims$",
    "gdp": r"^(Advance|Prelim|Final) GDP q/q$", "jolts": r"^JOLTS Job Openings$",
    "umich": r"^(Prelim|Revised) UoM Consumer Sentiment$", "durables": r"^Durable Goods Orders m/m$",
    "homes": r"^New Home Sales$", "adp": r"^ADP Non-Farm Employment Change$", "fomc": r"^Federal Funds Rate$",
    "ism-m": r"^ISM Manufacturing PMI$", "ism-s": r"^ISM Services PMI$", "conf": r"^CB Consumer Confidence$",
}


def normalise(kind, value):
    """FF writes '7.20M', '198K', '0.3%', '51.7'; keep it in the calendar's own style."""
    v = (value or "").strip()
    if not v:
        return ""
    if kind == "jolts" and v.endswith("M"):
        return f"{float(v[:-1]):.1f}M"
    if kind == "homes" and v.endswith("M"):
        return f"{float(v[:-1]) * 1000:.0f}K"
    return v


def match(events, feed, kind_of, tz):
    """[(event, kind, forecast, ff title)] for calendar events with a consensus in the feed."""
    by_slot = {}
    for e in events:
        k = kind_of(e)
        if k in TITLES and e.get("time"):
            by_slot.setdefault((e["date"], e["time"], k), e)
    out = []
    for item in feed:
        if item.get("country") != "USD" or not item.get("forecast"):
            continue
        try:
            when = dt.datetime.fromisoformat(item["date"]).astimezone(tz)
        except (KeyError, ValueError):
            continue
        title = item.get("title", "")
        for k, pat in TITLES.items():
            if re.search(pat, title):
                e = by_slot.get((when.date().isoformat(), when.strftime("%H:%M"), k))
                if e:
                    out.append((e, k, normalise(k, item["forecast"]), title))
                break
    return out


def apply(events, kind_of, tz, manual_ids=(), fetch=publicdata.download, log=print, now=None):
    """Fill forecasts in place. Returns how many events were updated."""
    try:
        feed = json.loads(fetch(URL))
    except Exception as e:
        log(f"consensus: ForexFactory feed unavailable ({e})")
        return 0
    try:
        archive = json.load(open(ARCHIVE))
    except (OSError, ValueError):
        archive = {}
    n = 0
    stamp = (now or dt.datetime.now(tz)).isoformat(timespec="minutes")
    for e, k, fc, title in match(events, feed, kind_of, tz):
        if not fc:
            continue
        rec = archive.setdefault(e["id"], {"kind": k, "date": e["date"], "title": title, "first": fc, "seen": stamp})
        rec["forecast"], rec["last"] = fc, stamp
        if e["id"] in manual_ids or (e.get("actual") and e.get("forecast")):
            continue  # a hand-entered forecast wins; a released figure keeps the consensus it was judged against
        if e.get("forecast") != fc or e.get("fsrc") != SOURCE:
            e["forecast"], e["fsrc"] = fc, SOURCE
            n += 1
    os.makedirs(os.path.dirname(ARCHIVE), exist_ok=True)
    with open(ARCHIVE, "w") as fh:
        json.dump(dict(sorted(archive.items())), fh, indent=1)
    if n:
        log(f"consensus: {n} forecast(s) filled from ForexFactory")
    return n
