"""News-outcome model v4: how gold, the Nasdaq-100, the dollar and the 2-year yield react to consensus surprises.

Surprises come from tv.py: (actual - consensus) / that report's typical surprise, positive = hotter or stronger
than expected. Reports are pooled by theme (inflation, labor, activity, sentiment, housing) so each model learns
from hundreds of releases instead of a few dozen.

Markets and horizons
  gold2h, nq2h   first ~2 hours: open of the hourly bar holding the release -> close one bar later
                 (08:30 release: 08:00 -> 10:00 New York). Hourly futures bars, archived since mid-2024.
  gold, nq       release-day close vs the day before (2010 onward)
  usd, y2        Fed broad dollar index and the 2-year Treasury yield, release-day close vs the day before

Model, for each market x theme: P(market up) = 0.5 + k * (sigmoid(b * z) - 0.5). There is no intercept, so the
market's usual drift (stocks tend to rise) can never pass as a news edge: the lean depends only on the surprise.
b is a ridge logistic slope, recent years weighted more (half-life 5 years); k shrinks the probability toward 50%
by as much as the model's own out-of-sample record says it should, so a stated 65% has historically meant ~65%.

Walk-forward test: every release is predicted using only releases before it. A rule is PROVEN only if it made
enough out-of-sample calls (30 for the close, 20 for 2 hours), was right 55%+ of the time, survives a false-
discovery correction across every market x theme tested, beats a coin flip on calibration (Brier skill > 0),
worked in both the earlier and the later half, and is still right at least half the time over its last 20
calls (tested and live). Everything else is shown as the historical record only.
"""
import bisect
import datetime as dt
import math
import statistics

import tv

MARKETS = {  # key: (name, unit, horizon)
    "gold2h": ("Gold, first 2h", "pct", "2h"), "nq2h": ("Nasdaq 100, first 2h", "pct", "2h"),
    "gold": ("Gold, close", "pct", "close"), "nq": ("Nasdaq 100, close", "pct", "close"),
    "usd": ("Dollar, close", "pct", "close"), "y2": ("2-yr yield, close", "bp", "close"),
}
HALF_LIFE = 5.0
EDGE = 0.05
MIN_TRAIN = {"2h": 25, "close": 60}
MIN_CALLS = {"2h": 20, "close": 30}
PROVEN_RATE, FDR_Q, BREAKER_N = 0.55, 0.10, 20
BIN = 0.5  # |z| below this counts as "in line" in the scenario map


# ----------------------------------------------------------------- reactions
class Daily:
    def __init__(self, rows, unit):  # rows: [(date, close)]
        self.c = dict(rows)
        self.d = sorted(self.c)
        self.unit = unit

    def move(self, day):
        if day not in self.c:
            return None
        i = bisect.bisect_left(self.d, day)
        if not i:
            return None
        a, b = self.c[self.d[i - 1]], self.c[day]
        return (b - a) * 100 if self.unit == "bp" else ((b / a - 1) * 100 if a else None)


class Hourly:
    def __init__(self, rows, complete_before):  # rows: [(start NY, o, h, l, c)]
        self.by = {r[0]: r for r in rows}
        self.starts = [r[0] for r in rows]
        self.complete_before = complete_before

    def move(self, when):
        i = bisect.bisect_right(self.starts, when) - 1
        if i < 0:
            return None
        s = self.starts[i]
        if not s <= when < s + dt.timedelta(hours=1):
            return None
        end = self.by.get(s + dt.timedelta(hours=1))
        if not end or s + dt.timedelta(hours=2) > self.complete_before:
            return None
        o = self.by[s][1]
        return (end[4] / o - 1) * 100 if o else None


def reaction(markets, key, when):
    m = markets.get(key)
    if m is None:
        return None
    return m.move(when) if MARKETS[key][2] == "2h" else m.move(when.date().isoformat())


# ----------------------------------------------------------------- model
def _sig(x):
    return 1 / (1 + math.exp(-max(-30, min(30, x))))


