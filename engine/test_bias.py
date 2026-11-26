"""Offline checks for the daily bias (quant v2)."""
import datetime as dt
import json
import os
import random
import zlib
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
    rnd = random.Random(zlib.crc32(sid.encode()) % 1000)   # hash() changes every run (PYTHONHASHSEED): flaky
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
    now = dt.datetime.combine(dt.date.fromisoformat(last), dt.time(17, 30), B.NY).astimezone(dt.timezone.utc)
    assert B.run(now, fetch=lambda sym, rng="max": dict(data), fetch_series=series_fake, markets=["nq", "es"]) == 0
    doc = json.load(open(B.OUT))
    assert doc["order"] == ["nq", "es"] and doc["for"] == B.next_session(last)
    nq = doc["markets"]["nq"]
    assert nq["pv"] == 20 and nq["micro"] == 2 and len(nq["calendar"]) == len(B.EVENTS)
    new_session = {**data, last: [100, 110, 99, 102]}
    assert B.run(now + dt.timedelta(hours=2), fetch=lambda *args: new_session.copy(),
                 fetch_series=series_fake, markets=["nq", "es"]) == 0
    assert json.load(open(B.OUT))["markets"]["nq"] == nq
    row = next(row for row in json.load(open(B.LOG))["entries"] if row["market"] == "nq")
    assert B.PUB.matches(row, nq) and B.PUB.identity(row) == nq["forecast_id"]
    nd = B.next_session(last)
    data[nd] = [1, data[last][1] * 2, data[last][2] / 2, data[last][3] * 1.01]
    now2 = dt.datetime.combine(dt.date.fromisoformat(nd), dt.time(17, 30), B.NY).astimezone(dt.timezone.utc)
    B.run(now2, fetch=lambda sym, rng="max": dict(data), fetch_series=series_fake, markets=["nq", "es"])
    log = json.load(open(B.LOG))["entries"]
    done = [e for e in log if e["candle"] == last]
    assert len(done) == 2 and all(e["scored"] and e["up"] == 1 and e["highTaken"] and e["up1Hit"] for e in done)
    assert json.load(open(B.OUT))["live"]["nq"]["days"] == 0  # no verified deployment receipt
    assert all(e["eligible"] for e in log)          # 17:30 New York: after the close, before the 18:00 open


def test_fixes():
    # bad candles and gold's pre-2013 history are dropped
    rows = [("2012-06-01", [1, 2, 0.5, 1.5]), ("2013-01-02", [1, 1, 1, 1]), ("2013-01-03", [1, 2, 0.5, 1.5]),
            ("2013-01-04", [-1, 2, -3, -2])]
    assert [d for d, _ in B.clean("gold", rows)] == ["2013-01-03"]
    assert [d for d, _ in B.clean("nq", rows)] == ["2012-06-01", "2013-01-03"]
    # a weekly-published series is only used once public
    keys = ["2026-01-12", "2026-01-16"]
    v = B.lagged(keys, {"2026-01-05": 1.0, "2026-01-09": 2.0}, lag_days=7)
    assert v[0] == 1.0 and v[1] == 2.0
    # one bar across markets; equity indices must agree
    T = {m: {"signals": {"mom20": {"stable": True, "t": 4.0, "skill": 0.002}}, "events": {}} for m in ("nq", "es", "ym")}
    T["es"]["signals"]["mom20"]["skill"] = -0.001
    T["ym"]["signals"]["mom20"]["skill"] = -0.001
    B.decide(T, 3.0, 3.0)
    assert not T["nq"]["signals"]["mom20"]["tested"], "an index edge the other indices do not share is not trusted"
    T["es"]["signals"]["mom20"]["skill"] = 0.001
    B.decide(T, 3.0, 3.0)
    assert not T["nq"]["signals"]["mom20"]["tested"], "one of two other indices is not a majority"
    T["ym"]["signals"]["mom20"]["skill"] = 0.001
    B.decide(T, 3.0, 3.0)
    assert T["nq"]["signals"]["mom20"]["tested"]
    B.decide(T, 5.0, 3.0)
    assert not T["nq"]["signals"]["mom20"]["tested"]
    assert Q.z_needed(40) > 3.2


def test_completed_session_and_bars():
    from bars import completed
    now = dt.datetime.fromisoformat("2026-11-25T23:45:00+00:00")
    days = {"2026-11-24": [100, 104, 99, 102], "2026-11-25": [102, 104, 101, 103]}
    cache = {"days": days, "fetched": now.isoformat()}
    assert [day for day, _ in B.settled_rows("nq", cache, {}, now)[0]] == ["2026-11-24"]
    real = {"2026-11-25": {"complete": True, "full": True, "o": 104, "h": 108, "l": 100, "c": 101}}
    assert B.settled_rows("nq", cache, real, now)[0][-1] == ("2026-11-25", [104, 108, 100, 101])
    rows = {f"2026-11-25T23:{minute}:00+00:00": days["2026-11-25"] for minute in (30, 34, 40, 45)}
    assert set(completed(rows, "5m", now)) == {"2026-11-25T23:30:00+00:00", "2026-11-25T23:40:00+00:00"}


