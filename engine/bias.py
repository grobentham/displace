"""Daily bias for eight futures markets: a tested probability of an up day, a volatility-model range, touch
probabilities, level odds, session statistics and calibration, each with its out-of-sample record.

Runs after the New York futures close (17:00 NY). Free data only: Yahoo daily futures candles since 2000, FRED
(implied volatility indices, credit spreads, real yields, the dollar, the 2-year yield) and the release calendar.

  direction   P(next close > today's close). Starts at the long-run base rate and moves only for signals that pass
              walk-forward testing: out-of-sample Brier skill with a Diebold-Mariano t above a Bonferroni bar for
              the number of signals tried, and positive skill in both halves and the last three years. Calendar
              effects need |z| >= 1.96 on the same side in both halves and since 2019.
  range       a HAR model of the log daily range (yesterday, last week, last month, implied volatility, a news-day
              flag for the next session, Mondays), refit every year and compared with a 20-day average.
  touch       how often the next day reached the close +/- 0.5, 1, 1.5 and 2 forecast standard deviations.
  levels      P(trading above today's high / below today's low) from the close's distance to each.
  sessions    overnight vs New York session behaviour and an intraday momentum test (NQ and gold, hourly bars).

FRED values are used one day late in both the tests and the live read, because FRED publishes a day's close the
next morning. Direction is close to close: Yahoo's daily futures opens are unreliable.
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

import quant as Q

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
SERIES = ["VIXCLS", "VXNCLS", "RVXCLS", "GVZCLS", "OVXCLS", "VXVCLS", "BAMLH0A0HYM2", "DFII10", "DTWEXBGS", "DGS2"]

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
          "bigdown": "After a 2-sigma down day", "bigup": "After a 2-sigma up day"}
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
        if not (o and h and lo and c):
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


def next_session(last_iso):
    d = dt.date.fromisoformat(last_iso) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def lagged(keys, series):
    """Value of a daily series from the last date strictly before each key (published by the next morning)."""
    if not series:
        return np.full(len(keys), np.nan)
    sd = sorted(series)
    out, j, last = np.full(len(keys), np.nan), 0, np.nan
    for i, k in enumerate(keys):
        while j < len(sd) and sd[j] < k:
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


def build(rows, tiers, fomc):
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
    F["ev2"] = np.array([1.0 if tiers.get(d) == 1 else 0.0 for d in nxt])
    F["mon"] = np.array([1.0 if dt.date.fromisoformat(d).weekday() == 0 else 0.0 for d in nxt])
    F["dist_h"] = np.log(h / c) / atr
    F["dist_l"] = np.log(c / l) / atr
    dates = [dt.date.fromisoformat(k) for k in keys]
    S = {"keys": keys, "o": o, "h": h, "l": l, "c": c, "r": r, "rg": rg, "vol": vol, "atr": atr,
         "years": np.array([d.year for d in dates])}
    return F, S


def cross_features(F, S, series, iv_sid):
    keys = S["keys"]
    n = len(keys)
    with np.errstate(divide="ignore", invalid="ignore"):
        if iv_sid:
            liv = np.log(lagged(keys, series.get(iv_sid)))
            med = np.array([np.nanmedian(liv[i - 250:i + 1]) if i >= 250 and np.isfinite(liv[i - 250:i + 1]).sum() > 100 else np.nan for i in range(n)])
            F["iv_level"] = liv - med
            F["iv_chg5"] = np.r_[np.full(5, np.nan), liv[5:] - liv[:-5]]
            F["iv"] = liv
        vix, vxv = lagged(keys, series.get("VIXCLS")), lagged(keys, series.get("VXVCLS"))
        F["term"] = np.log(vix / vxv)
        for name, sid, how in (("hy5", "BAMLH0A0HYM2", "diff"), ("ry5", "DFII10", "diff"), ("usd5", "DTWEXBGS", "log"),
                               ("y2_5", "DGS2", "diff")):
            v = lagged(keys, series.get(sid))
            F[name] = np.r_[np.full(5, np.nan), (np.log(v[5:] / v[:-5]) if how == "log" else v[5:] - v[:-5])]


# ---------------------------------------------------------------- models

def direction(F, S, signals):
    c, years = S["c"], S["years"]
    n = len(c)
    y = np.r_[(c[1:] > c[:-1]).astype(float), np.nan]
    known = ~np.isnan(y)
    base = float(y[known].mean())
    t_req = Q.t_needed(len(signals))
    out = {}
    for k in signals:
        x = F[k]
        m = known & np.isfinite(x)
        w = Q.walk_forward_logit(years[m], x[m][:, None], y[m], first=FIRST_TEST_YEAR)
        res = Q.judge(w, t_req)
        res["n"] = int(m.sum())
        out[k] = res
    ev = {}
    half_year = years[n // 2]
    for k in EVENTS:
        lo = FOMC_KNOWN_FROM if k in ("prefomc", "fomc") else 0
        allow = known & (years >= lo)
        sel = allow & (F[k] == 1)
        if sel.sum() < 20:
            ev[k] = {"n": int(sel.sum()), "tested": False}
            continue
        b, rate = float(y[allow].mean()), float(y[sel].mean())
        z = (rate - b) / math.sqrt(b * (1 - b) / sel.sum())
        parts = [y[sel & (years < half_year)], y[sel & (years >= half_year)], y[sel & (years >= 2019)]]
        same = all(len(p) and (p.mean() - b) * (rate - b) > 0 for p in parts)
        rr = lambda a: round(float(a.mean()), 3) if len(a) else None
        ev[k] = {"n": int(sel.sum()), "up": round(rate, 3), "base": round(b, 3), "z": round(z, 2),
                 "halves": [rr(parts[0]), rr(parts[1])], "recent": rr(parts[2]),
                 "tested": bool(abs(z) >= 1.96 and same and sel.sum() >= 60)}
    i = n - 1
    used = [k for k in signals if out[k].get("tested") and np.isfinite(F[k][i])]
    p = base
    if used:
        Xa = np.column_stack([F[k] for k in used])
        m = known & np.isfinite(Xa).all(1)
        (Xt, Xe), _ = Q.standardize(Xa[m], Xa[i:i + 1])
        b = Q.logit_fit(Xt, y[m])
        p = float(Q.sig(np.r_[1.0, Xe[0]] @ b))
    why = list(used)
    for k, v in ev.items():
        if v.get("tested") and F[k][i] == 1:
            p += v["up"] - v["base"]
            why.append(k)
    p = min(0.9, max(0.1, p))
    bias = "long" if p >= 0.5 + LEAN else "short" if p <= 0.5 - LEAN else "neutral"
    return {"p_up": round(p, 3), "base_up": round(base, 3), "bias": bias, "drivers": why, "tier": "tested" if why else "base",
            "signals": out, "events": ev, "t_req": round(t_req, 2), "days": int(known.sum())}


def levels(F, S):
    """P(next day above today's high / below today's low), with out-of-sample skill and reliability."""
    h, l, years = S["h"], S["l"], S["years"]
    n = len(h)
    out = {}
    for side, key in (("high", "dist_h"), ("low", "dist_l")):
        y = np.r_[((h[1:] > h[:-1]) if side == "high" else (l[1:] < l[:-1])).astype(float), np.nan]
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
    """HAR on the log daily range, compared out of sample with the 20-day average; touch ladder from it."""
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
    base = np.log(_roll(rg, 20, np.nanmean))
    good = np.where(np.isfinite(Fm).all(1))[0]
    train_from = max(EVENTS_FROM, int(years[good[0]]) + 1) if len(good) else EVENTS_FROM
    wf = Q.har_walk_forward(years, Fm, y, base, first=train_from + 2, train_from=train_from)
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
    r_next = np.r_[r[1:], np.nan][ok]
    scale = float(math.sqrt(np.nanmean(r_next ** 2) / np.mean(fitted ** 2)))
    sigma = scale * math.exp(pred)
    touch = []
    if len(wf["y"]):
        idx = wf["idx"].astype(int)
        keep = idx + 1 < n
        idx, sig_hist = idx[keep], scale * np.exp(wf["pred"][keep])
        c, h, l = S["c"], S["h"], S["l"]
        for k in TOUCH_K:
            touch.append({"k": k, "up_p": round(float(np.mean(np.log(h[idx + 1] / c[idx]) >= k * sig_hist)), 3),
                          "dn_p": round(float(np.mean(np.log(c[idx] / l[idx + 1]) >= k * sig_hist)), 3)})
    mult = {nm: round(float(math.exp(bb)), 3) for nm, bb in zip(names, b[1:]) if nm in ("big release", "other major release", "Monday")}
    return {"pred": pred, "q": [float(x) for x in q], "sigma": sigma, "stats": stats, "touch": touch, "inputs": names,
            "multipliers": mult}


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
    days = sorted(by)
    ov, dy, mx, my = [], [], [], []
    for a, b in zip(days, days[1:]):
        A, B = by[a], by[b]
        if 15 not in A or not all(k in B for k in (8, 9, 14, 15)):
            continue
        prev = A[15][1]  # the 16:00 close
        c9, c10, c15, c16 = B[8][1], B[9][1], B[14][1], B[15][1]
        ov.append(math.log(c9 / prev))
        dy.append(math.log(c16 / c9))
        mx.append(math.log(c10 / prev))
        my.append(math.log(c16 / c15))
    if len(ov) < 120:
        return None
    ov, dy, mx, my = map(np.array, (ov, dy, mx, my))
    n = len(ov)
    agree = (np.sign(mx) == np.sign(my)) & (mx != 0) & (my != 0)
    k = int(agree.sum())
    z = (k / n - 0.5) / math.sqrt(0.25 / n)
    h1, h2 = float(agree[: n // 2].mean()), float(agree[n // 2:].mean())
    up = ov > 0
    rate = lambda a: round(float((a > 0).mean()), 3)
    tstat = lambda a: round(float(a.mean() / (a.std() / math.sqrt(len(a)))), 2)
    zrate = lambda a: round(float(((a > 0).mean() - 0.5) / math.sqrt(0.25 / len(a))), 2)
    halves = lambda a: [round(float((a[: len(a) // 2] > 0).mean()), 3), round(float((a[len(a) // 2:] > 0).mean()), 3)]
    return {"days": n, "overnight_up": rate(ov), "day_up": rate(dy),
            "overnight_t": tstat(ov), "day_t": tstat(dy), "overnight_z": zrate(ov), "day_z": zrate(dy),
            "overnight_halves": halves(ov), "day_halves": halves(dy),
            "overnight_bp": round(float(ov.mean() * 1e4), 1), "day_bp": round(float(dy.mean() * 1e4), 1),
            "day_up_after_up": round(float((dy[up] > 0).mean()), 3), "day_up_after_down": round(float((dy[~up] > 0).mean()), 3),
            "momentum": {"agree": round(k / n, 3), "z": round(z, 2), "corr": round(float(np.corrcoef(mx, my)[0, 1]), 3),
                         "halves": [round(h1, 3), round(h2, 3)], "tested": bool(z >= 1.96 and h1 > 0.5 and h2 > 0.5)}}


def read(m, rows, series, tiers, fomc):
    sym, short, full, pv, micro, iv_sid, dp, group = MARKETS[m]
    F, S = build(rows, tiers, fomc)
    cross_features(F, S, series, iv_sid)
    sigs = list(PRICE_SIGNALS) + [k for k in CROSS_FOR[group] if k in F and np.isfinite(F[k]).sum() > 1500]
    D = direction(F, S, sigs)
    L = levels(F, S)
    V = volatility(F, S, iv_ok=bool(iv_sid))
    i = len(rows) - 1
    c, h, l = float(S["c"][i]), float(S["h"][i]), float(S["l"][i])
    pts = lambda x: round(c * (math.exp(math.exp(x)) - 1), 6)  # x is the log of the log-range
    yd = rows[-1][0]
    nxt = next_session(yd)
    labels = {**PRICE_SIGNALS, **CROSS_SIGNALS}
    val = lambda a: None if not np.isfinite(a) else round(float(a), 2)
    board = [{"key": k, "label": labels[k], "value": val(F[k][i]), "skill": D["signals"][k].get("skill"),
              "t": D["signals"][k].get("t"), "tested": D["signals"][k].get("tested"), "used": k in D["drivers"],
              "kind": "price" if k in PRICE_SIGNALS else "cross"} for k in sigs]
    cal = [{"key": k, "label": lab, "active": bool(F[k][i] == 1), "n": D["events"][k].get("n"), "up": D["events"][k].get("up"),
            "base": D["events"][k].get("base"), "z": D["events"][k].get("z"), "tested": D["events"][k].get("tested"),
            "used": k in D["drivers"]} for k, lab in EVENTS.items()]
    return {"name": short, "full": full, "pv": pv, "micro": micro, "dp": dp, "group": group,
            "candle": yd, "day_name": WD[dt.date.fromisoformat(yd).weekday()],
            "p_up": D["p_up"], "base_up": D["base_up"], "bias": D["bias"], "drivers": D["drivers"], "tier": D["tier"], "t_req": D["t_req"],
            "levels": {"high": h, "low": l, "close": c},
            "takes": {s: {k: v for k, v in L[s].items() if k != "calib"} for s in L},
            "range": {"points": pts(V["pred"] + V["q"][1]), "lo": pts(V["pred"] + V["q"][0]), "hi": pts(V["pred"] + V["q"][2])},
            "band": {"lo": round(c * math.exp(-V["sigma"]), 6), "hi": round(c * math.exp(V["sigma"]), 6), "sigma": round(c * (math.exp(V["sigma"]) - 1), 6)},
            "touch": [{**t, "up": round(c * math.exp(t["k"] * V["sigma"]), 6), "dn": round(c * math.exp(-t["k"] * V["sigma"]), 6)} for t in V["touch"]],
            "vol": {"stats": V["stats"], "inputs": V["inputs"], "multipliers": V["multipliers"],
                    "news": "big" if tiers.get(nxt) == 2 else "major" if tiers.get(nxt) == 1 else None},
            "calib": {"high": L["high"]["calib"], "low": L["low"]["calib"]},
            "signals": board, "calendar": cal, "sessions": sessions(m) if m in ("nq", "gold") else None,
            "history": {"days": D["days"], "since": rows[0][0][:4]}}


# ---------------------------------------------------------------- live record

def score_log(rows_by, entries):
    for e in entries:
        if e.get("scored"):
            continue
        rows = rows_by.get(e["market"]) or []
        days = dict(rows)
        nxt = next((d for d, _ in rows if d > e["candle"]), None)
        if not nxt or e["candle"] not in days:
            continue
        a, b = days[e["candle"]], days[nxt]
        up = 1 if b[3] > a[3] else 0
        e.update({"day": nxt, "scored": 1, "up": up, "brier": round((e["p_up"] - up) ** 2, 4),
                  "highTaken": int(b[1] > a[1]), "lowTaken": int(b[2] < a[2]),
                  "inRange": int(e["range_lo"] <= b[1] - b[2] <= e["range_hi"])})
        if e.get("up1") is not None:
            e["up1Hit"], e["dn1Hit"] = int(b[1] >= e["up1"]), int(b[2] <= e["dn1"])
        if e["bias"] != "neutral":
            e["hit"] = int((up == 1) == (e["bias"] == "long"))
    return entries


def summary(entries):
    done = [e for e in entries if e.get("scored")]
    calls = [e for e in done if "hit" in e]
    out = {"days": len(done), "calls": len(calls), "hits": sum(e["hit"] for e in calls),
           "inRange": sum(e["inRange"] for e in done), "recent": done[-10:][::-1]}
    if done:
        out["brier"] = round(sum(e["brier"] for e in done) / len(done), 4)
        out["baseBrier"] = round(sum((e["base_up"] - e["up"]) ** 2 for e in done) / len(done), 4)
        lv = [(e["p_high"], e["highTaken"]) for e in done] + [(e["p_low"], e["lowTaken"]) for e in done]
        out["levelBrier"] = round(sum((p - y) ** 2 for p, y in lv) / len(lv), 4)
    return out


def news_today(day_iso):
    try:
        ev = json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]
    except (OSError, ValueError, KeyError):
        return []
    return [{"time": e.get("time"), "title": e.get("title"), "impact": e.get("impact")}
            for e in ev if e.get("date") == day_iso and e.get("impact") == "high"]


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def run(now=None, fetch=download, fetch_series=fred_download, markets=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ny = now.astimezone(NY)
    t0 = time.time()
    try:
        entries = json.load(open(LOG)).get("entries", [])
    except (OSError, ValueError):
        entries = []
    entries = [e for e in entries if "p_up" in e]
    series = {sid: sync_series(sid, now, fetch_series) for sid in SERIES}
    tiers, fomc = calendar_tiers()
    out, rows_by = {}, {}
    for m in markets or MARKETS:
        try:
            c = sync(m, now, fetch)
            rows = finished(c["days"], now_ny)
            rows_by[m] = rows
            if len(rows) < 800:
                log(f"bias: not enough {m} history yet ({len(rows)} days)")
                continue
            r = read(m, rows, series, tiers, fomc)
        except Exception as e:  # one market failing never blocks the others
            log(f"bias: {m} failed ({e!r})")
            continue
        out[m] = r
        if not any(e["market"] == m and e["candle"] == r["candle"] for e in entries):
            t1 = next((t for t in r["touch"] if t["k"] == 1.0), None)
            entries.append({"market": m, "candle": r["candle"], "for": next_session(r["candle"]), "bias": r["bias"],
                            "p_up": r["p_up"], "base_up": r["base_up"], "tier": r["tier"],
                            "p_high": r["takes"]["high"]["p"], "p_low": r["takes"]["low"]["p"],
                            "range_lo": r["range"]["lo"], "range_hi": r["range"]["hi"],
                            "up1": t1["up"] if t1 else None, "dn1": t1["dn"] if t1 else None,
                            "logged": now.isoformat(timespec="minutes")})
    if not out:
        log("bias: nothing to publish; the last file stays live")
        return 1
    score_log(rows_by, entries)
    day = max(next_session(v["candle"]) for v in out.values())
    live = {m: summary([e for e in entries if e["market"] == m]) for m in out}
    doc = {"asof": now.isoformat(timespec="minutes"), "for": day, "markets": out, "order": [m for m in MARKETS if m in out],
           "news": news_today(day), "live": live, "method": {"first_test_year": FIRST_TEST_YEAR, "lean": LEAN},
           "inputs": {sid: (max(v) if v else None) for sid, v in series.items()}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(_clean(doc), fh, separators=(",", ":"), allow_nan=False)
    with open(LOG, "w") as fh:
        json.dump({"entries": _clean(entries[-6000:])}, fh, separators=(",", ":"))
    for m, v in out.items():
        tested = [s["key"] for s in v["signals"] if s["tested"]] + [e["key"] for e in v["calendar"] if e["tested"]]
        log(f"bias: {m} P(up) {v['p_up']} ({v['bias']}, {v['tier']}); tested: {tested or 'none'}; "
            f"range model gain {v['vol']['stats'].get('gain')}; P(high) {v['takes']['high']['p']}")
    log(f"bias: {len(out)} markets in {time.time() - t0:.1f}s")
    return 0


def main():
    try:
        return run()
    except Exception as e:  # never break the publish job
        log(f"bias: unexpected error ({e!r}); the last file stays live")
        return 0


if __name__ == "__main__":
    sys.exit(main())
