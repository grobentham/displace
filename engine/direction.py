"""Direction engine v2.

Decides which way gold, the dollar, EUR/USD, the Nasdaq 100 and the 2- and 10-year yields tend to close on
release day, and publishes a direction only where it has been proven on releases the model had not seen.

Method
  1. History since 2010 from first-published figures (FRED/ALFRED vintages, no hindsight revisions).
  2. Surprise for the headline AND the key components (core and headline CPI; payrolls, unemployment and
     wages; retail sales and the ex-autos measure...) against the consensus where recorded, otherwise the
     recent trend. Each is scaled by the typical surprise size known at the time; together they form one
     composite surprise score.
  3. Market regime at the time of each release: Fed hiking, cutting or on hold (6-month change in the fed
     funds rate), inflation above or below 3% (core CPI year on year), and each market's 5-day trend into it.
     Days with another high-impact release are down-weighted.
  4. Two models: (A) a tally of release-day closes by surprise bucket and (B) a ridge-regularised logistic
     regression on the surprise, its interaction with the regime, and the trend. Both weight recent years more
     (half-life 4 years). They are blended with a weight learned from which one predicted better out of sample.
  5. Calibration: the raw probability is shrunk toward 50% by a factor learned from the model's own past
     out-of-sample record, so that a stated 70% has historically meant about 70%.
  6. Walk-forward test: every past release is replayed using only data available before it.
     A rule (release x market) is proven only if:
       - at least 30 out-of-sample calls with a hit rate of 55% or more,
       - it survives a false-discovery-rate correction (Benjamini-Hochberg, 10%) across every rule tested,
       - its probabilities beat a coin flip (Brier skill > 0),
       - it worked in both the earlier and the later half of the test,
       - its most recent 20 calls (tested and live) are still right at least half the time (circuit breaker),
       - the market really responds to the surprise: higher and lower surprises led to clearly different outcomes.
  7. Every live call is logged, scored at that day's close and fed back into the circuit breaker.
"""
import bisect
import datetime as dt
import math
import re
import statistics

START = "2010-01-01"
HOT = 0.35
HALF_LIFE = 4.0
MIN_N = 12
WARMUP = 36
CALL_EDGE = 0.06
PROVEN_CALLS, PROVEN_RATE, FDR_Q, BREAKER_N = 30, 0.55, 0.10, 20

# kind: headline (series, transform, sign), components [(series, transform, sign)], metric, naive window, figure mult
MODELS = {
    "cpi": dict(head=("CPILFESL", "pct"), comps=[("CPIAUCSL", "pct", 1)], metric="core CPI m/m", window=3, mult=1),
    "ppi": dict(head=("PPIFIS", "pct"), comps=[("PPIFES", "pct", 1)], metric="PPI final demand m/m", window=3, mult=1),
    "pce": dict(head=("PCEPILFE", "pct"), comps=[("PCEPI", "pct", 1)], metric="core PCE m/m", window=3, mult=1),
    "nfp": dict(head=("PAYEMS", "diff"), comps=[("UNRATE", "level", -1), ("CES0500000003", "pct", 1)],
                metric="payrolls change", window=3, mult=1e-3),
    "retail": dict(head=("RSAFS", "pct"), comps=[("RSFSXMV", "pct", 1)], metric="retail sales m/m", window=3, mult=1),
    "durables": dict(head=("DGORDER", "pct"), comps=[("ADXTNO", "pct", 1)], metric="durable goods orders m/m", window=3, mult=1),
    "claims": dict(head=("ICSA", "level"), comps=[], metric="initial jobless claims", window=4, mult=1),
    "jolts": dict(head=("JTSJOL", "level"), comps=[], metric="job openings", window=3, mult=1e-3),
    "gdp": dict(head=("A191RL1Q225SBEA", "level"), comps=[], metric="real GDP, annualized", window=3, mult=1),
    "umich": dict(head=("UMCSENT", "level"), comps=[("MICH", "level", 1)], metric="consumer sentiment", window=3, mult=1),
    "homes": dict(head=("HSN1F", "level"), comps=[], metric="new home sales", window=3, mult=1e-3),
}
ASSETS = {  # key: (FRED series or None for gold, unit, name, invert)
    "gold": (None, "pct", "Gold", False),
    "usd": ("DTWEXBGS", "pct", "US dollar", False),
    "eur": ("DEXUSEU", "pct", "EUR/USD", False),
    "nq": ("NASDAQ100", "pct", "Nasdaq 100", False),
    "y2": ("DGS2", "bp", "2-year yield", False),
    "y10": ("DGS10", "bp", "10-year yield", False),
}
BINS = ("hot", "cool", "inline")
BASIS = {}  # kind -> name of the recorded expectation, e.g. {"cpi": "nowcast"}; set by the caller
NF = 6  # logistic features: 1, z, z*infl, z*hike, z*cut, trend


