"""Direction engine tests on simulated worlds where the truth is known.

World: CPI surprises (headline and core) move the dollar up, EUR/USD and gold down and yields up; jobless claims
move nothing; the Nasdaq ignores everything. Variants: no effect at all (noise), and an effect that only
exists while the Fed is hiking. The engine must find real rules in the right direction, find none in noise,
state honest probabilities, pick up regime effects and switch off a rule that stops working."""
import datetime as dt
import random
import statistics
import sys
import time

import direction as D

TODAY = dt.date(2026, 11, 15)


def bdays(a, b):
    d, out = a, []
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def world(seed, effect=0.30, regime_only=False, end=dt.date(2026, 11, 13)):
    rnd = random.Random(seed)
    days = bdays(dt.date(2008, 1, 1), end)
    keys = ("usd", "gold", "nq", "y2", "y10", "eur")
    rets = {a: {d: rnd.gauss(0, 0.4) for d in days} for a in keys}
    # fed funds: alternate hiking / cutting / hold cycles of ~2 years
    ff, rate = [], 1.0
    for i, d in enumerate(days):
        phase = (i // 520) % 3
        rate = max(0.1, rate + (0.0025 if phase == 0 else -0.0025 if phase == 1 else 0))
        ff.append((d.isoformat(), rate, d.isoformat()))
    hiking = {d.isoformat(): (i // 520) % 3 == 0 and (i % 520) > 130 for i, d in enumerate(days)}
    core, head, moms = [], [], []
    lc = lh = 100.0
    m = dt.date(2008, 1, 1)
    while True:
        mom = rnd.gauss(0.25, 0.12)
        hmom = mom + rnd.gauss(0, 0.06)
        lc *= 1 + mom / 100
        lh *= 1 + hmom / 100
        nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        if nxt.replace(day=12) > end:
            break
        rel = next(d for d in days if d >= nxt.replace(day=12))
        core.append((m.isoformat(), lc, rel.isoformat()))
        head.append((m.isoformat(), lh, rel.isoformat()))
        moms.append(mom)
        if len(moms) > 3 and (not regime_only or hiking[rel.isoformat()]):
            s = (mom - statistics.mean(moms[-4:-1])) / 0.15
            for a, f in (("usd", 1), ("gold", -1.2), ("y2", 1.5), ("y10", 1.0), ("eur", -0.9)):
                rets[a][rel] += effect * f * s
        m = nxt
    claims = [((d - dt.timedelta(days=5)).isoformat(), rnd.gauss(230000, 15000), d.isoformat()) for d in days if d.weekday() == 3]
    px = {}
    for a, base in (("usd", 100), ("gold", 1200), ("nq", 2000), ("y2", 2.0), ("y10", 3.0), ("eur", 1.2)):
        v, rows = base, []
        for d in days:
            v = v + rets[a][d] / 100 if a in ("y2", "y10") else v * (1 + rets[a][d] / 100)
            rows.append((d.isoformat(), v, d.isoformat()))
        px[a] = rows
    series = {"CPILFESL": core, "CPIAUCSL": head, "ICSA": claims, "DFF": ff, "DTWEXBGS": px["usd"], "NASDAQ100": px["nq"],
              "DGS2": px["y2"], "DGS10": px["y10"], "DEXUSEU": px["eur"]}

    def fetch(s, start, initial=False):
        return [o for o in series.get(s, []) if o[0] >= start] or None

    def gold(start):
        return [(d, v) for d, v, _ in px["gold"] if d >= start], "sim"
    return fetch, gold


def run(seed, live_rows=(), **kw):
    fetch, gold = world(seed, **kw)
    return D.fit(fetch, gold, {}, TODAY, log=lambda *a: None, live_rows=live_rows)


class Q:
    def __init__(self):
        self.c = []

    def check(self, n, ok, d="", critical=False):
        self.c.append((n, ok))
        return ok


def main():
    t0 = time.time()
    model, px = run(1)
    print(f"fit time {time.time() - t0:.1f}s")
    cpi, cl = model["kinds"]["cpi"]["assets"], model["kinds"]["claims"]["assets"]
    for a in ("usd", "gold", "y2", "y10", "eur"):
        assert cpi[a]["bt"]["proven"], (a, cpi[a]["bt"])
    assert not cpi["nq"]["bt"]["proven"], "found an edge in the Nasdaq where there is none"
    assert not any(m["bt"]["proven"] for m in cl.values()), "claims edge out of noise"
    print("cpi rules:", {a: (m["bt"]["hits"], m["bt"]["calls"], m["bt"]["rate"]) for a, m in cpi.items()})

    # honest probabilities: stated vs realised in the out-of-sample record
    for a in ("usd", "gold"):
        for band in cpi[a]["bt"]["reliability"]:
            if band["n"] >= 25:
                assert abs(band["stated"] - band["actual"]) <= 0.10, (a, band)
    print("reliability (gold):", cpi["gold"]["bt"]["reliability"])

    kind_of = lambda e: "cpi" if e["title"].startswith("CPI") else "claims" if "claims" in e["title"] else None
    ev = [{"id": "a", "date": "2026-11-13", "time": "08:30", "title": "CPI (Oct)", "actual": "0.7%", "forecast": "0.3%"},
          {"id": "b", "date": "2026-12-10", "time": "08:30", "title": "CPI (Nov)"},
          {"id": "c", "date": "2026-11-19", "time": "08:30", "title": "Initial jobless claims"}]
    live = D.apply(model, ev, kind_of, dt.date(2026, 11, 14), horizon=30)
    a = live["a"]["calls"]
    assert a["usd"]["dir"] == "up" and a["gold"]["dir"] == "down" and a["eur"]["dir"] == "down" and a["y2"]["dir"] == "up", a
    assert a["nq"].get("none"), a["nq"]
    b = live["b"]
    assert b["hot"]["gold"]["dir"] == "down" and b["cool"]["gold"]["dir"] == "up", b
    assert all(c.get("none") for c in live["c"]["hot"].values())
    q = Q()
    assert D.check(q, model, live), q.c
    rows = D.log_calls([], live)
    assert len(rows) == 5 and len(D.log_calls(rows, live)) == 5
    rec = D.score(rows, px)
    assert rec["calls"] == 5, rec

    # circuit breaker: a run of wrong live calls switches the rule off
    bad = [{"kind": "cpi", "asset": "gold", "hit": False}] * D.BREAKER_N
    m2, _ = run(1, live_rows=bad)
    g = m2["kinds"]["cpi"]["assets"]["gold"]["bt"]
    assert not g["proven"] and "switched off" in g["why"], g
    assert m2["kinds"]["cpi"]["assets"]["usd"]["bt"]["proven"]

    # regime effect: only while the Fed hikes
    m3, _ = run(5, regime_only=True, effect=0.45)
    u = m3["kinds"]["cpi"]["assets"]["usd"]
    km = m3["kinds"]["cpi"]
    p_hike, _ = D._prob(km, "usd", 1.0, 1, 0, 0)
    p_cut, _ = D._prob(km, "usd", 1.0, -1, 0, 0)
    print(f"regime world: usd rule proven={u['bt']['proven']} p(up|hot, hiking)={p_hike:.2f} p(up|hot, cutting)={p_cut:.2f}")
    beta = u["beta"]
    assert beta[3] > 0.3 and beta[3] > abs(beta[4]) + 0.2, beta  # surprise x hiking picked up, not surprise x cutting
    assert p_hike - p_cut >= 0.03, (p_hike, p_cut)

    # false discoveries on pure noise
    fp = tot = 0
    for seed in range(100, 108):
        m, _ = run(seed, effect=0.0)
        for k in m["kinds"].values():
            for x in k["assets"].values():
                tot += 1
                fp += x["bt"]["proven"]
    print(f"noise worlds: {fp}/{tot} rules wrongly proven")
    assert fp <= 1, (fp, tot)
    found = sum(run(s, effect=0.2)[0]["kinds"]["cpi"]["assets"]["usd"]["bt"]["proven"] for s in range(30, 36))
    print(f"moderate real effect found in {found}/6 worlds")
    assert found >= 3
    print(f"direction tests passed in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    sys.exit(main())
