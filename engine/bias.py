"""Daily bias for NQ and gold futures: a tested probability of an up day, the expected range and the key levels.

Every run after the New York futures close (17:00 NY) the engine re-tests a fixed set of signals on every day since
2000 (Yahoo daily futures candles, free) and publishes, for the next session:

  direction   P(next close > today's close). It starts at the long-run base rate and only moves for signals that
              passed walk-forward testing (refit every year on the years before it, scored on the year itself):
              Brier skill above the base rate overall, in both halves of the history and in the last three years.
              Calendar effects (turn of the month, Fed days, after a 2-sigma day) must differ from the base rate
              with z >= 1.96, on the same side in both halves and since 2019. Signals that fail are shown, not used.
  range       expected high-low range from the 20-day average range, with the 10th-90th percentile band of what
              followed similar readings
  levels      P(trading above today's high) and P(below today's low), from how far the close sits from each
              (in units of the average range); a one-sigma close band from 20-day volatility

Direction is close to close because Yahoo's daily futures opens are unreliable. Calls are logged in
site/data/bias/log.json and scored the next day (direction, Brier score, levels, range band).
"""
import datetime as dt
import glob
import json
import math
import os
import statistics
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
OUT = os.path.join(DATA, "bias", "current.json")
LOG = os.path.join(DATA, "bias", "log.json")
CACHE_DIR = os.path.join(HERE, "cache", "daily")
TV_DIR = os.path.join(HERE, "cache", "tv")
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
MARKETS = {"nq": ("NQ%3DF", "NQ", "Nasdaq-100 futures"), "gold": ("GC%3DF", "Gold", "COMEX gold futures")}
SESSION_END = 17   # the futures day ends 17:00 New York
FIRST_TEST_YEAR = 2006
LEAN = 0.02        # a probability within 2 points of 50% is no lean
RANGE_LOOKBACK = 1500
FOMC_KNOWN_FROM = 2010  # the calendar cache has Fed dates from 2010
WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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
        out[d.isoformat()] = [round(o, 2), round(max(h, o, c), 2), round(min(lo, o, c), 2), round(c, 2)]
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


def finished(days, now_ny):
    """Candles whose session has ended (a day's candle is final at 17:00 New York)."""
    cut = now_ny.date() if now_ny.hour >= SESSION_END else now_ny.date() - dt.timedelta(days=1)
    return [(d, v) for d, v in sorted(days.items()) if dt.date.fromisoformat(d) <= cut]


def next_session(last_iso):
    d = dt.date.fromisoformat(last_iso) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


def fomc_dates():
    """Fed decision days (New York dates) from the TradingView calendar cache."""
    out = set()
    for f in glob.glob(os.path.join(TV_DIR, "*.json")):
        try:
            c = json.load(open(f))
        except (OSError, ValueError):
            continue
        for r in c.get("rows", []) if isinstance(c, dict) else c:
            if r.get("t") == "Interest Rate" and r.get("d"):
                out.add(dt.datetime.fromisoformat(r["d"].replace("Z", "+00:00")).astimezone(NY).date().isoformat())
    return out


# ---------------------------------------------------------------- features

SIGNALS = {  # continuous signals, each tested on its own
    "mom20": "20-day momentum",
    "mom120": "6-month momentum",
    "trend200": "Distance from the 200-day average",
    "rev1": "Yesterday's move (reversal)",
    "clv": "Where the day closed in its range",
    "volreg": "Volatility regime",
}
EVENTS = {  # calendar effects about the next session
    "tom": "Turn of the month",
    "prefomc": "Day before a Fed decision",
    "fomc": "Fed decision day",
    "bigdown": "After a 2-sigma down day",
    "bigup": "After a 2-sigma up day",
}