def d_(s):
    return dt.date.fromisoformat(s[:10])


def figure(s, mult=1.0):
    """'165K' -> 165000 * mult, '0.3%' -> 0.3. None if unreadable."""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("−", "-").strip()
    m = re.search(r"-?\d+(\.\d+)?", t)
    if not m:
        return None
    v = float(m.group(0))
    tail = t[m.end():m.end() + 2].upper()
    v *= 1e3 if tail.startswith("K") else 1e6 if tail.startswith("M") else 1e9 if tail.startswith("B") else 1
    return v * mult


def transform(obs, mode):
    out = []
    for i, (d, v, rt) in enumerate(obs):
        if mode == "pct":
            if i and obs[i - 1][1]:
                out.append((d, (v / obs[i - 1][1] - 1) * 100, rt))
        elif mode == "diff":
            if i:
                out.append((d, v - obs[i - 1][1], rt))
        else:
            out.append((d, v, rt))
    return out


def bucket(z):
    return "hot" if z >= HOT else "cool" if z <= -HOT else "inline"


def scale_of(s):
    s = [abs(x) for x in s]
    return (statistics.median(s) * 1.4826 or None) if len(s) >= MIN_N else None


def surprises(vals, window, records=None, kind=None, recorded_only=False):
    """{release date: (z, value, expected, basis)} with walk-forward scaling.
    recorded_only: use only releases that have a recorded expectation (e.g. a nowcast), so every surprise in
    the sample, and its scale, is measured the same way."""
    out, hist = {}, []
    for i, (period, x, rt) in enumerate(vals):
        if not rt or i < window:
            continue
        fc = records.get((kind, rt)) if records else None
        if recorded_only and fc is None:
            continue
        exp_ = fc if fc is not None else sum(v[1] for v in vals[i - window:i]) / window
        s = x - exp_
        sc = scale_of(hist)
        hist.append(s)
        if sc and rt >= START:
            out[rt] = (max(-6, min(6, s / sc)), x, exp_, BASIS.get(kind, "consensus") if fc is not None else "trend", period)
    return out


class Px:
    """Daily closes for one market."""

    def __init__(self, rows, unit):
        self.c = dict(rows)
        self.d = sorted(self.c)
        self.unit = unit

    def _chg(self, a, b):
        if self.unit == "bp":
            return (b - a) * 100
        return (b / a - 1) * 100 if a else None

    def move(self, day):
        if day not in self.c:
            return None
        i = bisect.bisect_left(self.d, day)
        return self._chg(self.c[self.d[i - 1]], self.c[day]) if i else None

    def trend(self, day, n=5):
        i = bisect.bisect_left(self.d, day)
        if i < n + 1:
            return 0
        m = self._chg(self.c[self.d[i - 1 - n]], self.c[self.d[i - 1]])
        return 0 if m is None else (1 if m > 0 else -1)


