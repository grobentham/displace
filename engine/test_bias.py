"""Offline checks for the bias of the day."""
import datetime as dt
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bias as B


def candle(o, h, l, c):
    return [o, h, l, c]


def test_rules():
    prev = candle(100, 110, 90, 100)
    assert B.classify(prev, candle(100, 115, 95, 112)) == "close_above"
    assert B.classify(prev, candle(100, 105, 85, 88)) == "close_below"
    assert B.classify(prev, candle(100, 112, 95, 105)) == "failed_high"
    assert B.classify(prev, candle(100, 105, 88, 95)) == "failed_low"
    assert B.classify(prev, candle(100, 108, 92, 101)) == "inside"
    assert B.classify(prev, candle(100, 112, 88, 101)) == "both"
    # direction is close-to-close, draw is the candle's own high/low
    assert B.outcome(candle(0, 112, 95, 110), candle(0, 113, 100, 111), "long") == (True, True)
    assert B.outcome(candle(0, 112, 95, 110), candle(0, 111, 100, 109), "long") == (False, False)
    assert B.outcome(candle(0, 112, 95, 100), candle(0, 105, 94, 99), "short") == (True, True)


def test_finished_and_session():
    days = {"2026-11-18": [1, 2, 0.5, 1.5], "2026-11-19": [1, 2, 0.5, 1.5], "2026-11-20": [1, 2, 0.5, 1.5]}
    at = lambda h: dt.datetime(2026, 11, 19, h, 0, tzinfo=B.NY)
    assert [d for d, _ in B.finished(days, at(16))] == ["2026-11-18"]
    assert [d for d, _ in B.finished(days, at(18))] == ["2026-11-18", "2026-11-19"]
    assert B.next_session("2026-11-20") == "2026-11-23"  # Friday -> Monday


def synthetic(n=900, seed=3):
    rnd = random.Random(seed)
    d, px, out = dt.date(2020, 1, 1), 100.0, {}
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        o = px
        c = o * (1 + rnd.gauss(0.0004, 0.012))
        h, l = max(o, c) * (1 + abs(rnd.gauss(0, 0.005))), min(o, c) * (1 - abs(rnd.gauss(0, 0.005)))
        out[d.isoformat()] = [round(o, 2), round(h, 2), round(l, 2), round(c, 2)]
        px = c
    return out


def test_run_end_to_end():
    tmp = tempfile.mkdtemp()
    B.OUT, B.LOG, B.CACHE_DIR, B.DATA = (os.path.join(tmp, "bias", "current.json"), os.path.join(tmp, "bias", "log.json"),
                                         os.path.join(tmp, "cache"), tmp)
    data = synthetic()
    last = max(data)
    fake = lambda sym, rng="max": dict(data)
    now = dt.datetime.combine(dt.date.fromisoformat(last), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    assert B.run(now, fetch=fake) == 0
    doc = json.load(open(B.OUT))
    assert set(doc["markets"]) == {"nq", "gold"}
    nq = doc["markets"]["nq"]
    assert nq["candle"] == last and doc["for"] == B.next_session(last)
    assert nq["bias"] in ("long", "short", "neutral") and nq["named"]
    rec = doc["markets"]["nq"]["record"]
    assert rec["n"] > 10
    st = B.study(B.finished(data, dt.datetime.combine(dt.date.fromisoformat(last), dt.time(18), B.NY)))
    for k, v in st["cases"].items():
        if B.CASES[k][0] != "neutral":
            assert 0 <= v["dir"] <= 1 and "zones" in v and v["late"]["n"] <= v["n"]
    # the next day finishes: yesterday's call is scored once, and a new one is logged
    nd = B.next_session(last)
    data[nd] = [1, 1e9, 0.0001, data[last][3] * 1.01]
    now2 = dt.datetime.combine(dt.date.fromisoformat(nd), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    B.run(now2, fetch=lambda sym, rng="max": dict(data))
    log = json.load(open(B.LOG))["entries"]
    scored = [e for e in log if e["candle"] == last and e["bias"] != "neutral"]
    assert all("hit" in e and e["drawHit"] == 1 for e in scored)
    assert len([e for e in log if e["market"] == "nq"]) == 2


if __name__ == "__main__":
    test_rules()
    test_finished_and_session()
    test_run_end_to_end()
    print("bias tests passed")
