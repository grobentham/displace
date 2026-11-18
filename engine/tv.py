"""US economic releases with the market consensus, from TradingView's free economic calendar (no key).

https://economic-calendar.tradingview.com/events gives, for every US release since 2010, the figure as first
reported ("actual") and the consensus forecast the market expected. That is the surprise markets trade on, so
the news-outcome model is built on it. Each month is cached in engine/cache/tv/YYYY-MM.json (committed); the
last, current and next month are refreshed every run, older months are read once.

surprise z for one release = (actual - consensus) / typical size of that report's surprises, where the typical
size is a robust spread of the surprises BEFORE it (walk-forward, no peeking). Reports with several headline
figures (CPI: core and headline; payrolls: jobs, unemployment, wages) are combined into one composite, the
headline counting double, each signed so that positive always means "hotter / stronger than expected".
"""
import datetime as dt
import json
import os
import statistics
import time
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache", "tv")
NY = ZoneInfo("America/New_York")
URL = "https://economic-calendar.tradingview.com/events?from={a}T00:00:00.000Z&to={b}T00:00:00.000Z&countries=US"
HEADERS = {"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
START = dt.date(2010, 1, 1)
MIN_HIST = 12
CLIP = 4.0

# kind -> [(TradingView title, sign, weight)]; sign makes "positive = hotter / stronger than expected"
REPORTS = {
    "cpi": [("Core Inflation Rate MoM", 1, 2), ("Inflation Rate MoM", 1, 1)],
    "ppi": [("PPI MoM", 1, 2), ("Core PPI MoM", 1, 1)],
    "pce": [("Core PCE Price Index MoM", 1, 2), ("PCE Price Index MoM", 1, 1)],
    "nfp": [("Non Farm Payrolls", 1, 2), ("Unemployment Rate", -1, 1), ("Average Hourly Earnings MoM", 1, 1)],
    "retail": [("Retail Sales MoM", 1, 2), ("Retail Sales Control Group", 1, 1), ("Retail Sales Ex Autos MoM", 1, 1)],
    "claims": [("Initial Jobless Claims", -1, 1)],
    "jolts": [("JOLTs Job Openings", 1, 1)],
    "adp": [("ADP Employment Change", 1, 1)],
    "gdp": [("GDP Growth Rate QoQ Adv", 1, 1)],
    "durables": [("Durable Goods Orders MoM", 1, 2), ("Durable Goods Orders Ex Transp MoM", 1, 1)],
    "ism-m": [("ISM Manufacturing PMI", 1, 1)],
    "ism-s": [("ISM Services PMI", 1, 1)],
    "philly": [("Philadelphia Fed Manufacturing Index", 1, 1)],
    "empire": [("NY Empire State Manufacturing Index", 1, 1)],
    "umich": [("Michigan Consumer Sentiment Prel", 1, 1), ("Michigan Consumer Sentiment Final", 1, 1)],
    "conf": [("CB Consumer Confidence", 1, 1)],
    "homes": [("New Home Sales", 1, 1)],
    "fomc": [("Interest Rate", 1, 1)],
}
# The Fed's decision rarely differs from the consensus, so its surprises can't set their own scale:
# a quarter-point surprise counts as one typical surprise.
FIXED_SCALE = {"Interest Rate": 0.25}
CACHE_VERSION = 2  # bump when REPORTS gains titles, so older months are downloaded again
GROUPS = {"inflation": ("cpi", "ppi", "pce"), "labor": ("nfp", "claims", "jolts", "adp"),
          "activity": ("retail", "durables", "gdp", "ism-m", "ism-s", "philly", "empire"),
          "sentiment": ("umich", "conf"), "housing": ("homes",), "fed": ("fomc",)}
GROUP_OF = {k: g for g, ks in GROUPS.items() for k in ks}
TITLES = {t: (k, s, w) for k, comps in REPORTS.items() for t, s, w in comps}
# kept for showing the consensus on the calendar, not used by the model
DISPLAY = {"GDP Growth Rate QoQ 2nd Est", "GDP Growth Rate QoQ Final"}


def _months(a, b):
    d = dt.date(a.year, a.month, 1)
    while d <= b:
        n = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, n
        d = n


def _fetch(a, b, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL.format(a=a, b=b), headers=HEADERS), timeout=40) as r:
                return json.load(r)["result"]
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def _compact(raw):
    out = []
    for e in raw:
        if (e.get("title") in TITLES or e.get("title") in DISPLAY) and e.get("date"):
            out.append({"t": e["title"], "d": e["date"], "a": e.get("actual"), "f": e.get("forecast"),
                        "p": e.get("previous"), "u": e.get("unit"), "s": e.get("scale")})
    return out