def regimes(fetch_obs):
    """Functions date -> regime flags, built from data known at the time."""
    ff = fetch_obs("DFF", "2009-01-01") or []
    ffd = [o[0] for o in ff]
    core = transform(fetch_obs("CPILFESL", "2008-01-01", initial=True) or [], "level")
    lv = {p: v for p, v, _ in core}
    yoy = []
    for p, v, rt in core:
        y0 = (d_(p).replace(year=d_(p).year - 1)).isoformat()
        if y0 in lv and rt:
            yoy.append((rt, (v / lv[y0] - 1) * 100))
    yoy.sort()

    def fed(day):
        if not ff:
            return 0
        i = bisect.bisect_left(ffd, day) - 1
        j = bisect.bisect_left(ffd, (d_(day) - dt.timedelta(days=182)).isoformat())
        if i < 0 or j >= len(ff):
            return 0
        ch = ff[i][1] - ff[j][1]
        return 1 if ch >= 0.25 else -1 if ch <= -0.25 else 0

    def infl(day):
        i = bisect.bisect_left([y[0] for y in yoy], day) - 1
        return 1 if i >= 0 and yoy[i][1] >= 3.0 else 0
    return fed, infl


def feats(z, hike, infl, trend):
    return [1.0, z, z * infl, z * (hike == 1), z * (hike == -1), float(trend)]


# ----------------------------------------------------------------- models
def tally(points, asset, b, asof):
    w_up = w = w2 = 0.0
    n, moves = 0, []
    for p in points:
        r = p["r"].get(asset)
        if r is None or r == 0 or p["bin"] != b:
            continue
        wt = 0.5 ** ((asof - d_(p["date"])).days / 365.25 / HALF_LIFE) * p["w"]
        w += wt
        w2 += wt * wt
        w_up += wt * (r > 0)
        n += 1
        moves.append(r)
    if not n:
        return {"n": 0, "pUp": 0.5, "moves": []}
    return {"n": n, "pUp": (w_up + 1) / (w + 2), "neff": w * w / w2, "moves": moves}


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def logit_fit(X, y, w, lam=2.0, iters=8):
    """Ridge logistic regression by Newton steps (intercept not penalised)."""
    beta = [0.0] * NF
    for _ in range(iters):
        H = [[lam * (i == j and i > 0) for j in range(NF)] for i in range(NF)]
        g = [lam * beta[i] * (i > 0) for i in range(NF)]
        for xi, yi, wi in zip(X, y, w):
            eta = sum(a * b for a, b in zip(beta, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, eta))))
            for i in range(NF):
                g[i] -= wi * (yi - p) * xi[i]
                for j in range(i, NF):
                    H[i][j] += wi * p * (1 - p) * xi[i] * xi[j]
        for i in range(NF):
            for j in range(i):
                H[i][j] = H[j][i]
        step = solve(H, g)
        if not step:
            break
        beta = [b - s for b, s in zip(beta, step)]
    return beta


def logit_p(beta, x):
    eta = sum(a * b for a, b in zip(beta, x))
    return 1 / (1 + math.exp(-max(-30, min(30, eta))))


def train_rows(points, asset, asof):
    X, y, w = [], [], []
    for p in points:
        r = p["r"].get(asset)
        if r is None or r == 0:
            continue
        X.append(feats(p["z"], p["hike"], p["infl"], p["trend"].get(asset, 0)))
        y.append(1 if r > 0 else 0)
        w.append(0.5 ** ((asof - d_(p["date"])).days / 365.25 / HALF_LIFE) * p["w"])
    return X, y, w


def blend_alpha(trip):
    """Weight on the logistic model vs the tally, learned from past out-of-sample (pa, pb, y) by log loss."""
    if len(trip) < 20:
        return 0.5
    best, ba = 1e9, 0.5
    for a in (0, 0.25, 0.5, 0.75, 1):
        ll = 0.0
        for pa, pb, y in trip:
            q = min(0.98, max(0.02, (1 - a) * pa + a * pb))
            ll -= math.log(q if y else 1 - q)
        if ll < best:
            best, ba = ll, a
    return ba


def calib_k(pairs):
    """Shrink factor k for p_cal = 0.5 + k (p - 0.5), fitted on past out-of-sample (p, y) by log loss."""
    if len(pairs) < 20:
        return 0.5
    best, bk = 1e9, 0.5
    for k in [i / 20 for i in range(0, 31)]:
        ll = 0.0
        for p, y in pairs:
            q = min(0.98, max(0.02, 0.5 + k * (p - 0.5)))
            ll -= math.log(q if y else 1 - q)
        if ll < best:
            best, bk = ll, k
    return bk