def features(rows, fomc):
    """Per day i (known at its close): signal values and calendar flags about day i+1."""
    n = len(rows)
    c = [v[3] for _, v in rows]
    h = [v[1] for _, v in rows]
    l = [v[2] for _, v in rows]
    r = [0.0] + [math.log(c[i] / c[i - 1]) for i in range(1, n)]
    lr = [math.log(h[i] / l[i]) if l[i] > 0 and h[i] > l[i] else 0.0 for i in range(n)]
    vol, atr = [None] * n, [None] * n
    for i in range(21, n):
        vol[i] = statistics.pstdev(r[i - 19:i + 1]) or None
        atr[i] = sum(lr[i - 19:i + 1]) / 20 or None
    lvol = [math.log(v) if v else None for v in vol]
    dates = [dt.date.fromisoformat(d) for d, _ in rows]
    F = []
    for i in range(n):
        f = {}
        if vol[i]:
            v = vol[i]
            f["rev1"] = r[i] / v
            f["mom20"] = math.log(c[i] / c[i - 20]) / (v * math.sqrt(20))
            if i >= 120:
                f["mom120"] = math.log(c[i] / c[i - 120]) / (v * math.sqrt(120))
            if i >= 199:
                f["trend200"] = math.log(c[i] / (sum(c[i - 199:i + 1]) / 200)) / (v * math.sqrt(50))
            if i >= 271:
                past = [x for x in lvol[i - 250:i + 1] if x is not None]
                f["volreg"] = lvol[i] - statistics.median(past)
        f["clv"] = ((c[i] - l[i]) / (h[i] - l[i]) - 0.5) if h[i] > l[i] else 0.0
        nd = dt.date.fromisoformat(next_session(rows[i][0]))
        after = dt.date.fromisoformat(next_session(nd.isoformat()))
        k = sum(1 for x in range(1, nd.day + 1) if dt.date(nd.year, nd.month, x).weekday() < 5)
        f["tom"] = 1.0 if (after.month != nd.month or k <= 3) else 0.0
        f["prefomc"] = 1.0 if after.isoformat() in fomc else 0.0
        f["fomc"] = 1.0 if nd.isoformat() in fomc else 0.0
        f["bigdown"] = 1.0 if f.get("rev1", 0) < -2 else 0.0
        f["bigup"] = 1.0 if f.get("rev1", 0) > 2 else 0.0
        if atr[i]:
            f["dist_h"] = math.log(h[i] / c[i]) / atr[i]
            f["dist_l"] = math.log(c[i] / l[i]) / atr[i]
        F.append(f)
    return F, {"c": c, "h": h, "l": l, "r": r, "vol": vol, "atr": atr, "lr": lr, "dates": dates}


# ---------------------------------------------------------------- small models (pure python)

def _sig(x):
    return 1 / (1 + math.exp(-max(-30, min(30, x))))


