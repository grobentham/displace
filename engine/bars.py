"""Intraday gold and Nasdaq-100 futures bars, archived so the history keeps growing.

Yahoo's free chart API only serves the last ~730 days of hourly bars and ~60 days of 5-minute bars, so every
run merges what it serves into engine/cache/bars/<market>_<interval>.json (committed). Hourly bars start in
mid-2024, 5-minute bars in November 2026; both grow from there.
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
INTERVALS = {"1h": "730d", "5m": "60d"}
REFRESH = dt.timedelta(minutes=50)


def _path(m, interval="1h"):
    return os.path.join(CACHE_DIR, f"{m}_{interval}.json")


def _load(m, interval="1h"):
    try:
        return json.load(open(_path(m, interval)))
    except (OSError, ValueError):
        return {"fetched": "", "bars": {}}


def _download(symbol, interval="1h", tries=3):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={INTERVALS[interval]}&interval={interval}"
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                res = json.load(r)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            out = {}
            vols = q.get("volume") or [None] * len(res["timestamp"])
            for t, o, h, lo, c, v in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], vols):
                if o and h and lo and c:
                    out[dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec="minutes")] = [o, h, lo, c, v or 0]
            return out
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def sync(now, log=print, download=_download):
    """Merge the latest bars into the archive (at most about once an hour per interval)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    for interval in INTERVALS:
        for m, sym in SYMBOLS.items():
            c = _load(m, interval)
            try:
                if now - dt.datetime.fromisoformat(c["fetched"]) < REFRESH:
                    continue
            except (KeyError, ValueError):
                pass
            try:
                got = download(sym, interval) if download is _download else download(sym)
            except Exception as e:
                log(f"bars: {m} {interval} bars unavailable ({e!r}); using the archive")
                continue
            if len(got) < 100:
                continue
            # the newest bar may still be forming: always replace it with the latest download
            c["bars"].update(got)
            c["fetched"] = now.isoformat(timespec="minutes")
            with open(_path(m, interval), "w") as fh:
                json.dump({"fetched": c["fetched"], "bars": dict(sorted(c["bars"].items()))}, fh, separators=(",", ":"))


def load(m, interval="1h"):
    """[(start time NY, open, high, low, close)] oldest first."""
    return [(dt.datetime.fromisoformat(t).astimezone(NY), *v[:4]) for t, v in sorted(_load(m, interval)["bars"].items())]


def export(site_data, markets=("nq",), log=print):
    """Publish the archive for the site's MNQ backtester: site/data/bars/<market>-<interval>.json."""
    out_dir = os.path.join(site_data, "bars")
    os.makedirs(out_dir, exist_ok=True)
    for m in markets:
        for interval in INTERVALS:
            c = _load(m, interval)
            rows = [[int(dt.datetime.fromisoformat(t).timestamp()), *[round(x, 2) for x in v[:4]], int(v[4]) if len(v) > 4 else 0]
                    for t, v in sorted(c["bars"].items())]
            if len(rows) < 100:
                continue
            doc = {"market": m, "symbol": "NQ=F" if m == "nq" else m, "interval": interval, "source": "Yahoo Finance",
                   "updated": c.get("fetched", ""), "rows": rows}
            with open(os.path.join(out_dir, f"{m}-{interval}.json"), "w") as fh:
                json.dump(doc, fh, separators=(",", ":"))
        log(f"bars: published {m} bars for the backtester")


def fetched(m, interval="1h"):
    v = _load(m, interval).get("fetched")
    return dt.datetime.fromisoformat(v) if v else None
