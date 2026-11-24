"""News-outcome engine v4 end to end, offline: consensus surprises from a fake TradingView cache, a world
where hot CPI pushes gold down in the first two hours, and the full publish / log / score cycle."""
import datetime as dt
import json
import os
import random
import shutil
import sys
import tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

import predict as P  # noqa: E402


def build(tmp):
    rnd = random.Random(7)
    P.tv.CACHE_DIR = os.path.join(tmp, "tv")
    os.makedirs(P.tv.CACHE_DIR)
    raw, hourly, daily = [], [], {a: [] for a in ("gold", "nq", "usd", "y2")}
    lv = {"gold": 2000.0, "nq": 15000.0, "usd": 110.0, "y2": 3.0}
    day = dt.date(2010, 1, 1)
    surprises = {}
    while day <= dt.date(2026, 11, 13):
        if day.weekday() < 5:
            when = dt.datetime.combine(day, dt.time(8, 30), NY)
            z = 0.0
            if day.day == 12 or (day.day in (13, 14) and day.weekday() == 0):
                if day.strftime("%Y-%m") not in surprises:
                    f = round(rnd.gauss(0.25, 0.1), 1)
                    z = rnd.gauss(0, 1)
                    a = round(f + 0.1 * z, 1)
                    if day == dt.date(2026, 11, 12):
                        f, a = 0.2, 0.6
                    surprises[day.strftime("%Y-%m")] = (when, a - f)
                    raw.append({"t": "Core Inflation Rate MoM", "d": when.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                                "a": a, "f": f, "p": None, "u": "%", "s": None})
                    z = (a - f) / 0.1
            for k in lv:
                r = rnd.gauss(0, 0.6) + (0.4 * z if k == "y2" else 0)
                lv[k] = lv[k] + r / 100 if k == "y2" else lv[k] * (1 + r / 100)
                daily[k].append((day.isoformat(), lv[k]))
            if day.year >= 2021:
                o = lv["gold"]
                c = o * (1 + (rnd.gauss(0, 0.15) - 0.35 * z) / 100)
                s = when.replace(minute=0)
                hourly += [(s, o, o, o, o), (s + dt.timedelta(hours=1), c, c, c, c)]
        day += dt.timedelta(days=1)
    # an upcoming CPI with a consensus only
    raw.append({"t": "Core Inflation Rate MoM", "d": "2026-11-24T13:30:00Z", "a": None, "f": 0.3, "p": 0.6, "u": "%", "s": None})
    with open(os.path.join(P.tv.CACHE_DIR, "all.json"), "w") as fh:
        json.dump(raw, fh)
    P.tv.sync = lambda *a, **k: 0
    P.prices.closes = lambda a, s, **k: ([r for r in daily[a] if r[0] >= s], "sim")
    P.prices.ranges = lambda a, s: [(d, v * 1.01, v * 0.99, v) for d, v in daily[a] if d >= s]
    P.bars.sync = lambda *a, **k: None
    P.bars.load = lambda m, interval="1h": hourly if m == "gold" and interval == "1h" else []
    P.bars._load = lambda m, interval="1h": {"fetched": "2026-11-12T20:00:00+00:00"}
    store = lambda sid, start, initial=False: [(d, v, "") for d, v in daily["usd" if sid == "DTWEXBGS" else "y2"] if d >= start]
    P.OUT = os.path.join(tmp, "current.json")
    P.LOG_PATH = os.path.join(tmp, "log.json")
    return store


def main():
    tmp = tempfile.mkdtemp()
    try:
        store = build(tmp)
        events = [{"id": "cpi-oct", "date": "2026-11-12", "time": "08:30", "title": "CPI inflation (Oct)", "actual": "0.6%"},
                  {"id": "cpi-nov", "date": "2026-11-24", "time": "08:30", "title": "CPI inflation (Nov)"}]
        kind_of = lambda e: "cpi" if e["title"].startswith("CPI") else None
        # 1. release morning, 09:00: lean for the first 2 hours, logged; scenario for the next CPI
        out = P.run(now=dt.datetime(2026, 11, 12, 9, 0, tzinfo=NY), kind_of=kind_of, events=events, store=store)
        g = out["groups"]["inflation"]
        assert g["gold2h"]["proven"] and g["gold2h"]["b"] < 0, g["gold2h"]
        assert g["y2"]["proven"] and g["y2"]["b"] > 0, g["y2"]
        assert not g["nq"]["proven"] and not g["gold"]["proven"]
        assert "eur" not in out["assets"] and set(out["assets"]) >= {"gold2h", "gold", "nq", "usd", "y2"}
        pre = out["events"]["cpi-nov"]
        assert pre["stage"] == "pre" and pre["hot"]["gold2h"]["dir"] == "down" and pre["cool"]["gold2h"]["dir"] == "up"
        assert pre["consensus"]["forecast"] == 0.3
        post = out["events"]["cpi-oct"]
        assert post["stage"] == "post" and post["z"] > 2 and post["calls"]["gold2h"]["dir"] == "down", post
        logged = json.load(open(P.LOG_PATH))["rows"]
        assert any(r["asset"] == "gold2h" and r["dir"] == "down" for r in logged), logged
        assert not any("hit" in r for r in logged), "scored before the window closed"
        sc = out["scenarios"]["cpi"]["assets"]["gold2h"]
        assert sc["hot"]["up"] < 0.4 < 0.6 < sc["cool"]["up"], sc
        # 2. after the close: no lean shown, the 2-hour call is scored (bars fetched after the window)
        P.bars._load = lambda m, interval="1h": {"fetched": "2026-11-12T22:00:00+00:00"}
        out = P.run(now=dt.datetime(2026, 11, 12, 18, 0, tzinfo=NY), kind_of=kind_of, events=events, store=store)
        assert "cpi-oct" not in out["events"]
        rows = json.load(open(P.LOG_PATH))["rows"]
        assert all("hit" in r for r in rows if r["asset"] == "gold2h") and out["live"]["calls"] == 0 and out["live"]["historicalOnly"] >= 1, rows
        n = len(rows)
        out = P.run(now=dt.datetime(2026, 11, 12, 19, 0, tzinfo=NY), kind_of=kind_of, events=events, store=store)
        assert len(json.load(open(P.LOG_PATH))["rows"]) == n, "logged the same call twice"
        print("predict v4 tests passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