def test_sessions_keep_mondays():
    import bars
    rows, d = [], dt.datetime(2025, 1, 6, tzinfo=B.NY)  # a Monday
    rnd = random.Random(1)
    px = 100.0
    while len(rows) < 24 * 260:
        if not (d.weekday() == 5 or (d.weekday() == 4 and d.hour >= 17) or (d.weekday() == 6 and d.hour < 18)):
            o = px
            px *= 1 + rnd.gauss(0, 0.002)
            rows.append((d, o, max(o, px), min(o, px), px))
        d += dt.timedelta(hours=1)
    old = bars.load
    bars.load = lambda m, interval="1h": rows
    try:
        S = B.sessions("nq")
    finally:
        bars.load = old
    assert S and S["mondays"] > 40, S and S["mondays"]
    assert not S["overnight"]["passed"] and not S["momentum"]["passed"]



def test_despike_days_from_iron_brain():
    """A bad print in Yahoo's daily high is clipped to Iron Brain's clean session high and remembered; small gaps and
    incomplete sessions leave the candle alone, and a clean feed never extends a range."""
    import bias as B
    days = {"2026-11-23": [25561.5, 27137.0, 25426.75, 26808.0], "2026-11-24": [26888.0, 27036.0, 26684.0, 26831.0]}
    ib = {"nq": {"2026-11-23": {"h": 27090.5, "l": 25462.0, "rawH": 27137.0, "rawL": 25462.0, "complete": True, "full": True},
                 "2026-11-24": {"h": 26900.0, "l": 26700.0, "complete": False, "full": True}}}
    patches = {}
    notes = B.despike_days("nq", days, ib, patches)
    assert days["2026-11-23"] == [25561.5, 27090.5, 25426.75, 26808.0], days
    assert days["2026-11-24"] == [26888.0, 27036.0, 26684.0, 26831.0]
    assert patches["nq"]["2026-11-23"][:2] == [27090.5, 25426.75] and "27,137.00" in notes[0]
    # next run: Iron Brain's window has moved on and Yahoo serves the bad print again; the patch still applies
    again = {"2026-11-23": [25561.5, 27137.0, 25426.75, 26808.0]}
    B.despike_days("nq", again, {}, patches)
    assert again["2026-11-23"][1] == 27090.5
    # a tiny difference (minutes missing from the 1-minute feed) changes nothing
    d2 = {"2026-11-23": [100.0, 110.0, 90.0, 105.0]}
    B.despike_days("gold", d2, {"gold": {"2026-11-23": {"h": 109.95, "l": 90.05, "complete": True, "full": True}}}, {})
    assert d2["2026-11-23"] == [100.0, 110.0, 90.0, 105.0]
    # a different window (Yahoo's low below anything the minute bars saw, no spike there) is left alone
    d3 = {"2026-11-23": [3570.5, 3691.0, 3552.3, 3651.4]}
    B.despike_days("gold", d3, {"gold": {"2026-11-23": {"h": 3691.0, "l": 3566.3, "rawH": 3691.0, "rawL": 3566.3, "complete": True, "full": True}}}, {})
    assert d3["2026-11-23"] == [3570.5, 3691.0, 3552.3, 3651.4]


def test_nyse_holidays_and_preholiday():
    """The exchanges' holiday rules (observed dates, Good Friday, Juneteenth from 2022) and the pre-holiday flag."""
    assert sorted(B.nyse_holidays(2026)) == ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
                                             "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"]
    assert "2027-12-24" in B.nyse_holidays(2027) and "2021-12-31" not in B.nyse_holidays(2022)   # Sat New Year: no Friday
    assert "2021-06-18" not in B.nyse_holidays(2021) and "2012-10-29" in B.nyse_holidays(2012)
    days, d = [], dt.date(2025, 11, 3)
    while d <= dt.date(2026, 11, 24):
        if d.weekday() < 5 and d.isoformat() not in B.nyse_holidays(d.year):
            days.append(d.isoformat())
        d += dt.timedelta(days=1)
    rows = [(k, [100.0 + i % 7, 101.5 + i % 7, 99.0 + i % 7, 100.5 + i % 5]) for i, k in enumerate(days)]
    F, S = B.build(rows, {}, set())
    pre = [k for k, v in zip(days, F["preholiday"]) if v]
    # each is the day BEFORE the forecast session, which itself precedes a holiday
    assert "2026-11-24" in pre and "2026-11-23" not in pre                 # forecast for Wed 25 Nov: Thanksgiving next
    assert "2026-07-01" in pre                                             # Thu 2 Jul, then the 3 Jul holiday
    assert 8 <= len(pre) <= 11


if __name__ == "__main__":
    test_quant_basics()
    test_random_walk_finds_no_direction_but_real_volatility()
    test_run_end_to_end()
    test_fixes()
    test_completed_session_and_bars()
    test_sessions_keep_mondays()
    test_despike_days_from_iron_brain()
    test_nyse_holidays_and_preholiday()
    print("bias tests passed")
