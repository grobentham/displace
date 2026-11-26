"""Daily bias for eight futures markets: a tested probability of an up day, a volatility-model range, touch
probabilities, level odds, session statistics and calibration, each with its out-of-sample record.

Runs after the New York futures close (17:00 NY). Free data only: Yahoo daily futures candles since 2000, FRED
(implied volatility indices, credit spreads, real yields, the dollar, the 2-year yield) and the release calendar.

  direction   P(next close > today's close). Starts at the long-run base rate and moves only for signals that pass
              walk-forward testing: out-of-sample Brier skill with a Diebold-Mariano t above a Bonferroni bar for
              every signal tried across all markets, positive skill in both halves and the last three years, and
              (for the equity indices) positive skill in most of the other indices too. Calendar effects need a
              Bonferroni z across every market's calendar tests, on the same side in both halves and since 2019.
  range       a HAR model of the log daily range (yesterday, last week, last month, implied volatility, a news-day
              flag for the next session, Mondays), refit every year and compared with a 20-day average.
  touch       P(the next session reaches the close +/- 0.5, 1, 1.5, 2 forecast standard deviations), given how far
              today's high and low sit from the close; every input is out of sample.
  levels      P(trading above today's high / below today's low) from the close's distance to each.
  sessions    overnight vs New York session and an intraday momentum test (NQ and gold, hourly bars).

FRED values are used only once published: one day late, the trade-weighted dollar a week late. Direction is close
to close (Yahoo's daily futures opens are unreliable). Bad candles (high = low, prices at or below zero) are
dropped, and gold uses 2013 onward because its earlier Yahoo highs and lows cover the day session only.
Writes site/data/bias/current.json and log.json.
"""
import datetime as dt
import glob
import json
import math
import os
import re
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

import numpy as np

import exchange as X
import quant as Q
import publication as PUB

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
OUT = os.path.join(DATA, "bias", "current.json")
LOG = os.path.join(DATA, "bias", "log.json")
CACHE_DIR = os.path.join(HERE, "cache", "daily")
SERIES_DIR = os.path.join(HERE, "cache", "series")
TV_DIR = os.path.join(HERE, "cache", "tv")
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
SESSION_END = 17
FIRST_TEST_YEAR = 2006
LEAN = 0.02
FOMC_KNOWN_FROM = 2010
EVENTS_FROM = 2010
TOUCH_K = (0.5, 1.0, 1.5, 2.0)
WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# key: (Yahoo symbol, short name, full name, $ per point, micro $ per point, implied-vol series, decimals, group)
MARKETS = {
    "nq": ("NQ%3DF", "NQ", "Nasdaq-100 futures", 20, 2, "VXNCLS", 2, "equity"),
    "es": ("ES%3DF", "ES", "S&P 500 futures", 50, 5, "VIXCLS", 2, "equity"),
    "ym": ("YM%3DF", "YM", "Dow futures", 5, 0.5, "VIXCLS", 0, "equity"),
    "rty": ("RTY%3DF", "RTY", "Russell 2000 futures", 50, 5, "RVXCLS", 1, "equity"),
    "gold": ("GC%3DF", "Gold", "COMEX gold futures", 100, 10, "GVZCLS", 1, "gold"),
    "cl": ("CL%3DF", "Crude", "WTI crude oil futures", 1000, 100, "OVXCLS", 2, "oil"),
    "6e": ("6E%3DF", "Euro", "Euro FX futures", 125000, 12500, None, 5, "fx"),
    "btc": ("BTC%3DF", "Bitcoin", "CME bitcoin futures", 5, 0.1, None, 0, "crypto"),
}
START = {"gold": "2013-01-01"}  # earlier Yahoo gold candles: placeholders and day-session highs and lows
SERIES = ["VIXCLS", "VXNCLS", "RVXCLS", "GVZCLS", "OVXCLS", "VXVCLS", "BAMLH0A0HYM2", "DFII10", "DTWEXBGS", "DGS2"]
PUBLISH_LAG = {"DTWEXBGS": 7}  # calendar days before a value is public; everything else is out the next morning

PRICE_SIGNALS = {
    "mom20": "20-day momentum", "mom120": "6-month momentum", "trend200": "Distance from the 200-day average",
    "rev1": "Yesterday's move (reversal)", "clv": "Where the day closed in its range", "volreg": "Volatility regime",
}
CROSS_SIGNALS = {
    "iv_level": "Implied volatility vs its 1-year median", "iv_chg5": "5-day change in implied volatility",
    "term": "VIX vs 3-month VIX (term structure)", "hy5": "5-day change in high-yield credit spreads",
    "ry5": "5-day change in the 10-year real yield", "usd5": "5-day change in the dollar", "y2_5": "5-day change in the 2-year yield",
}
CROSS_FOR = {
    "equity": ["iv_level", "iv_chg5", "term", "hy5", "usd5", "y2_5"],
    "gold": ["iv_level", "iv_chg5", "ry5", "usd5", "y2_5"],
    "oil": ["iv_level", "iv_chg5", "hy5", "usd5"],
    "fx": ["usd5", "y2_5", "ry5"],
    "crypto": ["hy5", "usd5", "y2_5", "term"],
}
EVENTS = {"tom": "Turn of the month", "prefomc": "Day before a Fed decision", "fomc": "Fed decision day",
          "bigdown": "After a 2-sigma down day", "bigup": "After a 2-sigma up day",
          # registered 24 Nov 2026 (research/registered-2026-11-24.json), before testing
          "announce": "CPI, payrolls or Fed day", "preholiday": "Day before a market holiday"}
EVENT_FROM = {"prefomc": 2010, "fomc": 2010, "announce": 2010}   # first year each event's calendar is complete
EQUITY = ("nq", "es", "ym", "rty")
TIER1 = re.compile(r"\bCPI\b|Non-farm|FOMC rate decision", re.I)
TIER2 = re.compile(r"Retail sales|\bPCE\b|\bGDP\b|\bISM\b|\bPPI\b", re.I)


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- data

def _cache_path(m):
    return os.path.join(CACHE_DIR, f"{m}.json")


def load_cache(m):
    try:
        return json.load(open(_cache_path(m)))
    except (OSError, ValueError):
        return {"fetched": "", "days": {}}


def download(symbol, rng="max"):
    # an explicit span keeps daily candles; range=max quietly switches to monthly ones
    start = 946684800 if rng == "max" else int(time.time()) - 120 * 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={int(time.time()) + 86400}"
           f"&interval=1d")
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return parse(json.load(r))
        except Exception:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def parse(doc):
    """Yahoo daily futures candles -> {trading date: [open, high, low, close]}."""
    r = doc["chart"]["result"][0]
    off = r.get("meta", {}).get("gmtoffset", 0) or 0
    q = r["indicators"]["quote"][0]
    out = {}
    for t, o, h, lo, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if o is None or h is None or lo is None or c is None:
            continue
        d = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date()
        if d.weekday() >= 5:
            continue
        out[d.isoformat()] = [round(o, 6), round(max(h, o, c), 6), round(min(lo, o, c), 6), round(c, 6)]
    return out