def logit_fit(X, y, lam=2.0, iters=25):
    """Ridge logistic regression with an intercept; X is a list of feature lists."""
    k = len(X[0]) + 1
    b = [0.0] * k
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for x, t in zip(X, y):
            a = [1.0] + x
            p = _sig(sum(bi * ai for bi, ai in zip(b, a)))
            w = p * (1 - p)
            for u in range(k):
                g[u] += (p - t) * a[u]
                for v in range(k):
                    H[u][v] += w * a[u] * a[v]
        for u in range(1, k):
            g[u] += lam * b[u]
            H[u][u] += lam
        step = _solve(H, g)
        b = [bi - si for bi, si in zip(b, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return b


def _solve(A, g):
    n = len(g)
    M = [row[:] + [g[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        if abs(M[col][col]) < 1e-12:
            continue
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                for k in range(col, n + 1):
                    M[r][k] -= f * M[col][k]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _std(vals):
    mu = sum(vals) / len(vals)
    return mu, (math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals)) or 1.0)


def walk_forward(points, cols):
    """points: [(year, [features], y)]; refit each year on the years before it. Returns [(year, p, p0, y)]."""
    out = []
    for yr in sorted({p[0] for p in points}):
        if yr < FIRST_TEST_YEAR:
            continue
        tr = [p for p in points if p[0] < yr]
        te = [p for p in points if p[0] == yr]
        if len(tr) < 500 or not te:
            continue
        stats = [_std([p[1][j] for p in tr]) for j in range(cols)]
        z = lambda x: [(x[j] - stats[j][0]) / stats[j][1] for j in range(cols)]
        b = logit_fit([z(p[1]) for p in tr], [p[2] for p in tr])
        p0 = sum(p[2] for p in tr) / len(tr)
        for p in te:
            out.append((yr, _sig(b[0] + sum(bi * xi for bi, xi in zip(b[1:], z(p[1])))), p0, p[2]))
    return out


def skill(rows):
    if not rows:
        return None
    bs = sum((p - y) ** 2 for _, p, _, y in rows)
    b0 = sum((p0 - y) ** 2 for _, _, p0, y in rows)
    return 1 - bs / b0 if b0 else None


T_NEEDED = 2.64  # one-sided 5% after a Bonferroni split over the six direction signals


def judge(wf, t_needed=T_NEEDED):
    """Out-of-sample Brier skill over the base rate, with a Diebold-Mariano t-test on the score differences.
    Passing needs t >= t_needed and positive skill in both halves and in the last three years."""
    if len(wf) < 400:
        return {"skill": None, "tested": False}
    half = len(wf) // 2
    last = max(r[0] for r in wf)
    s, s1, s2 = skill(wf), skill(wf[:half]), skill(wf[half:])
    s3 = skill([r for r in wf if r[0] >= last - 2])
    d = [(p0 - y) ** 2 - (p - y) ** 2 for _, p, p0, y in wf]
    mu, sd = _std(d)
    t = mu / (sd / math.sqrt(len(d))) if sd else 0.0
    ok = t >= t_needed and all(x is not None and x > 0 for x in (s1, s2, s3))
    return {"skill": round(s, 4), "t": round(t, 2), "halves": [round(s1, 4), round(s2, 4)], "recent": round(s3, 4),
            "tested": bool(ok)}


def _z(k, n, p):
    return (k / n - p) / math.sqrt(p * (1 - p) / n) if n and 0 < p < 1 else 0.0


# ---------------------------------------------------------------- the daily read

def study(rows, F, S):
    n = len(rows)
    y = [None] * n
    for i in range(n - 1):
        y[i] = 1 if S["c"][i + 1] > S["c"][i] else 0
    known = [t for t in y if t is not None]
    base = sum(known) / max(1, len(known))
    years = [d.year for d in S["dates"]]
    out = {"base_up": round(base, 3), "days": len(known), "since": rows[0][0][:4], "signals": {}, "events": {}}
    for key in SIGNALS:
        pts = [(years[i], [F[i][key]], y[i]) for i in range(n) if y[i] is not None and key in F[i]]
        res = judge(walk_forward(pts, 1))
        res["n"] = len(pts)
        out["signals"][key] = res
    half_year = years[n // 2]
    for key in EVENTS:
        lo_year = FOMC_KNOWN_FROM if key in ("prefomc", "fomc") else 0
        allow = [i for i in range(n) if y[i] is not None and years[i] >= lo_year]
        sel = [i for i in allow if F[i].get(key)]
        if len(sel) < 20:
            out["events"][key] = {"n": len(sel), "tested": False}
            continue
        b = sum(y[i] for i in allow) / len(allow)
        k = sum(y[i] for i in sel)
        rate = lambda ix: sum(y[i] for i in ix) / len(ix) if ix else None
        ra = rate([i for i in sel if years[i] < half_year])
        rb = rate([i for i in sel if years[i] >= half_year])
        rr = rate([i for i in sel if years[i] >= 2019])
        z = _z(k, len(sel), b)
        same = all(x is not None and (x - b) * (k / len(sel) - b) > 0 for x in (ra, rb, rr))
        r3 = lambda x: round(x, 3) if x is not None else None
        out["events"][key] = {"n": len(sel), "up": round(k / len(sel), 3), "base": round(b, 3), "z": round(z, 2),
                              "halves": [r3(ra), r3(rb)], "recent": r3(rr),
                              "tested": bool(abs(z) >= 1.96 and same and len(sel) >= 60)}
    return out, y


def direction_today(F, y, st, i_last):
    """P(up) for the next session: the base rate, moved only by tested signals and tested calendar effects."""
    used = [k for k, v in st["signals"].items() if v.get("tested") and k in F[i_last]]
    p, why = st["base_up"], []
    if used:
        pts = [([F[i][k] for k in used], y[i]) for i in range(len(y)) if y[i] is not None and all(k in F[i] for k in used)]
        stats = [_std([x[j] for x, _ in pts]) for j in range(len(used))]
        z = lambda x: [(x[j] - stats[j][0]) / stats[j][1] for j in range(len(used))]
        b = logit_fit([z(x) for x, _ in pts], [t for _, t in pts])
        p = _sig(b[0] + sum(bi * xi for bi, xi in zip(b[1:], z([F[i_last][k] for k in used]))))
        why += used
    for k, v in st["events"].items():
        if v.get("tested") and F[i_last].get(k):
            p += v["up"] - v["base"]  # shift by the effect's measured difference from its base rate
            why.append(k)
    p = min(0.9, max(0.1, p))
    bias = "long" if p >= 0.5 + LEAN else "short" if p <= 0.5 - LEAN else "neutral"
    return round(p, 3), bias, why


def levels_model(F, S, n):
    """P(next day trades above today's high / below today's low), from the close's distance to each."""
    out = {}
    years = [d.year for d in S["dates"]]
    for side, key in (("high", "dist_h"), ("low", "dist_l")):
        pts = []
        for i in range(n - 1):
            if key in F[i]:
                hit = S["h"][i + 1] > S["h"][i] if side == "high" else S["l"][i + 1] < S["l"][i]
                pts.append((years[i], [F[i][key]], 1 if hit else 0))
        res = judge(walk_forward(pts, 1), t_needed=1.65)
        mu, sd = _std([p[1][0] for p in pts])
        b = logit_fit([[(p[1][0] - mu) / sd] for p in pts], [p[2] for p in pts])
        out[side] = {"fit": (b, mu, sd), "skill": res.get("skill"), "tested": res.get("tested"),
                     "base": round(sum(p[2] for p in pts) / len(pts), 3)}
    return out


def range_model(S, n):
    """Quantiles of next-day range / 20-day average range, over the recent past."""
    ratios = sorted(S["lr"][i + 1] / S["atr"][i] for i in range(max(0, n - 1 - RANGE_LOOKBACK), n - 1) if S["atr"][i])
    q = lambda f: ratios[min(len(ratios) - 1, int(f * len(ratios)))]
    return {"p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "n": len(ratios)}


def read(m, rows, fomc):
    F, S = features(rows, fomc)
    n = len(rows)
    st, y = study(rows, F, S)
    i = n - 1
    p, bias, why = direction_today(F, y, st, i)
    lv = levels_model(F, S, n)
    rg = range_model(S, n)
    c, h, l, atr, vol = S["c"][i], S["h"][i], S["l"][i], S["atr"][i], S["vol"][i]
    takes = {}
    for side, key in (("high", "dist_h"), ("low", "dist_l")):
        b, mu, sd = lv[side]["fit"]
        takes[side] = {"p": round(_sig(b[0] + b[1] * (F[i][key] - mu) / sd), 3), "base": lv[side]["base"],
                       "skill": lv[side]["skill"], "tested": lv[side]["tested"]}
    pts = lambda frac: round(c * (math.exp(frac * atr) - 1), 2)
    board = []
    for k, label in SIGNALS.items():
        v, s = F[i].get(k), st["signals"][k]
        board.append({"key": k, "label": label, "value": round(v, 2) if v is not None else None,
                      "skill": s.get("skill"), "t": s.get("t"), "tested": s.get("tested"), "used": k in why})
    cal = []
    for k, label in EVENTS.items():
        e = st["events"][k]
        cal.append({"key": k, "label": label, "active": bool(F[i].get(k)), "n": e.get("n"), "up": e.get("up"),
                    "base": e.get("base"), "z": e.get("z"), "tested": e.get("tested"), "used": k in why})
    yd = rows[-1][0]
    return {"candle": yd, "day_name": WD[dt.date.fromisoformat(yd).weekday()],
            "p_up": p, "base_up": st["base_up"], "bias": bias, "drivers": why, "tier": "tested" if why else "base",
            "levels": {"high": h, "low": l, "close": c}, "takes": takes,
            "range": {"points": pts(rg["p50"]), "lo": pts(rg["p10"]), "hi": pts(rg["p90"]), "n": rg["n"]},
            "band": {"lo": round(c * math.exp(-vol), 2), "hi": round(c * math.exp(vol), 2), "sigma": round(c * (math.exp(vol) - 1), 2)},
            "signals": board, "calendar": cal, "history": {"days": st["days"], "since": st["since"]}}


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
    return out


def news_today(day_iso):
    try:
        ev = json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]
    except (OSError, ValueError, KeyError):
        return []
    return [{"time": e.get("time"), "title": e.get("title"), "impact": e.get("impact")}
            for e in ev if e.get("date") == day_iso and e.get("impact") == "high"]


def run(now=None, fetch=download):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ny = now.astimezone(NY)
    try:
        entries = json.load(open(LOG)).get("entries", [])
    except (OSError, ValueError):
        entries = []
    entries = [e for e in entries if "p_up" in e]  # calls from the retired candle-pattern version are dropped
    fomc = fomc_dates()
    markets, rows_by = {}, {}
    for m, (_, short, name) in MARKETS.items():
        c = sync(m, now, fetch)
        rows = finished(c["days"], now_ny)
        rows_by[m] = rows
        if len(rows) < 800:
            log(f"bias: not enough {m} history yet")
            continue
        r = read(m, rows, fomc)
        r.update({"name": short, "full": name})
        markets[m] = r
        if not any(e["market"] == m and e["candle"] == r["candle"] for e in entries):
            entries.append({"market": m, "candle": r["candle"], "for": next_session(r["candle"]), "bias": r["bias"],
                            "p_up": r["p_up"], "base_up": r["base_up"], "tier": r["tier"],
                            "p_high": r["takes"]["high"]["p"], "p_low": r["takes"]["low"]["p"],
                            "range_lo": r["range"]["lo"], "range_hi": r["range"]["hi"],
                            "logged": now.isoformat(timespec="minutes")})
    if not markets:
        log("bias: nothing to publish; the last file stays live")
        return 1
    score_log(rows_by, entries)
    day = max(next_session(v["candle"]) for v in markets.values())
    live = {m: summary([e for e in entries if e["market"] == m]) for m in markets}
    doc = {"asof": now.isoformat(timespec="minutes"), "for": day, "markets": markets, "news": news_today(day),
           "live": live, "method": {"first_test_year": FIRST_TEST_YEAR, "lean": LEAN}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    with open(LOG, "w") as fh:
        json.dump({"entries": entries[-3000:]}, fh, separators=(",", ":"))
    for m, v in markets.items():
        tested = [s["key"] for s in v["signals"] if s["tested"]] + [e["key"] for e in v["calendar"] if e["tested"]]
        log(f"bias: {m} P(up) {v['p_up']} ({v['bias']}, {v['tier']}) for {day}; tested: {tested or 'none'}; "
            f"P(high) {v['takes']['high']['p']} P(low) {v['takes']['low']['p']}")
    return 0


def main():
    try:
        return run()
    except Exception as e:  # never break the publish job
        log(f"bias: unexpected error ({e!r}); the last file stays live")
        return 0


if __name__ == "__main__":
    sys.exit(main())
