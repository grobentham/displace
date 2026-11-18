"""Daily closes for the markets the direction engine studies, from free public sources (no API keys).

  gold  COMEX gold futures (GC=F) from Yahoo
  nq    Nasdaq-100 index (^NDX) from Yahoo; FRED's public NASDAQ100 series as a fallback

Closes are cached in engine/cache/prices/<market>.json, which the workflow commits, so a run that cannot reach
any source still has the full history and only the latest days are missing. Two different gold prices (spot vs
futures) are never spliced together; the Nasdaq-100 index is the same number at both sources, so it is merged.
"""
import datetime as dt
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache", "prices")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
REFRESH_HOURS = 4
_TRIED = set()  # markets already refreshed (or failed) in this run


def _fetch(url, timeout=25, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(8 * 1024 * 1024).decode("utf-8", "replace")
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def parse_stooq(txt):
    out = {}
    for line in txt.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 5:
            try:
                dt.date.fromisoformat(p[0])
                v = float(p[4])
            except ValueError:
                continue
            if v > 0:
                out[p[0]] = v
    return out


def parse_yahoo(txt):
    d = json.loads(txt)
    r = d["chart"]["result"][0]
    tz = r.get("meta", {}).get("gmtoffset", 0)
    out = {}
    for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]):
        if c:
            out[dt.datetime.utcfromtimestamp(t + tz).date().isoformat()] = float(c)
    return out


def stooq(symbol):
    return lambda: parse_stooq(_fetch(f"https://stooq.com/q/d/l/?s={symbol}&i=d"))


def yahoo(symbol):
    return lambda: parse_yahoo(_fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=20y&interval=1d"))


def fred_csv(series):
    def get():
        out = {}
        for line in _fetch(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd=2006-01-01").splitlines()[1:]:
            d, _, v = line.partition(",")
            try:
                if float(v) > 0:
                    out[d] = float(v)
            except ValueError:
                pass
        return out
    return get


MARKETS = {
    # name: (sources [(label, fn)], splice: may different sources be merged into one history)
    # Stooq now answers automated requests with a browser check, so it is no longer used.
    "gold": ([("Yahoo COMEX gold", yahoo("GC=F"))], False),
    "nq": ([("Yahoo Nasdaq-100", yahoo("%5ENDX")), ("FRED Nasdaq-100", fred_csv("NASDAQ100"))], True),
}


def _load(name):
    try:
        with open(os.path.join(CACHE_DIR, name + ".json")) as fh:
            c = json.load(fh)
        if isinstance(c.get("closes"), dict):
            return c
    except (OSError, ValueError):
        pass
    return {"source": "", "fetched": "", "closes": {}}


def _save(name, cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, name + ".json"), "w") as fh:
        json.dump(cache, fh, separators=(",", ":"), sort_keys=True)


def closes(name, start, now=None, log=print, sources=None):
    """([(date, close)] from `start`, source label), or (None, "") when there's no usable history. Never raises."""
    srcs, splice = MARKETS[name]
    srcs = sources or srcs
    now = now or dt.datetime.now(dt.timezone.utc)
    cache = _load(name)
    fresh = False
    try:
        fresh = now - dt.datetime.fromisoformat(cache["fetched"]) < dt.timedelta(hours=REFRESH_HOURS)
    except (TypeError, ValueError):
        pass
    if not fresh and name not in _TRIED:
        _TRIED.add(name)
        for label, fn in srcs:
            try:
                got = fn()
            except Exception as e:  # network, format, rate limit
                log(f"prices: {name} source {label} failed: {e}")
                continue
            if not got or len(got) < 50:
                log(f"prices: {name} source {label} returned too little data")
                continue
            if cache["source"] and cache["source"] != label and not splice:
                cache["closes"] = {}
            cache["closes"].update(got)
            cache["source"] = label
            cache["fetched"] = now.isoformat(timespec="minutes")
            _save(name, cache)
            break
    rows = sorted((d, v) for d, v in cache["closes"].items() if d >= start)
    return (rows, cache["source"]) if len(rows) > 50 else (None, "")


def gold(start, log=print):
    return closes("gold", start, log=log)


def nq(start, log=print):
    return closes("nq", start, log=log)
