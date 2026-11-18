"""Daily gold closes (XAU/USD). FRED no longer carries a gold price, so this reads free public sources:
Stooq's daily CSV first, Yahoo's chart API (COMEX gold futures) as a fallback. Results are cached in
engine/cache/gold.json so each run only needs the latest days."""
import datetime as dt
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "gold.json")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}


def _fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def stooq():
    txt = _fetch("https://stooq.com/q/d/l/?s=xauusd&i=d")
    out = {}
    for line in txt.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5:
            try:
                out[p[0]] = float(p[4])
            except ValueError:
                pass
    return out


def yahoo():
    d = json.loads(_fetch("https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=15y&interval=1d"))
    r = d["chart"]["result"][0]
    out = {}
    for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
        if c:
            out[dt.datetime.utcfromtimestamp(t).date().isoformat()] = float(c)
    return out


SOURCES = [("Stooq XAU/USD", stooq), ("Yahoo COMEX gold", yahoo)]


def gold(start, log=print):
    """[(date, close)] from `start`, or None. Never raises."""
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {"source": "", "closes": {}}
    got, src = None, ""
    for name, fn in SOURCES:
        try:
            got = fn()
            if got and len(got) > 50:
                src = name
                break
        except Exception as e:  # network, format, rate limit
            log(f"gold source {name} failed: {e}")
            got = None
    if got:
        if cache.get("source") and cache["source"] != src:
            cache["closes"] = {}  # don't splice two different gold prices together
        cache["closes"].update(got)
        cache["source"] = src
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as fh:
            json.dump(cache, fh, separators=(",", ":"), sort_keys=True)
    closes = cache.get("closes") or {}
    rows = sorted((d, v) for d, v in closes.items() if d >= start)
    return (rows, cache.get("source", "")) if len(rows) > 50 else (None, "")