def sync(today, log=print, fetch=_fetch, budget=240):
    """Make sure every month from 2010 to next month is cached. Returns the number of months downloaded."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    fresh_from = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    end = (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    t0, n, failed = time.monotonic(), 0, 0
    for a, b in _months(START, end):
        path = os.path.join(CACHE_DIR, a.strftime("%Y-%m") + ".json")
        if os.path.exists(path) and a < fresh_from and _version(path) >= CACHE_VERSION:
            continue
        if time.monotonic() - t0 > budget:
            log("tv: download budget used; the rest loads next run")
            break
        try:
            rows = _compact(fetch(a.isoformat(), b.isoformat()))
        except Exception as e:
            failed += 1
            log(f"tv: {a:%Y-%m} unavailable ({e!r})")
            if failed >= 3:
                break
            continue
        with open(path, "w") as fh:
            json.dump({"v": CACHE_VERSION, "rows": rows}, fh, separators=(",", ":"))
        n += 1
    return n


def _version(path):
    try:
        c = json.load(open(path))
    except (OSError, ValueError):
        return 0
    return c.get("v", 1) if isinstance(c, dict) else 1


def _rows(c):
    return c.get("rows", []) if isinstance(c, dict) else c


def raw_events():
    out = []
    if os.path.isdir(CACHE_DIR):
        for f in sorted(os.listdir(CACHE_DIR)):
            if f.endswith(".json"):
                try:
                    out += _rows(json.load(open(os.path.join(CACHE_DIR, f))))
                except ValueError:
                    pass
    seen, uniq = set(), []
    for e in out:
        key = (e["t"], e["d"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return sorted(uniq, key=lambda e: e["d"])


def _num(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def releases(raw=None):
    """[{when, kind, group, z, comps}] oldest first. z is None until the figure is out (or if no consensus).
    when is a New York datetime."""
    raw = raw if raw is not None else raw_events()
    hist = {}  # title -> past surprises
    slots = {}  # (kind, when) -> {"parts": [(z, w)], "comps": [...]}
    for e in raw:
        if e["t"] not in TITLES:
            continue
        k, sign, w = TITLES[e["t"]]
        when = dt.datetime.fromisoformat(e["d"].replace("Z", "+00:00")).astimezone(NY)
        a, f = _num(e["a"]), _num(e["f"])
        slot = slots.setdefault((k, when), {"parts": [], "comps": []})
        slot["comps"].append({"title": e["t"], "actual": a, "forecast": f, "previous": _num(e.get("p")),
                              "unit": e.get("u"), "scale": e.get("s"), "weight": w})
        if a is None or f is None:
            continue
        past = hist.setdefault(e["t"], [])
        sc = FIXED_SCALE.get(e["t"])
        if sc is None and len(past) >= MIN_HIST:
            sc = statistics.median(abs(x) for x in past) * 1.4826
        if sc:
            slot["parts"].append((max(-CLIP, min(CLIP, sign * (a - f) / sc)), w))
        past.append(a - f)
    out = []
    for (k, when), s in sorted(slots.items(), key=lambda x: x[0][1]):
        z = sum(z * w for z, w in s["parts"]) / sum(w for _, w in s["parts"]) if s["parts"] else None
        rel = {"when": when, "kind": k, "group": GROUP_OF[k], "z": z, "comps": s["comps"]}
        if k == "fomc" and s["comps"]:
            c = s["comps"][0]
            if c["actual"] is not None and c["previous"] is not None:
                d = c["actual"] - c["previous"]
                rel["decision"] = "hike" if d > 0.01 else "cut" if d < -0.01 else "hold"
        out.append(rel)
    return out


def scale_now(title, raw=None):
    """Typical surprise size for a report today (for turning a live print into z)."""
    raw = raw if raw is not None else raw_events()
    s = [_num(e["a"]) - _num(e["f"]) for e in raw if e["t"] == title and _num(e["a"]) is not None and _num(e["f"]) is not None]
    return statistics.median(abs(x) for x in s) * 1.4826 if len(s) >= MIN_HIST else None
