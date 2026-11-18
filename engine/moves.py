"""Expected move: how far gold and the Nasdaq-100 travel on a release day, against a normal day.

Direction after a release is hard to call; the SIZE of the move is not. This module measures, for every past
release since 2008:

  true range %   (max(high, previous close) - min(low, previous close)) / previous close
                 so the opening gap after an 08:30 release counts for the Nasdaq-100 cash index
  baseline       the median true range of the 40 trading days before it, skipping other major release days,
                 so the prediction scales with how volatile markets are right now
  multiplier     true range / baseline

Prediction for an upcoming release: today's baseline x the median multiplier of that release's past days,
with an 80% band from the 10th-90th percentile of past multipliers.

Walk-forward test (every past release replayed with only earlier releases): the prediction must beat the naive
"it's a normal day" guess (the baseline alone) on log error, survive a false-discovery correction across every
release x market tested, beat the naive guess on most days (sign test), and its 80% band must have held
70-90% of the time. Only then is it marked proven; otherwise the historical numbers are shown as a record.
"""
import bisect
import math
import statistics

BASE_DAYS = 40
MIN_PRIOR = 12
RECENT = 60  # multipliers from the latest 60 releases of each kind
PROVEN_TESTS, MIN_SKILL, FDR_Q = 30, 0.05, 0.10
HIGH = ("cpi", "nfp", "pce", "retail", "ppi", "gdp")


def true_ranges(rows):
    """{date: true range %} from [(date, high, low, close)]."""
    out = {}
    for (d0, _, _, c0), (d, h, lo, c) in zip(rows, rows[1:]):
        if c0 > 0:
            out[d] = (max(h, c0) - min(lo, c0)) / c0 * 100
    return out


def baselines(tr, skip):
    """{date: median true range of the BASE_DAYS normal days before it}."""
    days = sorted(tr)
    normal = [d for d in days if d not in skip]
    out = {}
    for d in days:
        i = bisect.bisect_left(normal, d)
        window = [tr[x] for x in normal[max(0, i - BASE_DAYS):i]]
        if len(window) >= BASE_DAYS // 2:
            out[d] = statistics.median(window)
    return out


def quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f = math.floor(k)
    return xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f)


def sign_p(wins, n):
    """One-sided P(X >= wins) for X ~ Bin(n, 0.5)."""
    if n == 0:
        return 1.0
    return min(1.0, sum(math.comb(n, i) for i in range(wins, n + 1)) / 2 ** n)


def bh(pvals, q=FDR_Q):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, cut = len(pvals), 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cut = rank
    return {order[r] for r in range(cut)}


def walk_forward(points):
    """points: [(date, ratio, baseline, actual)] oldest first. Out-of-sample errors and band hits."""
    err_m, err_n, inside = [], [], []
    for i, (d, ratio, base, actual) in enumerate(points):
        prior = [p[1] for p in points[max(0, i - RECENT):i]]
        if len(prior) < MIN_PRIOR:
            continue
        mult = statistics.median(prior)
        err_m.append(abs(math.log(actual / (base * mult))))
        err_n.append(abs(math.log(actual / base)))
        inside.append(quantile(prior, 0.1) <= ratio <= quantile(prior, 0.9))
    n = len(err_m)
    if not n:
        return {"tests": 0}
    wins = sum(a < b for a, b in zip(err_m, err_n))
    return {"tests": n, "skill": round(1 - sum(err_m) / sum(err_n), 3) if sum(err_n) else 0,
            "beatNaive": round(wins / n, 3), "pval": sign_p(wins, n), "coverage": round(sum(inside) / n, 3)}


def fit(price_rows, release_dates, today):
    """price_rows: {market: [(date, high, low, close)]}; release_dates: {kind: [dates]}.
    Returns {"markets": {...}, "kinds": {kind: {market: stats}}}."""
    skip = set().union(*[set(release_dates.get(k, [])) for k in HIGH]) if release_dates else set()
    out = {"asof": today.isoformat(), "markets": {}, "kinds": {}}
    tests, keys = [], []
    for m, rows in price_rows.items():
        tr = true_ranges(rows)
        if len(tr) < 300:
            continue
        base = baselines(tr, skip)
        days = sorted(tr)
        normal = [d for d in days if d not in skip][-BASE_DAYS:]
        now = statistics.median(tr[d] for d in normal) if normal else None
        out["markets"][m] = {"baseline": round(now, 3) if now else None, "close": rows[-1][3], "asof": rows[-1][0]}
        for k, dates in release_dates.items():
            pts = [(d, tr[d] / base[d], base[d], tr[d]) for d in sorted(set(dates)) if d in tr and d in base and base[d] > 0]
            if len(pts) < MIN_PRIOR + 5:
                continue
            ratios = [p[1] for p in pts[-RECENT:]]
            bt = walk_forward(pts)
            out["kinds"].setdefault(k, {})[m] = {
                "n": len(pts), "since": pts[0][0], "mult": round(statistics.median(ratios), 3),
                "lo": round(quantile(ratios, 0.1), 3), "hi": round(quantile(ratios, 0.9), 3),
                "medRange": round(statistics.median(p[3] for p in pts[-RECENT:]), 3), "bt": bt}
            if bt["tests"]:
                tests.append(bt["pval"])
                keys.append((k, m))
    passed = bh(tests)
    for i, (k, m) in enumerate(keys):
        s = out["kinds"][k][m]
        bt = s["bt"]
        why = []
        if bt["tests"] < PROVEN_TESTS:
            why.append("too few tested releases")
        if bt["skill"] < MIN_SKILL:
            why.append("no better than treating it as a normal day")
        if i not in passed:
            why.append("not significant after correcting for the number of rules tested")
        if not 0.7 <= bt["coverage"] <= 0.9:
            why.append("its 80% band was not reliable")
        s["proven"] = not why
        s["why"] = why[0] if why else ""
    return out


def for_event(model, kind):
    """{market: expected move} for an upcoming release of `kind`, using today's baseline."""
    res = {}
    for m, s in (model.get("kinds", {}).get(kind) or {}).items():
        mk = model["markets"].get(m) or {}
        b, c = mk.get("baseline"), mk.get("close")
        if not b or not c:
            continue
        res[m] = {"pct": round(b * s["mult"], 2), "lo": round(b * s["lo"], 2), "hi": round(b * s["hi"], 2),
                  "normal": round(b, 2), "mult": s["mult"], "pts": round(b * s["mult"] / 100 * c, 1),
                  "n": s["n"], "proven": s.get("proven", False), "why": s.get("why", "")}
    return res