class Model:
    """Bins + logistic ensemble for one release x market, fitted on `points`."""

    def __init__(self, points, asset, asof):
        self.asset, self.asof = asset, asof
        self.cells = {b: tally(points, asset, b, asof) for b in BINS}
        X, y, w = train_rows(points[-360:], asset, asof)
        self.beta = logit_fit(X, y, w) if len(y) >= MIN_N * 2 else None

    def raw(self, z, hike, infl, trend):
        c = self.cells[bucket(z)]
        pa = c["pUp"] if c["n"] >= MIN_N else 0.5
        pb = logit_p(self.beta, feats(z, hike, infl, trend)) if self.beta else pa
        return pa, pb


# ----------------------------------------------------------------- history
def build_points(kind, fetch_obs, records, px, other_dates, fed, infl):
    cfg = MODELS[kind]
    hs, hm = cfg["head"]
    obs = [o for o in (fetch_obs(hs, "2008-01-01", initial=True) or []) if o[2]]
    if not obs:
        return [], None
    vals = transform(obs, hm)
    head = surprises(vals, cfg["window"], records, kind, recorded_only=kind in BASIS)
    comps = []
    for s, m, sign in cfg["comps"]:
        o = [x for x in (fetch_obs(s, "2008-01-01", initial=True) or []) if x[2]]
        if o:
            comps.append((surprises(transform(o, m), cfg["window"]), sign))
    pts = []
    for rt, (zh, x, exp_, basis, period) in sorted(head.items()):
        zs = [zh * 2] + [sign * c[rt][0] for c, sign in comps if rt in c]
        z = sum(zs) / (len(zs) + 1)  # headline counts double
        r, tr = {}, {}
        for a, p in px.items():
            m = p.move(rt)
            if m is not None:
                r[a] = m
            tr[a] = p.trend(rt)
        pts.append({"date": rt, "period": period, "z": round(z, 3), "zh": round(zh, 3), "x": x, "exp": exp_, "basis": basis,
                    "bin": bucket(z), "r": r, "trend": tr, "hike": fed(rt), "infl": infl(rt),
                    "w": 0.5 if rt in other_dates else 1.0})
    # scale of the SURPRISES (value - expected), the same yardstick walk-forward used for each z
    return pts, {"vals": vals, "scale": scale_of([v[1] - v[2] for v in head.values()])}