def sync(m, now, fetch=download):
    c = load_cache(m)
    try:
        fresh = now - dt.datetime.fromisoformat(c["fetched"]) < dt.timedelta(minutes=50)
    except (KeyError, ValueError):
        fresh = False
    if not fresh:
        try:
            got = fetch(MARKETS[m][0], "max" if len(c["days"]) < 1000 else "3mo")
            if len(got) > 20:
                c["days"].update(got)  # the latest download wins, so a forming candle is replaced once it finishes
                c["fetched"] = now.isoformat(timespec="minutes")
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(_cache_path(m), "w") as fh:
                    json.dump({"fetched": c["fetched"], "days": dict(sorted(c["days"].items()))}, fh, separators=(",", ":"))
        except Exception as e:
            log(f"bias: {m} daily candles unavailable ({e!r}); using the archive")
    return c


IRON_BRAIN = "https://raw.githubusercontent.com/grobentham/iron-brain/quotes/quotes.json"
PATCHES = os.path.join(CACHE_DIR, "patches.json")


def iron_brain_sessions(url=IRON_BRAIN):
    """Clean daily candles from Iron Brain (its engine/sessions.py): NQ and gold Globex sessions rebuilt every 5 minutes
    from spike-filtered 1-minute bars. {} when unreachable: the Yahoo candles then stand as they are."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return (json.load(r).get("outlook") or {}).get("sessions") or {}
    except Exception as e:
        log(f"bias: Iron Brain sessions unavailable ({e!r})")
        return {}


def load_patches():
    try:
        return json.load(open(PATCHES))
    except (OSError, ValueError):
        return {}


def despike_days(m, days, ib, patches):
    """Clip a daily high or low that a bad print pushed past the clean session's (Yahoo took 23 Nov 2026's one-minute
    27,137 print as NQ's high; the real high was about 27,090). Only clips, never extends, by more than 0.1%, and only
    when the minute bars saw the same print and filtered it out. Fixes are kept in patches.json, because
    Yahoo's next download would bring the bad print back after Iron Brain's 5-day window has passed."""
    mp = patches.setdefault(m, {})
    for d, x in (ib.get(m) or {}).items():
        if d in days and x.get("complete") and x.get("full"):
            o, h, l, c = days[d]
            tol = 0.001 * c
            # only the bad print the filter removed: Yahoo's extreme equals the minute bars' raw one and the clean one is
            # well inside it. A candle that merely covers a different window (Yahoo's opens and lows differ) stays as is.
            nh = max(x["h"], o, c) if h - x["h"] > tol and abs(h - x.get("rawH", x["h"])) <= tol else h
            nl = min(x["l"], o, c) if x["l"] - l > tol and abs(l - x.get("rawL", x["l"])) <= tol else l
            if (nh, nl) != (h, l):
                mp[d] = [round(nh, 6), round(nl, 6), round(h, 6), round(l, 6)]   # clean high, low; Yahoo's high, low
    notes = []
    for d, (nh, nl, yh, yl) in mp.items():
        if d in days:
            o, h, l, c = days[d]
            days[d] = [o, min(h, nh), max(l, nl), c]
            if h > nh or l < nl:
                notes.append(f"{d}: Yahoo's " + " and ".join(
                    ([f"high {yh:,.2f}"] if yh > nh else []) + ([f"low {yl:,.2f}"] if yl < nl else []))
                    + " came from a bad print; using " + " and ".join(
                    ([f"{nh:,.2f}"] if yh > nh else []) + ([f"{nl:,.2f}"] if yl < nl else [])) + " (Iron Brain's spike-filtered minute bars)")
    return notes


def clean(m, rows):
    """Drop placeholder candles (high = low), prices at or below zero, and history before the market's usable start;
    then fold holiday candles into the next trading date (merge_holidays)."""
    start = START.get(m, "")
    return merge_holidays([(d, v) for d, v in rows if d >= start and v[1] > v[2] and min(v) > 0])


def merge_holidays(rows):
    """Yahoo publishes a daily candle for US holidays on which CME only trades a short, thin session until its early
    halt (Memorial Day, Independence Day, Labor Day...; 37 such NQ candles from 2015 to 2026). CME has no trading date
    for those days: that trading belongs to the next one. So each such candle is folded into the next trading date
    (its open, the wider high and low, the next day's close) instead of standing as a short day of its own; a holiday
    candle with no following candle is dropped. engine/exchange.py decides which dates trade."""
    out, carry = [], None
    for d, v in rows:
        if not X.is_trade_date(d):
            carry = [carry[0], max(carry[1], v[1]), min(carry[2], v[2]), v[3]] if carry else list(v)
            continue
        if carry:
            v = [carry[0], max(carry[1], v[1]), min(carry[2], v[2]), v[3]]
            carry = None
        out.append((d, v))
    return out


def fred_download(sid, start="1999-01-01"):
    import publicdata
    url = f"{publicdata.FRED}/graph/fredgraph.csv?id={sid}&cosd={start}"
    return [(d, v) for d, v, _ in publicdata.read_csv(publicdata.download(url), sid, start)]


def sync_series(sid, now, fetch=fred_download):
    """A FRED series cached in engine/cache/series/<id>.json (same format as series_store)."""
    path = os.path.join(SERIES_DIR, f"{sid}.json")
    try:
        c = json.load(open(path))
    except (OSError, ValueError):
        c = {"source": "", "fetched": "", "rows": []}
    try:
        stale = now - dt.datetime.fromisoformat(c.get("fetched") or "2000-01-01T00:00+00:00") > dt.timedelta(hours=4)
    except ValueError:
        stale = True
    early = not c["rows"] or c["rows"][0][0] > "2001-01-01"
    if stale or early:
        try:
            got = fetch(sid, "1999-01-01" if early else (now - dt.timedelta(days=120)).date().isoformat())
            if got and len(got) > 5:
                merged = {r[0]: [r[0], r[1], ""] for r in c["rows"]}
                merged.update({d: [d, v, ""] for d, v in got})
                c = {"source": f"FRED {sid}", "fetched": now.isoformat(timespec="minutes"), "rows": [merged[d] for d in sorted(merged)]}
                os.makedirs(SERIES_DIR, exist_ok=True)
                with open(path, "w") as fh:
                    json.dump(c, fh, separators=(",", ":"))
        except Exception as e:
            log(f"bias: {sid} unavailable ({e!r}); using the archive")
    return {r[0]: float(r[1]) for r in c["rows"] if r[1] is not None}


def finished(days, now_ny):
    cut = now_ny.date() if now_ny.hour >= SESSION_END else now_ny.date() - dt.timedelta(days=1)
    return [(d, v) for d, v in sorted(days.items()) if dt.date.fromisoformat(d) <= cut]


def settled_rows(market, cache, minute_sessions, now):
    """A Yahoo daily row can switch to the new session after 18:00 while keeping today's date."""
    now_ny = now.astimezone(NY)
    today = now_ny.date().isoformat()
    session = X.session(market, today)
    days = dict(finished(cache["days"], now_ny))
    if session and session["close"] and now >= session["close"] and today in cache["days"]:
        days[today] = cache["days"][today]
    try:
        fetched = dt.datetime.fromisoformat(cache["fetched"]).astimezone(NY)
    except (KeyError, TypeError, ValueError):
        fetched = None
    if (fetched and X.is_trade_date(fetched.date()) and
            fetched >= window_start(target_session(fetched.date().isoformat()), market)):
        days.pop(fetched.date().isoformat(), None)

    days = dict(clean(market, sorted(days.items())))
    sources = {}
    for day, bar in sorted(minute_sessions.items()):
        session = X.session(market, day)
        if not session or session["close"] is None or now < session["close"]:
            continue
        if not (bar.get("complete") and bar.get("full")):
            continue
        values = [bar.get(key) for key in ("o", "h", "l", "c")]
        if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in values):
            continue
        o, h, lo, c = values
        if lo <= min(o, c) <= max(o, c) <= h and lo < h:
            days[day] = values
            sources[day] = "Iron Brain completed Globex session"
    return sorted(days.items()), sources


