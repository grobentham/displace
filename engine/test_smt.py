"""Tests for the ES / NQ divergence engine. Offline. python engine/test_smt.py"""
import datetime as dt
import math
import random
import time

import bars
import smt

NY = smt.NY


def series(start, n, f, step=5):
    out = []
    for i in range(n):
        t = start + dt.timedelta(minutes=step * i)
        c = f(i)
        out.append((t, c, c + 1, c - 1, c))
    return out


def test_swing_bearish():
    # two swing highs ~25 bars apart; NQ's second high is higher, ES's second high is lower
    start = dt.datetime(2026, 11, 17, 9, 30, tzinfo=NY)
    def bump(i, a, b):
        return 100 + a * math.exp(-((i - 20) / 3) ** 2) + b * math.exp(-((i - 45) / 3) ** 2)
    nq = series(start, 80, lambda i: bump(i, 10, 14))
    es = series(start, 80, lambda i: bump(i, 10, 7))
    found = smt.swing_divergences(smt.aligned(nq, es), 3, 48)
    bear = [f for f in found if f["direction"] == "bearish"]
    assert len(bear) == 1, found
    assert bear[0]["leader"] == "NQ" and bear[0]["laggard"] == "ES"
    same = smt.swing_divergences(smt.aligned(nq, series(start, 80, lambda i: bump(i, 10, 14))), 3, 48)
    assert not same, "no divergence when both make the higher high"


def test_level_divergence():
    # day 1 (Tue) sets the previous-day high; on day 2 NQ trades above it and ES does not
    d1 = dt.datetime(2026, 11, 16, 18, 0, tzinfo=NY)          # Tuesday 17 Nov session opens Monday 18:00
    nq = series(d1, 23 * 12, lambda i: 100 + (5 if i == 100 else 0), 5)
    es = series(d1, 23 * 12, lambda i: 50 + (5 if i == 100 else 0), 5)
    d2 = dt.datetime(2026, 11, 17, 18, 0, tzinfo=NY)
    nq += series(d2, 23 * 12, lambda i: 100 + (9 if 150 <= i <= 152 else 0), 5)
    es += series(d2, 23 * 12, lambda i: 50 + (2 if 150 <= i <= 152 else 0), 5)
    found = [f for f in smt.level_divergences(smt.aligned(nq, es), 3) if f["level"] == "previous day high"]
    assert len(found) == 1 and found[0]["leader"] == "NQ" and found[0]["direction"] == "bearish", found


def test_wilson_and_verdicts():
    lo, hi = smt.wilson(60, 100)
    assert 0.49 < lo < 0.51 and 0.69 < hi < 0.70
    assert smt.wilson(0, 0) == (None, None)


def test_real_bars():
    nq = bars.load("nq", "5m")
    if len(nq) < 500:
        print("skip: no NQ 5m archive")
        return
    rnd = random.Random(7)
    es = [(t, o / 4.7 + rnd.gauss(0, .4), h / 4.7 + rnd.gauss(0, .4), l / 4.7 + rnd.gauss(0, .4), c / 4.7) for t, o, h, l, c in nq]
    es = [(t, o, max(o, h, l, c), min(o, h, l, c), c) for t, o, h, l, c in es]
    t0 = time.time()
    loader = lambda m, iv: (bars.load("nq", iv) if m == "nq" else (es if iv == "5m" else []))
    doc = smt.build(dt.datetime(2026, 11, 26, 16, tzinfo=dt.timezone.utc), loader)
    assert time.time() - t0 < 60
    tf = doc["timeframes"]["5m"]
    assert tf["count"] > 10 and tf["stats"] and not smt.check(doc)
    for s in tf["stats"]:
        assert s["verdict"] in ("too few cases", "better than the base rate", "worse than the base rate", "no edge shown")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("smt tests passed")