def walk_forward(pts, asset):
    """Replay every release with only prior data. Returns out-of-sample predictions."""
    preds, trip, model, last_fit = [], [], None, -99
    refit = max(6, len(pts) // 40)
    for i, p in enumerate(pts):
        r = p["r"].get(asset)
        if i < WARMUP:
            continue
        if model is None or i - last_fit >= refit:
            model, last_fit = Model(pts[:i], asset, d_(p["date"])), i
            alpha = blend_alpha(trip)
            k = calib_k([((1 - alpha) * a + alpha * b, y) for a, b, y in trip])
        pa, pb = model.raw(p["z"], p["hike"], p["infl"], p["trend"].get(asset, 0))
        pc = min(0.98, max(0.02, 0.5 + k * ((1 - alpha) * pa + alpha * pb - 0.5)))
        if r is None or r == 0:
            continue
        y = 1 if r > 0 else 0
        trip.append((pa, pb, y))
        preds.append({"date": p["date"], "p": pc, "y": y, "call": abs(pc - 0.5) >= CALL_EDGE})
    alpha = blend_alpha(trip)
    return preds, alpha, calib_k([((1 - alpha) * a + alpha * b, y) for a, b, y in trip])


def binom_p(h, n):
    """One-sided P(X >= h) for X ~ Bin(n, 0.5)."""
    if n == 0:
        return 1.0
    return min(1.0, sum(math.comb(n, i) for i in range(h, n + 1)) / 2 ** n)


def evaluate(preds, live_rows=()):
    calls = [q for q in preds if q["call"]]
    hits = [((q["p"] > 0.5) == (q["y"] == 1)) for q in calls]
    n, h = len(calls), sum(hits)
    brier = sum((q["p"] - q["y"]) ** 2 for q in preds) / len(preds) if preds else 0.25
    half = n // 2
    h1, h2 = sum(hits[:half]), sum(hits[half:])
    recent = (hits + [bool(r["hit"]) for r in live_rows])[-BREAKER_N:]
    rel = []  # reliability: predicted vs realised in probability bands
    for lo in (0.5, 0.6, 0.7):
        band = [q for q in calls if lo <= max(q["p"], 1 - q["p"]) < lo + 0.1 or (lo == 0.7 and max(q["p"], 1 - q["p"]) >= 0.7)]
        if band:
            rel.append({"band": f"{int(lo * 100)}%+", "n": len(band), "stated": round(statistics.mean(max(q["p"], 1 - q["p"]) for q in band), 3),
                        "actual": round(sum((q["p"] > 0.5) == (q["y"] == 1) for q in band) / len(band), 3)})
    return {"calls": n, "hits": h, "rate": round(h / n, 3) if n else 0, "pval": binom_p(h, n),
            "brierSkill": round(1 - brier / 0.25, 3), "halves": [round(h1 / half, 3) if half else 0, round(h2 / (n - half), 3) if n - half else 0],
            "recent": round(sum(recent) / len(recent), 3) if recent else 0, "reliability": rel}


def bh(tests, q=FDR_Q):
    """Benjamini-Hochberg: which tests pass at false-discovery rate q."""
    order = sorted(range(len(tests)), key=lambda i: tests[i])
    m, cut = len(tests), -1
    for rank, i in enumerate(order, 1):
        if tests[i] <= q * rank / m:
            cut = rank
    return {order[r] for r in range(cut)} if cut > 0 else set()


# ----------------------------------------------------------------- fit / apply
HIGH = ("cpi", "nfp", "retail", "pce", "gdp", "ppi")


def fit(fetch_obs, gold_fn, records, today, log=print, live_rows=(), price_fns=None):
    cache = {}

    def fetch(s, start, initial=False):
        key = (s, start, initial)
        if key not in cache:
            cache[key] = fetch_obs(s, start, initial=initial) if initial else fetch_obs(s, start)
        return cache[key]
    px, srcs = {}, {}
    for a, (series, unit, name, _) in ASSETS.items():
        if price_fns and a in price_fns:
            rows, src = price_fns[a](START)
        elif series:
            o = fetch(series, START)
            rows, src = ([(d, v) for d, v, _ in o] if o else None), f"FRED {series}"
        else:
            rows, src = gold_fn(START) if gold_fn else (None, "")
        if rows and len(rows) > 250:
            px[a] = Px(rows, unit)
            srcs[a] = src
        else:
            log(f"direction: no price history for {name}")
    if not px:
        return None, {}
    fed, infl = regimes(fetch)
    other_dates = {k: {o[2] for o in (fetch(MODELS[k]["head"][0], "2008-01-01", True) or [])} for k in HIGH}
    model = {"asof": today.isoformat(), "version": 2, "method": __doc__.split("Method")[1].strip(), "sources": srcs,
             "assets": {a: ASSETS[a][2] for a in px}, "kinds": {}, "regime": {"hike": fed(today.isoformat()), "infl": infl(today.isoformat())},
             "trendNow": {a: p.trend((today + dt.timedelta(days=1)).isoformat()) for a, p in px.items()}}
    tests, keys, store = [], [], {}
    for kind, cfg in MODELS.items():
        try:
            others = set().union(*[v for k, v in other_dates.items() if k != kind]) if other_dates else set()
            pts, meta = build_points(kind, fetch, records, px, others, fed, infl)
        except Exception as e:
            log(f"direction: {kind} failed: {e}")
            continue
        if len(pts) < WARMUP + PROVEN_CALLS or not meta or not meta["scale"]:
            log(f"direction: not enough history for {kind}")
            continue
        km = {"metric": cfg["metric"], "n": len(pts), "since": pts[0]["date"], "scale": meta["scale"], "mult": cfg["mult"],
              "basis": BASIS.get(kind, "trend"),
              "window": cfg["window"], "recent": [[rt, x] for _, x, rt in meta["vals"][-8:]], "assets": {},
              "last": [{k: p[k] for k in ("date", "period", "z", "bin", "basis", "hike", "infl")} | {"trend": p["trend"]} for p in pts[-3:]]}
        for a in px:
            preds, alpha, k = walk_forward(pts, a)
            if not preds:
                continue
            ev = evaluate(preds, [r for r in live_rows if r.get("kind") == kind and r.get("asset") == a and "hit" in r])
            m = Model(pts, a, today)
            km["assets"][a] = {"k": k, "alpha": alpha, "beta": [round(b, 4) for b in m.beta] if m.beta else None,
                               "cells": {b: {"n": c["n"], "pUp": round(c["pUp"], 3),
                                             "med": round(statistics.median(c["moves"]), 3) if c["moves"] else 0,
                                             "q1": round(statistics.quantiles(c["moves"], n=4)[0], 3) if len(c["moves"]) >= 4 else 0,
                                             "q3": round(statistics.quantiles(c["moves"], n=4)[2], 3) if len(c["moves"]) >= 4 else 0}
                                         for b, c in m.cells.items()},
                               "bt": ev}
            tests.append(ev["pval"])
            keys.append((kind, a))
        model["kinds"][kind] = km
    passed = bh(tests)
    for i, (kind, a) in enumerate(keys):
        ev = model["kinds"][kind]["assets"][a]["bt"]
        reasons = []
        if ev["calls"] < PROVEN_CALLS:
            reasons.append("too few tested calls")
        if ev["rate"] < PROVEN_RATE:
            reasons.append("hit rate under 55%")
        if i not in passed:
            reasons.append("not significant after correcting for the number of rules tested")
        if ev["brierSkill"] <= 0:
            reasons.append("probabilities no better than a coin flip")
        if min(ev["halves"]) <= 0.5:
            reasons.append("did not work in both halves of history")
        if ev["recent"] < 0.5:
            reasons.append("switched off: recent calls below 50%")
        cells = model["kinds"][kind]["assets"][a]["cells"]
        if abs(cells["hot"]["pUp"] - cells["cool"]["pUp"]) < 0.12:
            reasons.append("market moves don't depend on the surprise")
        ev["proven"] = not reasons
        ev["why"] = reasons[0] if reasons else ""
    return model, px


def _prob(km, a, z, hike, infl, trend):
    m = km["assets"][a]
    c = m["cells"][bucket(z)]
    pa = c["pUp"] if c["n"] >= MIN_N else 0.5
    pb = logit_p(m["beta"], feats(z, hike, infl, trend)) if m["beta"] else pa
    raw = (1 - m["alpha"]) * pa + m["alpha"] * pb
    return min(0.98, max(0.02, 0.5 + m["k"] * (raw - 0.5))), c


def _call(model, kind, a, z, trend):
    km = model["kinds"][kind]
    m = km["assets"].get(a)
    if not m:
        return None
    bt = m["bt"]
    if not bt.get("proven"):
        return {"none": True, "n": bt["calls"], "why": bt.get("why") or "not proven"}
    p, c = _prob(km, a, z, model["regime"]["hike"], model["regime"]["infl"], trend)
    if abs(p - 0.5) < CALL_EDGE:
        return {"none": True, "n": c["n"], "why": "no clear lean in today's conditions"}
    return {"dir": "up" if p > 0.5 else "down", "p": round(max(p, 1 - p), 3), "n": c["n"], "med": c["med"],
            "iqr": [c["q1"], c["q3"]], "bt": [bt["hits"], bt["calls"]]}


def apply(model, events, kind_of, today, horizon=14, use_consensus=False, records=None):
    out = {}
    if not model or model.get("version") != 2:
        return out
    for e in events:
        k = kind_of(e)
        if k not in model["kinds"] or not e.get("time"):
            continue
        days = (d_(e["date"]) - today).days
        if days < -1 or days > horizon:
            continue
        km = model["kinds"][k]
        last = km["last"][-1] if km["last"] else {}
        trend = last.get("trend", {}) if last.get("date") == e["date"] else model.get("trendNow", {})
        if e.get("actual") and days <= 0:
            if last.get("date") == e["date"]:
                z, basis = last["z"], last["basis"]  # full composite from the refit after the release
            else:
                x = figure(e["actual"], km["mult"])
                fc = (records or {}).get((k, e["date"]))
                if fc is None and use_consensus:
                    fc = figure(e.get("forecast"), km["mult"])
                if fc is None and km.get("basis") not in (None, "trend"):
                    continue  # this release is modelled against a recorded expectation we don't have
                prior = [v for d, v in km["recent"] if d < e["date"]][-km["window"]:]
                exp_ = fc if fc is not None else (sum(prior) / len(prior) if len(prior) == km["window"] else None)
                if x is None or exp_ is None:
                    continue
                z, basis = max(-6, min(6, (x - exp_) / km["scale"])), (km.get("basis") or "consensus") if fc is not None else "trend"
            out[e["id"]] = {"kind": k, "date": e["date"], "stage": "post", "z": round(z, 2), "bin": bucket(z), "basis": basis,
                            "calls": {a: c for a in model["assets"] if (c := _call(model, k, a, z, trend.get(a, 0)))}}
        elif days >= 0:
            exp_ = (records or {}).get((k, e["date"]))
            out[e["id"]] = {"kind": k, "date": e["date"], "stage": "pre", "basis": km.get("basis", "trend"),
                            **({"expect": round(exp_, 3)} if exp_ is not None else {}),
                            "hot": {a: c for a in model["assets"] if (c := _call(model, k, a, 1.0, trend.get(a, 0)))},
                            "cool": {a: c for a in model["assets"] if (c := _call(model, k, a, -1.0, trend.get(a, 0)))}}
    return out


def score(log_rows, px):
    for row in log_rows:
        if "hit" in row or row["asset"] not in px:
            continue
        m = px[row["asset"]].move(row["date"])
        if m is None or m == 0:
            continue
        row["move"] = round(m, 3)
        row["hit"] = (m > 0) == (row["dir"] == "up")
    done = [r for r in log_rows if "hit" in r]
    by = {}
    for r in done:
        b = by.setdefault(r["asset"], [0, 0])
        b[0] += r["hit"]
        b[1] += 1
    return {"calls": len(done), "hits": sum(r["hit"] for r in done), "open": len(log_rows) - len(done),
            "byAsset": by, "recent": done[-12:][::-1]}


def log_calls(log_rows, live):
    have = {(r["id"], r["asset"]) for r in log_rows}
    for eid, v in live.items():
        if v["stage"] != "post":
            continue
        for a, c in v["calls"].items():
            if c.get("dir") and (eid, a) not in have:
                log_rows.append({"id": eid, "date": v["date"], "kind": v["kind"], "asset": a, "dir": c["dir"], "p": c["p"]})
    return log_rows


def check(QA, model, live):
    ok = True
    if model:
        bad = [(k, a) for k, km in model["kinds"].items() for a, m in km["assets"].items()
               if not (0 <= m["k"] <= 1.5) or any(not (0 < c["pUp"] < 1) for c in m["cells"].values() if c["n"])]
        ok &= QA.check("direction: model values valid", not bad, str(bad[:5]), critical=True)
        QA.check("direction: gold prices available", "gold" in model.get("assets", {}), "gold source unavailable; gold omitted")
        QA.check("direction: enough releases modelled", len(model["kinds"]) >= 5, f"{len(model['kinds'])} kinds")
    for eid, v in live.items():
        calls = dict(v.get("calls") or {})
        for side in ("hot", "cool"):
            calls.update({f"{side}:{a}": c for a, c in (v.get(side) or {}).items()})
        for a, c in calls.items():
            if c.get("dir") and not (c["dir"] in ("up", "down") and 0.5 < c["p"] < 1):
                ok &= QA.check(f"direction: call {eid}/{a} well-formed", False, str(c), critical=True)
    return ok