def next_session(last_iso):
    d = dt.date.fromisoformat(last_iso) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def lagged(keys, series, lag_days=1):
    """For each date, the latest value that was public by then: observations dated at least lag_days earlier."""
    if not series:
        return np.full(len(keys), np.nan)
    sd = sorted(series)
    out, j, last = np.full(len(keys), np.nan), 0, np.nan
    for i, k in enumerate(keys):
        cutoff = (dt.date.fromisoformat(k) - dt.timedelta(days=lag_days)).isoformat()
        while j < len(sd) and sd[j] <= cutoff:
            last = series[sd[j]]
            j += 1
        out[i] = last
    return out


def calendar_tiers():
    """{NY date: 2 for CPI / payrolls / Fed, 1 for other big releases} and Fed days, from the release calendar."""
    tiers, fomc = {}, set()
    for f in glob.glob(os.path.join(TV_DIR, "*.json")):
        try:
            c = json.load(open(f))
        except (OSError, ValueError):
            continue
        for r in c.get("rows", []) if isinstance(c, dict) else c:
            t, d = r.get("t") or "", r.get("d")
            if not d:
                continue
            day = dt.datetime.fromisoformat(d.replace("Z", "+00:00")).astimezone(NY).date().isoformat()
            if t == "Interest Rate":
                fomc.add(day)
                tiers[day] = 2
            elif re.search(r"Inflation Rate MoM|Core Inflation Rate MoM|Non Farm Payrolls", t):
                tiers[day] = 2
            elif re.search(r"Retail Sales MoM|Core PCE|GDP Growth|ISM (Manufacturing|Services)|PPI MoM", t):
                tiers[day] = max(tiers.get(day, 0), 1)
    try:
        for e in json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]:
            title, day = e.get("title") or "", e.get("date")
            if TIER1.search(title):
                tiers[day] = 2
                if "FOMC" in title:
                    fomc.add(day)
            elif TIER2.search(title):
                tiers[day] = max(tiers.get(day, 0), 1)
    except (OSError, ValueError, KeyError):
        pass
    return tiers, fomc


def _nth(y, m, wd, n):
    """n-th weekday wd (0 = Monday) of a month; n = -1 for the last."""
    if n > 0:
        d = dt.date(y, m, 1)
        return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
    d = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return dt.date(y, month, (h + l_ - 7 * m + 114) % 31 + 1)


# closures outside the regular rules (national days of mourning, 9/11, Hurricane Sandy)
SPECIAL_CLOSED = {"2001-09-11", "2001-09-12", "2001-09-13", "2001-09-14", "2004-06-11", "2007-01-02", "2012-10-29",
                  "2012-10-30", "2018-12-05", "2025-01-09"}


def nyse_holidays(y):
    """The US stock exchanges' full-day holidays for year y, by their published rules (a Saturday holiday is observed
    on Friday, a Sunday one on Monday; New Year's Day on a Saturday is not moved back into December)."""
    def obs(d, back=True):
        if d.weekday() == 5:
            return d - dt.timedelta(days=1) if back else None
        return d + dt.timedelta(days=1) if d.weekday() == 6 else d
    days = [obs(dt.date(y, 1, 1), back=False), _nth(y, 2, 0, 3), _easter(y) - dt.timedelta(days=2),
            _nth(y, 5, 0, -1), obs(dt.date(y, 7, 4)), _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), obs(dt.date(y, 12, 25))]
    if y >= 1998:
        days.append(_nth(y, 1, 0, 3))                       # Martin Luther King Jr. Day
    if y >= 2022:
        days.append(obs(dt.date(y, 6, 19)))                  # Juneteenth
    return {d.isoformat() for d in days if d} | {d for d in SPECIAL_CLOSED if d.startswith(str(y))}


def market_holidays():
    """Weekdays the US exchanges are closed, from Displace's calendar ('... US markets closed')."""
    try:
        ev = json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]
    except (OSError, ValueError, KeyError):
        return set()
    return {e["date"] for e in ev if e.get("impact") == "holiday" and re.search(r"markets closed", e.get("title", ""), re.I)}


# ---------------------------------------------------------------- features

def _roll(a, w, f):
    n = len(a)
    return np.array([f(a[i - w + 1:i + 1]) if i >= w - 1 else np.nan for i in range(n)])


def _turn_of_month(d):
    """The session is the last trading day of its month or one of the first three."""
    day = dt.date.fromisoformat(d)
    after = dt.date.fromisoformat(next_session(d))
    k = sum(1 for x in range(1, day.day + 1) if dt.date(day.year, day.month, x).weekday() < 5)
    return after.month != day.month or k <= 3


