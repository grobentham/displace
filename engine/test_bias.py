"""Offline checks for the daily bias (quant version)."""
import datetime as dt
import json
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bias as B


def synthetic(n=1800, seed=3, start=dt.date(2015, 1, 1)):
    rnd = random.Random(seed)
    d, px, out = start, 100.0, {}
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        o = px
        c = o * (1 + rnd.gauss(0.0004, 0.012))
        h, l = max(o, c) * (1 + abs(rnd.gauss(0, 0.005))), min(o, c) * (1 - abs(rnd.gauss(0, 0.005)))
        out[d.isoformat()] = [round(o, 4), round(h, 4), round(l, 4), round(c, 4)]
        px = c
    return out


def test_basics():
    days = {"2026-11-18": [1, 2, 0.5, 1.5], "2026-11-19": [1, 2, 0.5, 1.5]}
    at = lambda h: dt.datetime(2026, 11, 19, h, 0, tzinfo=B.NY)
    assert [d for d, _ in B.finished(days, at(16))] == ["2026-11-18"]
    assert [d for d, _ in B.finished(days, at(18))] == ["2026-11-18", "2026-11-19"]
    assert B.next_session("2026-11-20") == "2026-11-23"
    b = B.logit_fit([[x / 10] for x in range(-20, 21)], [1 if x > 0 else 0 for x in range(-20, 21)])
    assert b[1] > 0  # a logistic fit finds the obvious slope


def test_random_walk_has_no_direction_edge():
    rows = sorted(synthetic().items())
    r = B.read("nq", rows, set())
    assert not [s for s in r["signals"] if s["tested"]], "a random walk should not pass the direction tests"
    assert r["tier"] == "base" and abs(r["p_up"] - r["base_up"]) < 1e-9
    # but the levels model has real skill: a close near the high makes taking the high likelier
    assert r["takes"]["high"]["tested"] and r["takes"]["low"]["tested"]
    assert r["range"]["lo"] < r["range"]["points"] < r["range"]["hi"]
    assert r["band"]["lo"] < r["levels"]["close"] < r["band"]["hi"]


def test_run_end_to_end():
    tmp = tempfile.mkdtemp()
    B.OUT, B.LOG, B.CACHE_DIR, B.DATA, B.TV_DIR = (os.path.join(tmp, "bias", "current.json"), os.path.join(tmp, "bias", "log.json"),
                                                   os.path.join(tmp, "cache"), tmp, os.path.join(tmp, "tv"))
    data = synthetic()
    last = max(data)
    now = dt.datetime.combine(dt.date.fromisoformat(last), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    assert B.run(now, fetch=lambda sym, rng="max": dict(data)) == 0
    doc = json.load(open(B.OUT))
    nq = doc["markets"]["nq"]
    assert nq["candle"] == last and doc["for"] == B.next_session(last)
    assert 0.1 <= nq["p_up"] <= 0.9 and nq["bias"] in ("long", "short", "neutral")
    assert len(nq["signals"]) == len(B.SIGNALS) and len(nq["calendar"]) == len(B.EVENTS)
    nd = B.next_session(last)
    data[nd] = [1, data[last][1] * 2, data[last][2] / 2, data[last][3] * 1.01]
    now2 = dt.datetime.combine(dt.date.fromisoformat(nd), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    B.run(now2, fetch=lambda sym, rng="max": dict(data))
    log = json.load(open(B.LOG))["entries"]
    done = [e for e in log if e["candle"] == last]
    assert done and all(e["scored"] and e["up"] == 1 and e["highTaken"] == 1 and e["lowTaken"] == 1 for e in done)
    assert json.load(open(B.OUT))["live"]["nq"]["days"] == 1


if __name__ == "__main__":
    test_basics()
    test_random_walk_has_no_direction_edge()
    test_run_end_to_end()
    print("bias tests passed")