def fit_slope(zs, ys, ws, lam=1.0):
    """Ridge logistic with one coefficient and no intercept: P(up) = sigmoid(b z)."""
    b = 0.0
    for _ in range(25):
        g = lam * b
        h = lam
        for z, y, w in zip(zs, ys, ws):
            p = _sig(b * z)
            g -= w * (y - p) * z
            h += w * p * (1 - p) * z * z
        step = g / h if h else 0
        b -= step
        if abs(step) < 1e-7:
            break
    return b


def calib_k(pairs):
    """Shrink factor for p = 0.5 + k (p_raw - 0.5), fitted on past out-of-sample (p_raw, y) by log loss."""
    if len(pairs) < 20:
        return 0.5
    best, bk = 1e18, 0.5
    for k in [i / 20 for i in range(0, 31)]:
        ll = 0.0
        for p, y in pairs:
            q = min(0.98, max(0.02, 0.5 + k * (p - 0.5)))
            ll -= math.log(q if y else 1 - q)
        if ll < best:
            best, bk = ll, k
    return bk


def weights(points, asof):
    return [0.5 ** (max(0.0, (asof - p[0]).days) / 365.25 / HALF_LIFE) for p in points]


def walk_forward(points, horizon):
    """points: [(when, z, up)] oldest first -> out-of-sample predictions."""
    preds, pairs = [], []
    b, k, last = None, 0.5, -10 ** 9
    refit = max(5, len(points) // 40)
    for i, (when, z, y) in enumerate(points):
        if i < MIN_TRAIN[horizon]:
            continue
        if b is None or i - last >= refit:
            train = points[:i]
            b = fit_slope([p[1] for p in train], [p[2] for p in train], weights(train, when))
            k = calib_k(pairs)
            last = i
        raw = _sig(b * z)
        p = min(0.98, max(0.02, 0.5 + k * (raw - 0.5)))
        pairs.append((raw, y))
        preds.append({"when": when, "p": p, "y": y, "call": abs(p - 0.5) >= EDGE})
    return preds, calib_k(pairs)


def binom_p(h, n):
    if n == 0:
        return 1.0
    return min(1.0, sum(math.comb(n, i) for i in range(h, n + 1)) / 2 ** n)


def evaluate(preds, live=()):
    calls = [q for q in preds if q["call"]]
    hits = [(q["p"] > 0.5) == (q["y"] == 1) for q in calls]
    n, h = len(calls), sum(hits)
    brier = sum((q["p"] - q["y"]) ** 2 for q in preds) / len(preds) if preds else 0.25
    half = n // 2
    recent = (hits + [bool(r["hit"]) for r in live])[-BREAKER_N:]
    return {"calls": n, "hits": h, "rate": round(h / n, 3) if n else 0, "pval": binom_p(h, n),
            "brierSkill": round(1 - brier / 0.25, 3),
            "halves": [round(sum(hits[:half]) / half, 3) if half else 0, round(sum(hits[half:]) / (n - half), 3) if n - half else 0],
            "recent": round(sum(recent) / len(recent), 3) if recent else 0, "tested": len(preds)}


def bh(pvals, q=FDR_Q):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, cut = len(pvals), 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cut = rank
    return {order[r] for r in range(cut)}


def dataset(rels, markets, key, settled_before):
    """[(when, z, up, move, kind)] for one market."""
    out = []
    for r in rels:
        if r["z"] is None or r["when"] >= settled_before:
            continue
        m = reaction(markets, key, r["when"])
        if m is None or m == 0:
            continue
        out.append((r["when"], r["z"], 1 if m > 0 else 0, m, r["kind"]))
    return out


def fit(rels, markets, now, live_rows=()):
    """Train and test every market x theme. Returns the model dict."""
    model = {"asof": now.isoformat(timespec="minutes"), "version": 4, "markets": {k: MARKETS[k][0] for k in markets},
             "groups": {}, "scenarios": {}}
    tests, keys = [], []
    data = {key: dataset(rels, markets, key, now) for key in markets}
    for g, kinds in tv.GROUPS.items():
        gm = model["groups"].setdefault(g, {})
        for key in markets:
            pts = [(w, z, y) for w, z, y, _, k in data[key] if k in kinds]
            hz = MARKETS[key][2]
            if len(pts) < MIN_TRAIN[hz] + 10:
                continue
            preds, k = walk_forward(pts, hz)
            ev = evaluate(preds, [r for r in live_rows if r.get("group") == g and r.get("asset") == key and "hit" in r])
            b = fit_slope([p[1] for p in pts], [p[2] for p in pts], weights(pts, now))
            gm[key] = {"b": round(b, 4), "k": k, "n": len(pts), "since": pts[0][0].date().isoformat(), "bt": ev}
            tests.append(ev["pval"])
            keys.append((g, key))
    passed = bh(tests)
    for i, (g, key) in enumerate(keys):
        s = model["groups"][g][key]
        ev, hz = s["bt"], MARKETS[key][2]
        why = []
        if ev["calls"] < MIN_CALLS[hz]:
            why.append("too few tested calls")
        if ev["rate"] < PROVEN_RATE:
            why.append("right less than 55% of the time on unseen releases")
        if i not in passed:
            why.append("not significant after correcting for the number of rules tested")
        if ev["brierSkill"] <= 0:
            why.append("probabilities no better than a coin flip")
        if min(ev["halves"]) < 0.5:
            why.append("did not work in both halves of its history")
        if ev["recent"] < 0.5:
            why.append("switched off: recent calls below 50%")
        s["proven"] = not why
        s["why"] = why[0] if why else ""
    # scenario map per report: above / near / below consensus
    for kind in tv.REPORTS:
        sc = {}
        for key in markets:
            rows = [(z, m) for w, z, y, m, k in data[key] if k == kind]
            if len(rows) < 8:
                continue
            cells = {}
            for name, sel in (("hot", lambda z: z >= BIN), ("inline", lambda z: -BIN < z < BIN), ("cool", lambda z: z <= -BIN)):
                ms = [m for z, m in rows if sel(z)]
                if ms:
                    cells[name] = {"n": len(ms), "up": round(sum(m > 0 for m in ms) / len(ms), 3),
                                   "med": round(statistics.median(ms), 3)}
            sc[key] = cells
        if sc:
            model["scenarios"][kind] = {"n": max(len([1 for *_, k in data[key] if k == kind]) for key in markets), "assets": sc}
    return model


def prob(model, group, key, z):
    s = model["groups"].get(group, {}).get(key)
    if not s:
        return None
    return min(0.98, max(0.02, 0.5 + s["k"] * (_sig(s["b"] * z) - 0.5)))


def call(model, group, key, z):
    s = model["groups"].get(group, {}).get(key)
    if not s:
        return None
    if not s.get("proven"):
        return {"none": True, "n": s["bt"]["calls"], "why": s.get("why") or "not proven"}
    p = prob(model, group, key, z)
    if abs(p - 0.5) < EDGE:
        return {"none": True, "n": s["bt"]["calls"], "why": "the surprise is too small for a lean"}
    return {"dir": "up" if p > 0.5 else "down", "p": round(max(p, 1 - p), 3), "bt": [s["bt"]["hits"], s["bt"]["calls"]],
            "n": s["n"]}


def score(log_rows, markets, now):
    """Score logged calls once their window has closed."""
    for r in log_rows:
        if "hit" in r or r["asset"] not in markets:
            continue
        when = dt.datetime.fromisoformat(r["when"])
        m = reaction(markets, r["asset"], when)
        if m is None or m == 0:
            continue
        r["move"] = round(m, 3)
        r["hit"] = (m > 0) == (r["dir"] == "up")
    done = [r for r in log_rows if "hit" in r]
    by = {}
    for r in done:
        b = by.setdefault(r["asset"], [0, 0])
        b[0] += r["hit"]
        b[1] += 1
    return {"calls": len(done), "hits": sum(r["hit"] for r in done), "open": len(log_rows) - len(done),
            "byAsset": by, "recent": done[-12:][::-1]}