def build(rows, tiers, fomc, market=None):
    keys = [d for d, _ in rows]
    X = np.array([v for _, v in rows], float)
    o, h, l, c = X.T
    n = len(c)
    r = np.r_[0.0, np.log(c[1:] / c[:-1])]
    rg = np.log(np.maximum(h, c) / np.minimum(l, c))
    rg[rg <= 0] = np.nan
    vol = _roll(r, 20, np.std)
    vol[:21] = np.nan
    vol[vol == 0] = np.nan
    atr = _roll(rg, 20, np.nanmean)
    F = {}
    F["rev1"] = r / vol
    F["mom20"] = np.r_[np.full(20, np.nan), np.log(c[20:] / c[:-20])] / (vol * math.sqrt(20))
    F["mom120"] = np.r_[np.full(120, np.nan), np.log(c[120:] / c[:-120])] / (vol * math.sqrt(120))
    F["trend200"] = np.log(c / _roll(c, 200, np.mean)) / (vol * math.sqrt(50))
    lv = np.log(vol)
    F["volreg"] = lv - np.array([np.nanmedian(lv[i - 250:i + 1]) if i >= 271 else np.nan for i in range(n)])
    F["clv"] = np.where(h > l, (c - l) / np.where(h > l, h - l, 1) - 0.5, 0.0)
    nxt = [next_session(k) for k in keys]
    F["tom"] = np.array([1.0 if _turn_of_month(d) else 0.0 for d in nxt])
    F["prefomc"] = np.array([1.0 if next_session(d) in fomc else 0.0 for d in nxt])
    F["fomc"] = np.array([1.0 if d in fomc else 0.0 for d in nxt])
    F["bigdown"] = (np.nan_to_num(F["rev1"]) < -2).astype(float)
    F["bigup"] = (np.nan_to_num(F["rev1"]) > 2).astype(float)
    F["ev1"] = np.array([1.0 if tiers.get(d) == 2 else 0.0 for d in nxt])
    F["announce"] = F["ev1"]
    # the next weekday is an exchange holiday (scheduled, so known in advance): the exchanges' holiday rules, plus
    # Displace's calendar of 'US markets closed' days. Not gaps in the candles: Yahoo's history has missing days.
    yrs = {int(k[:4]) for k in keys} | {int(keys[-1][:4]) + 1} if keys else set()
    closed = set().union(*(nyse_holidays(y) for y in yrs)) | market_holidays() if yrs else market_holidays()
    F["preholiday"] = np.array([1.0 if next_session(d) in closed else 0.0 for d in nxt])
    F["ev2"] = np.array([1.0 if tiers.get(d) == 1 else 0.0 for d in nxt])
    F["mon"] = np.array([1.0 if dt.date.fromisoformat(d).weekday() == 0 else 0.0 for d in nxt])
    F["dist_h"] = np.log(h / c) / atr
    F["dist_l"] = np.log(c / l) / atr
    import rolls
    S = {"keys": keys, "o": o, "h": h, "l": l, "c": c, "r": r, "rg": rg, "vol": vol, "atr": atr,
         "roll": np.array(rolls.mask(market, keys) if market else [False] * len(keys), bool),
         "years": np.array([int(k[:4]) for k in keys])}
    return F, S


def cross_features(F, S, series, iv_sid):
    keys = S["keys"]
    n = len(keys)
    lag = lambda sid: lagged(keys, series.get(sid), PUBLISH_LAG.get(sid, 1))
    with np.errstate(divide="ignore", invalid="ignore"):
        if iv_sid:
            liv = np.log(lag(iv_sid))
            med = np.array([np.nanmedian(liv[i - 250:i + 1]) if i >= 250 and np.isfinite(liv[i - 250:i + 1]).sum() > 100 else np.nan for i in range(n)])
            F["iv_level"] = liv - med
            F["iv_chg5"] = np.r_[np.full(5, np.nan), liv[5:] - liv[:-5]]
            F["iv"] = liv
        F["term"] = np.log(lag("VIXCLS") / lag("VXVCLS"))
        for name, sid, how in (("hy5", "BAMLH0A0HYM2", "diff"), ("ry5", "DFII10", "diff"), ("usd5", "DTWEXBGS", "log"),
                               ("y2_5", "DGS2", "diff")):
            v = lag(sid)
            F[name] = np.r_[np.full(5, np.nan), (np.log(v[5:] / v[:-5]) if how == "log" else v[5:] - v[:-5])]


# ---------------------------------------------------------------- direction: tests, then a decision across all markets

