"""Offline checks for the daily bias (quant v2)."""
import datetime as dt
import json
import os
import random
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import bias as B
import quant as Q


def synthetic(n=2600, seed=3, start=dt.date(2008, 1, 1), drift=0.0004, vol=0.012):
    rnd = random.Random(seed)
    d, px, out, v = start, 100.0, {}, vol
    while len(out) < n:
        d += dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        v = max(0.004, 0.97 * v + 0.03 * vol + rnd.gauss(0, 0.0008))  # clustered volatility, like real markets
        o = px
        c = o * (1 + rnd.gauss(drift, v))
        h, l = max(o, c) * (1 + abs(rnd.gauss(0, v / 2))), min(o, c) * (1 - abs(rnd.gauss(0, v / 2)))
        out[d.isoformat()] = [round(o, 4), round(h, 4), round(l, 4), round(c, 4)]
        px = c
    return out


def series_fake(sid, start="1999-01-01"):
    rnd = random.Random(hash(sid) % 1000)
    d, v, out = dt.date(2005, 1, 3), 20.0, []
    while d < dt.date(2026, 12, 1):
        if d.weekday() < 5:
            v = max(5.0, v + rnd.gauss(0, 0.6))
            out.append((d.isoformat(), round(v, 3)))
        d += dt.timedelta(days=1)
    return out


def test_quant_basics():
    x = np.linspace(-2, 2, 400)[:, None]
    y = (x[:, 0] > 0).astype(float)
    assert Q.logit_fit(x, y)[1] > 0
    assert abs(Q.t_needed(6) - 2.394) < 0.01 and Q.t_needed(13) > 2.6
    keys = ["2026-01-05", "2026-01-06", "2026-01-07"]
    v = B.lagged(keys, {"2026-01-05": 1.0, "2026-01-06": 2.0})
    assert np.isnan(v[0]) and v[1] == 1.0 and v[2] == 2.0  # never the same day's value
    assert B.next_session("2026-11-20") == "2026-11-23"


def test_random_walk_finds_no_direction_but_real_volatility():
    rows = sorted(synthetic().items())
    series = {sid: dict(series_fake(sid)) for sid in B.SERIES}
    r = B.read("nq", rows, series, {}, set())
    assert not [s for s in r["signals"] if s["tested"]], "noise must not pass the direction tests"
    assert r["tier"] == "base" and r["p_up"] == r["base_up"]
    assert r["takes"]["high"]["tested"] and r["takes"]["low"]["tested"]
    assert 0 < r["range"]["lo"] < r["range"]["points"] < r["range"]["hi"]
    assert r["vol"]["stats"]["gain"] > 0, "HAR should beat a 20-day average when volatility clusters"
    assert 0.7 < r["vol"]["stats"]["coverage"] < 0.9
    ks = [t["k"] for t in r["touch"]]
    assert ks == list(B.TOUCH_K) and r["touch"][0]["up_p"] > r["touch"][-1]["up_p"]
    assert r["touch"][1]["dn"] < r["levels"]["close"] < r["touch"][1]["up"]


def test_run_end_to_end():
    tmp = tempfile.mkdtemp()
    B.OUT, B.LOG, B.CACHE_DIR, B.DATA, B.TV_DIR, B.SERIES_DIR = (
        os.path.join(tmp, "bias", "current.json"), os.path.join(tmp, "bias", "log.json"), os.path.join(tmp, "cache"),
        tmp, os.path.join(tmp, "tv"), os.path.join(tmp, "series"))
    data = synthetic()
    last = max(data)
    now = dt.datetime.combine(dt.date.fromisoformat(last), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    assert B.run(now, fetch=lambda sym, rng="max": dict(data), fetch_series=series_fake, markets=["nq", "es"]) == 0
    doc = json.load(open(B.OUT))
    assert doc["order"] == ["nq", "es"] and doc["for"] == B.next_session(last)
    nq = doc["markets"]["nq"]
    assert nq["pv"] == 20 and nq["micro"] == 2 and len(nq["calendar"]) == len(B.EVENTS)
    nd = B.next_session(last)
    data[nd] = [1, data[last][1] * 2, data[last][2] / 2, data[last][3] * 1.01]
    now2 = dt.datetime.combine(dt.date.fromisoformat(nd), dt.time(18, 30), B.NY).astimezone(dt.timezone.utc)
    B.run(now2, fetch=lambda sym, rng="max": dict(data), fetch_series=series_fake, markets=["nq", "es"])
    log = json.load(open(B.LOG))["entries"]
    done = [e for e in log if e["candle"] == last]
    assert len(done) == 2 and all(e["scored"] and e["up"] == 1 and e["highTaken"] and e["up1Hit"] for e in done)
    assert json.load(open(B.OUT))["live"]["nq"]["days"] == 1


if __name__ == "__main__":
    test_quant_basics()
    test_random_walk_finds_no_direction_but_real_volatility()
    test_run_end_to_end()
    print("bias tests passed")
