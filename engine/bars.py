"""Hourly gold and Nasdaq-100 futures bars, archived so the intraday history keeps growing.

Yahoo's free chart API only serves the last ~730 days of hourly bars, so every run merges what it serves into
engine/cache/bars/<market>_1h.json (committed). The archive starts in mid-2024 and grows from there.
  gold  COMEX gold futures (GC=F)      nq  E-mini Nasdaq-100 futures (NQ=F)
"""
import datetime as dt
import json
import os
import time
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache", "bars")
NY = ZoneInfo("America/New_York")
SYMBOLS = {"gold": "GC%3DF", "nq": "NQ%3DF"}
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
REFRESH = dt.timedelta(hours=1)


def _path(m):
    return os.path.join(CACHE_DIR, f"{m}_1h.json")


def _load(m):
    try:
        return json.load(open(_path(m)))
    except (OSError, ValueError):
        return {"fetched": "", "bars": {}}


def _download(symbol, tries=3):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=730d&interval=1h"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                res = json.load(r)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            out = {}
            for t, o, h, lo, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"]):
                if o and h and lo and c:
                    out[dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="minutes")] = [o, h, lo, c]
            return out
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def sync(now, log=print, download=_download):
    """Merge the latest hourly bars into the archive (at most once an hour)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for m, sym in SYMBOLS.items():
        c = _load(m)
        try:
            if now - dt.datetime.fromisoformat(c["fetched"]) < REFRESH:
                continue
        except (KeyError, ValueError):
            pass
        try:
            got = download(sym)
        except Exception as e:
            log(f"bars: {m} hourly bars unavailable ({e!r}); using the archive")
            continue
        if len(got) < 100:
            continue
        # the newest bar may still be forming: always replace it with the latest download
        c["bars"].update(got)
        c["fetched"] = now.isoformat(timespec="minutes")
        with open(_path(m), "w") as fh:
            json.dump({"fetched": c["fetched"], "bars": dict(sorted(c["bars"].items()))}, fh, separators=(",", ":"))


def load(m):
    """[(start time NY, open, high, low, close)] oldest first."""
    return [(dt.datetime.fromisoformat(t).astimezone(NY), *v) for t, v in sorted(_load(m)["bars"].items())]