def direction_tests(F, S, signals):
    c, years = S["c"], S["years"]
    n = len(c)
    y = np.r_[(c[1:] > c[:-1]).astype(float), np.nan]
    y[np.r_[S["roll"][1:], False]] = np.nan          # contract switch: the move from the last close isn't real (rolls.py)
    known = ~np.isnan(y)
    out = {}
    for k in signals:
        x = F[k]
        m = known & np.isfinite(x)
        w = Q.walk_forward_logit(years[m], x[m][:, None], y[m], first=FIRST_TEST_YEAR)
        res = Q.judge(w, float("inf"))
        res["n"] = int(m.sum())
        out[k] = res
    ev = {}
    half_year = years[n // 2]
    for k in EVENTS:
        lo = EVENT_FROM.get(k, 0)
        allow = known & (years >= lo)
        sel = allow & (F[k] == 1)
        if sel.sum() < 20:
            ev[k] = {"n": int(sel.sum()), "stable": False}
            continue
        b, rate = float(y[allow].mean()), float(y[sel].mean())
        z = (rate - b) / math.sqrt(b * (1 - b) / sel.sum())
        parts = [y[sel & (years < half_year)], y[sel & (years >= half_year)], y[sel & (years >= 2019)]]
        same = all(len(p) and (p.mean() - b) * (rate - b) > 0 for p in parts)
        rr = lambda a: round(float(a.mean()), 3) if len(a) else None
        ev[k] = {"n": int(sel.sum()), "up": round(rate, 3), "base": round(b, 3), "z": round(z, 2),
                 "halves": [rr(parts[0]), rr(parts[1])], "recent": rr(parts[2]), "stable": bool(same and sel.sum() >= 60)}
    return {"y": y, "base": float(y[known].mean()), "signals": out, "events": ev, "days": int(known.sum())}


def decide(tests, t_bar, z_bar):
    """Mark passes against bars set across all markets; equity indices must agree with each other."""
    for m, T in tests.items():
        for k, r in T["signals"].items():
            ok = r.get("stable") and (r.get("t") or 0) >= t_bar
            if ok and m in EQUITY:
                others = [tests[o]["signals"].get(k, {}).get("skill") for o in EQUITY if o != m and o in tests]
                others = [s for s in others if s is not None]
                ok = bool(others) and sum(1 for s in others if s > 0) * 2 > len(others)
            r["tested"] = bool(ok)
        for k, e in T["events"].items():
            e["tested"] = bool(e.get("stable") and abs(e.get("z") or 0) >= z_bar)


def direction_today(F, T, i):
    y, base = T["y"], T["base"]
    known = ~np.isnan(y)
    used = [k for k, r in T["signals"].items() if r.get("tested") and np.isfinite(F[k][i])]
    p = base
    if used:
        Xa = np.column_stack([F[k] for k in used])
        m = known & np.isfinite(Xa).all(1)
        (Xt, Xe), _ = Q.standardize(Xa[m], Xa[i:i + 1])
        b = Q.logit_fit(Xt, y[m])
        p = float(Q.sig(np.r_[1.0, Xe[0]] @ b))
    why = list(used)
    for k, v in T["events"].items():
        if v.get("tested") and F[k][i] == 1:
            p += v["up"] - v["base"]
            why.append(k)
    p = min(0.9, max(0.1, p))
    bias = "long" if p >= 0.5 + LEAN else "short" if p <= 0.5 - LEAN else "neutral"
    return round(p, 3), bias, why


# ---------------------------------------------------------------- volatility, touch, levels

def levels(F, S):
    """P(next day above today's high / below today's low), with out-of-sample skill and reliability."""
    h, l, years = S["h"], S["l"], S["years"]
    n = len(h)
    out = {}
    for side, key in (("high", "dist_h"), ("low", "dist_l")):
        y = np.r_[((h[1:] > h[:-1]) if side == "high" else (l[1:] < l[:-1])).astype(float), np.nan]
        y[np.r_[S["roll"][1:], False]] = np.nan      # contract switch (rolls.py)
        x = F[key]
        m = np.isfinite(y) & np.isfinite(x)
        w = Q.walk_forward_logit(years[m], x[m][:, None], y[m], first=FIRST_TEST_YEAR)
        res = Q.judge(w, 1.65)
        (Xt, Xe), _ = Q.standardize(x[m][:, None], x[n - 1:n][:, None])
        b = Q.logit_fit(Xt, y[m])
        out[side] = {"p": round(float(Q.sig(np.r_[1.0, Xe[0]] @ b)), 3), "base": round(float(y[m].mean()), 3),
                     "skill": res.get("skill"), "tested": res.get("tested"),
                     "calib": Q.reliability(w[:, 1], w[:, 3]) if len(w) else []}
    return out


def volatility(F, S, iv_ok):
    """HAR on the log daily range, compared out of sample with the 20-day average; a conditional touch ladder."""
    rg, years, r = S["rg"], S["years"], S["r"]
    n = len(rg)
    d1, d5, d22 = np.log(rg), np.log(_roll(rg, 5, np.nanmean)), np.log(_roll(rg, 22, np.nanmean))
    cols = [d1, d5, d22, F["ev1"], F["ev2"], F["mon"]]
    names = ["yesterday", "last week", "last month", "big release", "other major release", "Monday"]
    if iv_ok and "iv" in F and np.isfinite(F["iv"][-1]) and np.isfinite(F["iv"]).sum() > 1500:
        cols.insert(3, F["iv"])
        names.insert(3, "implied volatility")
    Fm = np.column_stack(cols)
    y = np.r_[np.log(rg[1:]), np.nan]
    r_next = np.r_[r[1:], np.nan]
    base = np.log(_roll(rg, 20, np.nanmean))
    good = np.where(np.isfinite(Fm).all(1))[0]
    train_from = max(EVENTS_FROM, int(years[good[0]]) + 1) if len(good) else EVENTS_FROM
    wf = Q.har_walk_forward(years, Fm, y, base, first=train_from + 2, train_from=train_from, r_next=r_next)
    stats = {}
    if len(wf["y"]):
        mse, mse0 = float(np.mean((wf["y"] - wf["pred"]) ** 2)), float(np.mean((wf["y"] - wf["base"]) ** 2))
        stats = {"gain": round(1 - mse / mse0, 3),
                 "coverage": round(float(np.mean((wf["y"] >= wf["lo"]) & (wf["y"] <= wf["hi"]))), 3),
                 "coverage_old": round(float(np.mean((wf["y"] >= wf["oldlo"]) & (wf["y"] <= wf["oldhi"]))), 3),
                 "width": round(float(np.mean(wf["hi"] - wf["lo"])), 3),
                 "width_old": round(float(np.mean(wf["oldhi"] - wf["oldlo"])), 3), "n": int(len(wf["y"])), "since": int(train_from + 2)}
    ok = np.isfinite(Fm).all(1) & np.isfinite(y) & (years >= train_from)
    b, q = Q.har_fit(Fm, y, ok)
    pred = float(np.r_[1.0, Fm[-1]] @ b)
    fitted = np.exp(np.c_[np.ones(ok.sum()), Fm[ok]] @ b)
    scale = float(math.sqrt(np.nanmean(r_next[ok] ** 2) / np.mean(fitted ** 2)))
    sigma = scale * math.exp(pred)
    touch = touch_ladder(S, wf, sigma) if len(wf["y"]) else []
    mult = {nm: round(float(math.exp(bb)), 3) for nm, bb in zip(names, b[1:]) if nm in ("big release", "other major release", "Monday")}
    return {"pred": pred, "q": [float(x) for x in q], "sigma": sigma, "stats": stats, "touch": touch, "inputs": names,
            "multipliers": mult}


def touch_ladder(S, wf, sigma_today):
    """P(reach close +/- k sigma), given how far today's high and low sit from the close (in forecast sigma).
    Sigma for each past day comes from the model fitted before that year, so nothing is seen in advance."""
    c, h, l, years = S["c"], S["h"], S["l"], S["years"]
    n = len(c)
    idx = wf["idx"].astype(int)
    keep = (idx + 1 < n) & np.isfinite(wf["c"])
    keep &= ~S["roll"][np.minimum(idx + 1, n - 1)]   # contract switch (rolls.py)
    idx = idx[keep]
    sig = wf["c"][keep] * np.exp(wf["pred"][keep])
    yrs = years[idx]
    dh, dl = np.log(h[idx] / c[idx]) / sig, np.log(c[idx] / l[idx]) / sig
    up_move, dn_move = np.log(h[idx + 1] / c[idx]) / sig, np.log(c[idx] / l[idx + 1]) / sig
    th, tl = math.log(h[-1] / c[-1]) / sigma_today, math.log(c[-1] / l[-1]) / sigma_today
    out = []
    for k in TOUCH_K:
        row = {"k": k}
        for side, x, mv, now in (("up", dh, up_move, th), ("dn", dl, dn_move, tl)):
            y = (mv >= k).astype(float)
            w = Q.walk_forward_logit(yrs, x[:, None], y, first=int(yrs.min()) + 3, min_train=400)
            (Xt, Xe), _ = Q.standardize(x[:, None], np.array([[now]]))
            b = Q.logit_fit(Xt, y)
            skill = Q.brier_skill(w) if len(w) else None
            base = float(y.mean())
            # the close's position only moves the odds where that beat the plain rate out of sample
            row[side + "_p"] = round(float(Q.sig(np.r_[1.0, Xe[0]] @ b)) if skill and skill > 0 else base, 3)
            row[side + "_base"] = round(base, 3)
            row[side + "_skill"] = round(skill, 4) if skill is not None else None
        out.append(row)
    return out


# ---------------------------------------------------------------- sessions

SESSION_TESTS = 6  # three tests in each of two markets


def sessions(m):
    """Overnight vs New York session and an intraday momentum test, from the hourly archive (NQ and gold)."""
    try:
        import bars
        rows = bars.load(m, "1h")
    except Exception:
        return None
    if len(rows) < 300:
        return None
    by = {}
    for t, o, h, l, c in rows:
        by.setdefault(t.date(), {})[t.hour] = (o, c)
    ov, dy, mx, my, dates = [], [], [], [], []
    prev = None  # the last day with a 16:00 close, so Mondays compare with Friday
    for d in sorted(by):
        B = by[d]
        if prev is not None and all(k in B for k in (8, 9, 14, 15)):
            p16 = by[prev][15][1]
            c9, c10, c15, c16 = B[8][1], B[9][1], B[14][1], B[15][1]
            ov.append(math.log(c9 / p16))
            dy.append(math.log(c16 / c9))
            mx.append(math.log(c10 / p16))
            my.append(math.log(c16 / c15))
            dates.append(d)
        if 15 in B and d.weekday() < 5:
            prev = d
    if len(ov) < 120:
        return None
    ov, dy, mx, my = map(np.array, (ov, dy, mx, my))
    n = len(ov)

    def effect(a):
        up = float((a > 0).mean())
        z = (up - 0.5) / math.sqrt(0.25 / n)
        t = float(a.mean() / (a.std() / math.sqrt(n)))
        h1, h2 = float((a[: n // 2] > 0).mean()), float((a[n // 2:] > 0).mean())
        same = (h1 - 0.5) * (up - 0.5) > 0 and (h2 - 0.5) * (up - 0.5) > 0
        bar = Q.z_needed(SESSION_TESTS)
        return {"up": round(up, 3), "z": round(z, 2), "bp": round(float(a.mean() * 1e4), 1), "t": round(t, 2),
                "halves": [round(h1, 3), round(h2, 3)], "bar": round(bar, 2),
                # more often up AND an average move that is itself significant, both past the bar, in both halves
                "passed": bool(abs(z) >= bar and abs(t) >= bar and same and z * t > 0),
                "frequent": bool(abs(z) >= bar and same)}
    agree = (np.sign(mx) == np.sign(my)) & (mx != 0) & (my != 0)
    k = int(agree.sum())
    z = (k / n - 0.5) / math.sqrt(0.25 / n)
    h1, h2 = float(agree[: n // 2].mean()), float(agree[n // 2:].mean())
    return {"days": n, "from": dates[0].isoformat(), "to": dates[-1].isoformat(),
            "mondays": int(sum(1 for d in dates if d.weekday() == 0)),
            "overnight": effect(ov), "day": effect(dy),
            "momentum": {"agree": round(k / n, 3), "z": round(z, 2), "corr": round(float(np.corrcoef(mx, my)[0, 1]), 3),
                         "halves": [round(h1, 3), round(h2, 3)], "passed": bool(z >= Q.z_needed(SESSION_TESTS) and h1 > 0.5 and h2 > 0.5)}}


# ---------------------------------------------------------------- one market

def prepare(m, rows, series, tiers, fomc):
    group, iv_sid = MARKETS[m][7], MARKETS[m][5]
    F, S = build(rows, tiers, fomc, m)
    cross_features(F, S, series, iv_sid)
    sigs = list(PRICE_SIGNALS) + [k for k in CROSS_FOR[group] if k in F and np.isfinite(F[k]).sum() > 1500]
    return {"F": F, "S": S, "sigs": sigs, "T": direction_tests(F, S, sigs), "rows": rows}


def finish(m, ctx, tiers, t_bar, z_bar):
    sym, short, full, pv, micro, iv_sid, dp, group = MARKETS[m]
    F, S, T, rows, sigs = ctx["F"], ctx["S"], ctx["T"], ctx["rows"], ctx["sigs"]
    i = len(rows) - 1
    p, bias, why = direction_today(F, T, i)
    L = levels(F, S)
    V = volatility(F, S, iv_ok=bool(iv_sid))
    c, h, l = float(S["c"][i]), float(S["h"][i]), float(S["l"][i])
    pts = lambda x: round(c * (math.exp(math.exp(x)) - 1), 6)  # x is the log of the log-range
    yd = rows[-1][0]
    nxt = target_session(yd)
    labels = {**PRICE_SIGNALS, **CROSS_SIGNALS}
    val = lambda a: None if not np.isfinite(a) else round(float(a), 2)
    board = [{"key": k, "label": labels[k], "value": val(F[k][i]), "skill": T["signals"][k].get("skill"),
              "t": T["signals"][k].get("t"), "stable": T["signals"][k].get("stable"), "tested": T["signals"][k].get("tested"),
              "historical_candidate": T["signals"][k].get("historical_candidate",False), "used": k in why, "kind": "price" if k in PRICE_SIGNALS else "cross"} for k in sigs]
    cal = [{"key": k, "label": lab, "active": bool(F[k][i] == 1), "n": T["events"][k].get("n"), "up": T["events"][k].get("up"),
            "base": T["events"][k].get("base"), "z": T["events"][k].get("z"), "tested": T["events"][k].get("tested"),
            "historical_candidate": T["events"][k].get("historical_candidate",False), "used": k in why} for k, lab in EVENTS.items()]
    touch = [{**t, "up": round(c * math.exp(t["k"] * V["sigma"]), 6), "dn": round(c * math.exp(-t["k"] * V["sigma"]), 6)} for t in V["touch"]]
    return {"name": short, "full": full, "pv": pv, "micro": micro, "dp": dp, "group": group,
            "candle": yd, "day_name": WD[dt.date.fromisoformat(yd).weekday()],
            "p_up": p, "base_up": round(T["base"], 3), "bias": bias, "drivers": why, "tier": "tested" if why else "base",
            "t_req": round(t_bar, 2), "z_req": round(z_bar, 2),
            "levels": {"high": h, "low": l, "close": c},
            "takes": {s: {k: v for k, v in L[s].items() if k != "calib"} for s in L},
            "range": {"points": pts(V["pred"] + V["q"][1]), "lo": pts(V["pred"] + V["q"][0]), "hi": pts(V["pred"] + V["q"][2]),
                      # what a normal day has looked like: last 20 sessions, and the last year (median), in points
                      "avg20": round(float(np.mean((S["h"] - S["l"])[-20:])), 6),
                      "med250": round(float(np.median((S["h"] - S["l"])[-250:])), 6)},
            "band": {"lo": round(c * math.exp(-V["sigma"]), 6), "hi": round(c * math.exp(V["sigma"]), 6), "sigma": round(c * (math.exp(V["sigma"]) - 1), 6)},
            "touch": touch,
            "vol": {"stats": V["stats"], "inputs": V["inputs"], "multipliers": V["multipliers"],
                    "news": "big" if tiers.get(nxt) == 2 else "major" if tiers.get(nxt) == 1 else None},
            "calib": {"high": L["high"]["calib"], "low": L["low"]["calib"]},
            "signals": board, "calendar": cal, "sessions": sessions(m) if m in ("nq", "gold") else None,
            "history": {"days": T["days"], "since": rows[0][0][:4]}}


def read(m, rows, series, tiers, fomc):
    """One market on its own (tests and tools): bars set for that market alone."""
    ctx = prepare(m, rows, series, tiers, fomc)
    t_bar, z_bar = Q.t_needed(len(ctx["sigs"])), Q.z_needed(len(EVENTS))
    decide({m: ctx["T"]}, t_bar, z_bar)
    return finish(m, ctx, tiers, t_bar, z_bar)


# ---------------------------------------------------------------- live record

ARCHIVE_DIR = os.path.join(DATA, "bias", "archive")
KEEP = 6000                                   # entries kept in the live log; older ones move to the archive, never dropped


def window_start(day_iso, market="nq"):
    """When the futures session a forecast is for opens (engine/exchange.py: 18:00 New York after the previous
    trading date, so Friday 27 Nov 2026 opens Wednesday 25 Nov; Monday opens Sunday). A date with no session
    (a holiday) falls back to 18:00 the evening before, and problems() voids such a forecast anyway."""
    try:
        return PUB.cutoff({"market": market, "for": day_iso})
    except ValueError:
        d = dt.date.fromisoformat(day_iso) - dt.timedelta(days=1)
        return dt.datetime.combine(d, dt.time(18, 0), NY)


def target_session(candle_iso):
    """The trading date a forecast made from this candle is for: the next CME trading date (engine/exchange.py),
    which skips exchange holidays. The registered historical features keep next_session (weekdays) unchanged."""
    return X.next_trade_date(candle_iso).isoformat()


def problems(e):
    """Why a log entry can't be a valid forecast (empty when it can): probabilities outside 0-1, an expected range
    below zero or upside down, touch levels on the wrong side."""
    out = []
    for k in ("p_up", "base_up", "p_high", "p_low", "p_up1", "p_dn1"):
        v = e.get(k)
        if (v is None and k in ("p_up", "base_up", "p_high", "p_low")) or (v is not None and not (type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1)):
            out.append(f"{k} {v} is not a probability")
    lo, hi = e.get("range_lo"), e.get("range_hi")
    if lo is None or hi is None or not (math.isfinite(lo) and math.isfinite(hi)) or lo < 0 or lo > hi:
        out.append(f"expected range {lo} to {hi} is not a valid high-minus-low range")
    if e.get("up1") is not None and e.get("dn1") is not None and not e["dn1"] < e["up1"]:
        out.append("touch levels are on the wrong side")
    if e.get("for"):
        try:
            if not X.is_trade_date(e["for"]):
                out.append(f"target date {e['for']} has no CME session ({X.day_status(e['for'])[1] or 'weekend'})")
        except ValueError:
            out.append(f"target date {e['for']} is not a date")
    return out


def audit(entries, now):
    """Mark, never delete: entries that fail problems() become void (kept, with the reason and when it was found, and
    left out of every score), and each entry records whether it was issued before its session opened. Only eligible,
    non-void entries count in the live record. Runs on old entries too, so earlier mistakes get a visible correction."""
    stamp = now.isoformat(timespec="minutes")
    for e in entries:
        if e.get("logged") and e.get("for") and "eligible" in e and not e.get("eligibility_checked"):
            try:
                new = dt.datetime.fromisoformat(e["logged"]) < window_start(e["for"], e.get("market", "nq"))
            except (ValueError, TypeError):
                new = False
            if new != e["eligible"]:
                e["eligibility_correction"] = {"found": stamp, "was": e["eligible"], "now": new,
                                               "reason": "rechecked against CME session times (engine/exchange.py)"}
                e["eligible"] = new
            e["eligibility_checked"] = "exchange " + __import__("exchange").EXCHANGE_VERSION
        if "eligible" not in e and e.get("logged") and e.get("for"):
            try:
                e["eligible"] = dt.datetime.fromisoformat(e["logged"]) < window_start(e["for"], e["market"])
            except (ValueError, TypeError):
                e["eligible"] = False
        if "eligible" not in e:
            e["eligible"] = False
        if not e.get("void"):
            p = problems(e)
            if p:
                e["void"] = True
                e["correction"] = {"found": stamp, "reason": "; ".join(p),
                                   "note": "Kept as published but excluded from all scores: the forecast was invalid."}
    return entries


def archive(entries, keep=KEEP, directory=ARCHIVE_DIR):
    """Move all but the newest `keep` entries into yearly archive files (by target day), merging without duplicates."""
    old, live = entries[:-keep] if len(entries) > keep else [], entries[-keep:]
    by = {}
    for e in old:
        by.setdefault(str(e.get("for", "unknown"))[:4], []).append(e)
    for year, rows in by.items():
        path = os.path.join(directory, f"log-{year}.json")
        try:
            have = json.load(open(path)).get("entries", [])
        except (OSError, ValueError):
            have = []
        seen = {(x["market"], x["candle"]) for x in have}
        have += [x for x in rows if (x["market"], x["candle"]) not in seen]
        write_json(path, {"entries": sorted(have, key=lambda x: (x.get("for", ""), x["market"]))})
    return live


def write_json(path, doc, **kw):
    """Write the whole file or nothing: a crash mid-write can't leave half a JSON file for the site."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, **kw)
    os.replace(tmp, path)


def score_log(rows_by, entries, published_views=None):
    for e in entries:
        if e.get("scored") or e.get("void"):
            continue
        rows = rows_by.get(e["market"]) or []
        days = dict(rows)
        nxt = e.get("for")
        if not nxt or nxt not in days or nxt <= e["candle"]:
            continue
        prior = e.get("prior_levels")
        if prior is None:
            view = (published_views or {}).get(e["market"])
            if view and PUB.matches(e, view):
                prior = view["levels"]
            elif e["candle"] in days:
                a = days[e["candle"]]
                prior = {"high": a[1], "low": a[2], "close": a[3]}
        if prior is None:
            continue
        b = days[nxt]
        up = 1 if b[3] > prior["close"] else 0
        actual_range = b[1] - b[2]
        import rolls
        if rolls.is_roll(e["market"], nxt):
            e["roll"] = True                             # contract switch day: kept, not counted (rolls.py)
        e.update({"day": nxt, "scored": 1, "up": up, "brier": round((e["p_up"] - up) ** 2, 4),
                  "highTaken": int(b[1] > prior["high"]), "lowTaken": int(b[2] < prior["low"]),
                  "inRange": int(e["range_lo"] <= actual_range <= e["range_hi"]),
                  "actual_range": actual_range})
        if e.get("up1") is not None:
            e["up1Hit"], e["dn1Hit"] = int(b[1] >= e["up1"]), int(b[2] <= e["dn1"])
        if e["bias"] != "neutral" and e.get("tier") == "tested":
            e["hit"] = int((up == 1) == (e["bias"] == "long"))
    return entries


def summary(entries):
    voided = sum(1 for e in entries if e.get("void"))
    late = sum(1 for e in entries if e.get("eligible") is False and not e.get("void"))
    done = [e for e in entries if e.get("scored") and not e.get("void") and not e.get("roll") and e.get("eligible") is True and e.get("publication_verified") is True]
    calls = [e for e in done if "hit" in e and e.get("tier") == "tested"]
    out = {"days": len(done), "calls": len(calls), "hits": sum(e["hit"] for e in calls),
           "inRange": sum(e["inRange"] for e in done), "recent": done[-10:][::-1],
           "voided": voided, "late": late,
           "unverified": sum(1 for e in entries if e.get("eligible") is True and not e.get("void") and not e.get("publication_verified"))}
    if done:
        out["brier"] = round(sum(e["brier"] for e in done) / len(done), 4)
        out["baseBrier"] = round(sum((e["base_up"] - e["up"]) ** 2 for e in done) / len(done), 4)
        lv = [(e["p_high"], e["highTaken"]) for e in done] + [(e["p_low"], e["lowTaken"]) for e in done]
        out["levelBrier"] = round(sum((p - y) ** 2 for p, y in lv) / len(lv), 4)
        t = [(e["p_up1"], e["up1Hit"]) for e in done if e.get("p_up1") is not None and "up1Hit" in e] + \
            [(e["p_dn1"], e["dn1Hit"]) for e in done if e.get("p_dn1") is not None and "dn1Hit" in e]
        if t:
            out["touchBrier"] = round(sum((p - y) ** 2 for p, y in t) / len(t), 4)
    return out


def news_today(day_iso):
    try:
        ev = json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]
    except (OSError, ValueError, KeyError):
        return []
    return [{"time": e.get("time"), "title": e.get("title"), "impact": e.get("impact")}
            for e in ev if e.get("date") == day_iso and e.get("impact") == "high"]


def _clean_json(o):
    if isinstance(o, dict):
        return {k: _clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean_json(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def run(now=None, fetch=download, fetch_series=fred_download, markets=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    t0 = time.time()
    try:
        entries = json.load(open(LOG)).get("entries", [])
    except (OSError, ValueError):
        entries = []
    entries = [e for e in entries if "p_up" in e]
    audit(entries, now)
    registered = {(e["market"], e["candle"]): e for e in entries}
    try:
        with open(OUT) as fh:
            previous = json.load(fh).get("markets", {})
    except (OSError, ValueError):
        previous = {}
    markets = markets or MARKETS
    out = {}
    for market in markets:
        view = previous.get(market)
        if view:
            row = registered.get((market, view.get("candle")))
            if row and PUB.matches(row, view):
                out[market] = {**view, "forecast_at": row["logged"], "forecast_id": PUB.identity(row)}

    series = {sid: sync_series(sid, now, fetch_series) for sid in SERIES}
    tiers, fomc = calendar_tiers()
    ctxs, rows_by, notes, candle_sources = {}, {}, {}, {}
    ib = iron_brain_sessions() if fetch is download else {}
    patches = load_patches()
    for m in markets:
        try:
            c = sync(m, now, fetch)
            notes[m] = despike_days(m, c["days"], ib, patches)
            rows, sources = settled_rows(m, c, ib.get(m, {}), now)
            rows_by[m] = rows
            if len(rows) < 800:
                log(f"bias: not enough {m} history yet ({len(rows)} days)")
                continue
            candle = rows[-1][0]
            candle_sources[m] = sources.get(candle, "Yahoo Finance daily candle")
            ctxs[m] = prepare(m, rows, series, tiers, fomc)
        except Exception as e:  # one market failing never blocks the others
            log(f"bias: {m} failed ({e!r})")
    if any(patches.values()):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(PATCHES, "w") as fh:
            json.dump(patches, fh, indent=1, sort_keys=True)
    for m, n in notes.items():
        for x in n:
            log(f"bias: {m} {x}")
    if not ctxs and not out:
        log("bias: nothing to publish; the last file stays live")
        return 1
    # one bar for every direction test on the site, and one for every calendar test
    n_sig = sum(len(x["sigs"]) for x in ctxs.values())
    t_bar, z_bar = Q.t_needed(max(1, n_sig)), Q.z_needed(max(1, len(EVENTS) * len(ctxs)))
    if ctxs:
        decide({m: x["T"] for m, x in ctxs.items()}, t_bar, z_bar)
    # Selection and combined-model performance need a separate untouched evaluation.
    # Preserve candidate diagnostics, but prevent automatic deployment of selected directions.
    for ctx in ctxs.values():
        for group in ("signals","events"):
            for result in ctx["T"][group].values():
                result["historical_candidate"] = bool(result.get("tested"))
                result["tested"] = False
    for m, ctx in ctxs.items():
        candle = rows_by[m][-1][0]
        if (m, candle) in registered or (m in out and candle <= out[m]["candle"]):
            continue
        try:
            r = finish(m, ctx, tiers, t_bar, z_bar)
        except Exception as e:
            log(f"bias: {m} failed ({e!r})")
            continue
        r["tests"] = {"signals": n_sig, "calendar": len(EVENTS) * len(ctxs)}
        r["dataNotes"] = notes.get(m, [])[-3:]
        r["candle_source"] = candle_sources[m]
        target = target_session(r["candle"])
        session = X.session(m, target)
        if session:
            r["session"] = {"date": target, "open": session["open"].isoformat(),
                            "close": session["close"].isoformat() if session["close"] else None,
                            "halts": [halt["halt_at"] for halt in session["includes_halt_days"]]}
        r["forecast_at"] = now.isoformat(timespec="minutes")
        row = {"market": m, "candle": r["candle"], "for": target, **PUB.forecast_values(r),
               "logged": r["forecast_at"], "eligible": now < window_start(target, m)}
        entries.append(row)
        if not problems(row):
            r["forecast_id"] = PUB.identity(row)
            out[m] = r
    if not out:
        log("bias: nothing to publish; the last file stays live")
        return 1
    audit(entries, now)
    score_log(rows_by, entries, previous)
    day = max(v["session"]["date"] for v in out.values())
    # Lifetime summaries include archived records; do not count duplicates.
    lifetime = {}
    for path in sorted(glob.glob(os.path.join(ARCHIVE_DIR, "log-*.json"))):
        for e in json.load(open(path))["entries"]:
            lifetime[(e["market"], e["candle"])] = e
    for e in entries:
        lifetime[(e["market"], e["candle"])] = e
    receipts = PUB.load()
    for e in lifetime.values():
        try:
            e["publication_verified"] = PUB.verified(e, receipts, PUB.cutoff(e))
        except (KeyError, ValueError, TypeError):
            e["publication_verified"] = False
    live = {m: summary([e for e in lifetime.values() if e["market"] == m]) for m in out}
    doc = {"asof": now.isoformat(timespec="minutes"), "for": day, "markets": out, "order": [m for m in MARKETS if m in out],
           "news": news_today(day), "live": live,
           "method": {"first_test_year": FIRST_TEST_YEAR, "lean": LEAN, "t_bar": round(t_bar, 2), "z_bar": round(z_bar, 2),
                      "signal_tests": max(v["tests"]["signals"] for v in out.values()),
                      "calendar_tests": max(v["tests"]["calendar"] for v in out.values()),
                      "directionQualification": "base_rate_only_pending_validation",
                      "rangeSkillMetric": "historical walk-forward squared error in log log-range, not points",
                      "limitations": ["Current-vintage cross series and retrospective calendar; publication availability not verified.",
                                      "Selected individual signals and their combined model need untouched evaluation.",
                                      "Level and range skill is historical, not prospective."]},
           "inputs": {sid: (max(v) if v else None) for sid, v in series.items()}}
    write_json(OUT, _clean_json(doc), separators=(",", ":"), allow_nan=False)
    write_json(LOG, {"entries": _clean_json(archive(entries))}, separators=(",", ":"))
    for m, v in out.items():
        tested = [s["key"] for s in v["signals"] if s["tested"]] + [e["key"] for e in v["calendar"] if e["tested"]]
        log(f"bias: {m} P(up) {v['p_up']} ({v['tier']}); tested: {tested or 'none'}; range gain {v['vol']['stats'].get('gain')}; "
            f"P(high) {v['takes']['high']['p']}; touch+1 {v['touch'][1]['up_p'] if len(v['touch']) > 1 else None}")
    log(f"bias: {len(out)} markets in {time.time() - t0:.1f}s; bars t >= {t_bar:.2f} over {n_sig} signals, |z| >= {z_bar:.2f}")
    return 0


def main():
    try:
        return run()
    except Exception as e:  # the last file stays live; the run reports the failure (engine/guard.py)
        log(f"bias: unexpected error ({e!r}); the last file stays live")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
