"""News-outcome engine (predict.py) end to end, offline, on the simulated world from test_direction.py.

Checks: first fit from FRED, schema the site reads, scenario map for gold and the Nasdaq, leans only where
proven, post-release calls logged only between the release and the close, scoring, no refit when nothing
changed, history extended from the calendar without FRED, and GDP revisions ignored."""
import datetime as dt
import importlib
import json
import os
import shutil
import sys
import tempfile
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
NY = ZoneInfo("America/New_York")


def setup(tmp):
    shutil.copytree(HERE, os.path.join(tmp, "engine"), ignore=shutil.ignore_patterns("cache", "__pycache__", "test_*"))
    shutil.copy(os.path.join(HERE, "test_direction.py"), os.path.join(tmp, "engine"))
    os.makedirs(os.path.join(tmp, "site", "data", "calendar"))
    os.makedirs(os.path.join(tmp, "site", "data", "history"))
    events = [
        {"id": "cpi-oct", "date": "2026-11-12", "time": "08:30", "title": "CPI inflation (Oct)", "impact": "high",
         "cur": "USD", "src": "BLS", "actual": "0.6%", "forecast": "0.2%",
         "components": [{"label": "Core CPI m/m", "actual": "0.6%"}, {"label": "CPI m/m", "actual": "0.7%"}]},
        {"id": "cpi-nov", "date": "2026-11-24", "time": "08:30", "title": "CPI inflation (Nov)", "impact": "high",
         "cur": "USD", "src": "BLS"},
        {"id": "gdp-2nd", "date": "2026-11-25", "time": "08:30", "title": "GDP, second estimate (Q3)", "impact": "high",
         "cur": "USD", "src": "BEA"},
    ]
    json.dump({"updated": "2026-11-12", "events": events}, open(os.path.join(tmp, "site", "data", "calendar", "events.json"), "w"))
    return events


def load_modules(tmp):
    eng = os.path.join(tmp, "engine")
    for m in list(sys.modules):
        if m in ("engine", "fredapi", "catalog", "calendar_rules", "direction", "prices", "quality", "predict",
                 "series_store", "agencies", "publicdata", "source_health", "test_direction"):
            sys.modules.pop(m)
    sys.path.insert(0, eng)
    T = importlib.import_module("test_direction")
    P = importlib.import_module("predict")
    return T, P


class Fred:
    def __init__(self, fetch, key="test"):
        self.KEY, self.fetch, self.calls = key, fetch, 0

    def observations(self, sid, start, initial=False):
        self.calls += 1
        return self.fetch(sid, start, initial=initial)


def main():
    tmp = tempfile.mkdtemp()
    try:
        setup(tmp)
        T, P = load_modules(tmp)
        fetch, gold = T.world(1, end=dt.date(2026, 11, 13))
        # the simulated world already has an Oct CPI print on Nov 12; drop it so the calendar supplies it
        series = {s: fetch(s, "2000-01-01") for s in ("CPILFESL", "CPIAUCSL", "ICSA", "DFF", "DTWEXBGS", "DEXUSEU", "DGS2", "DGS10")}
        for s in ("CPILFESL", "CPIAUCSL"):
            series[s] = [o for o in series[s] if o[2] < "2026-11-12"]

        def fred_fetch(s, start, initial=False):
            return [o for o in series.get(s) or [] if o[0] >= start] or None
        gold_rows = {d: v for d, v in gold("2000-01-01")[0]}
        nq_rows = {d: v for d, v, _ in fetch("NASDAQ100", "2000-01-01")}
        P.prices.MARKETS["gold"] = ([("sim gold", lambda: gold_rows)], False)
        P.prices.MARKETS["nq"] = ([("sim nq", lambda: nq_rows)], True)
        P.series_store.agencies.market_observations = lambda *a: []

        # 1. Release morning, 10:00 NY: first fit, post-release call for today, scenario map for the next CPI
        fred = Fred(fred_fetch)
        assert P.run(now=dt.datetime(2026, 11, 12, 10, 0, tzinfo=NY), fred=fred)
        out = json.load(open(os.path.join(tmp, "site", "data", "direction", "current.json")))
        for key in ("asof", "assets", "regime", "rules", "backtest", "live", "proven", "scenarios", "events", "disclaimer"):
            assert key in out, key
        assert {"gold", "nq"} <= set(out["assets"]), out["assets"]
        sc = out["scenarios"]["cpi"]["assets"]
        assert sc["gold"]["hot"]["up"] < 0.45 < sc["gold"]["cool"]["up"], sc["gold"]  # gold falls on hot CPI in this world
        assert "nq" in sc and sc["nq"]["hot"]["n"] > 10
        assert out["rules"]["cpi:gold"]["proven"] and not out["rules"]["cpi:nq"]["proven"]
        pre = out["events"]["cpi-nov"]
        assert pre["stage"] == "pre" and pre["hot"]["gold"]["dir"] == "down" and pre["cool"]["gold"]["dir"] == "up", pre
        assert pre["hot"]["nq"].get("none"), "a lean was published for an unproven rule"
        post = out["events"]["cpi-oct"]
        assert post["stage"] == "post" and post["bin"] == "hot" and post["calls"]["gold"]["dir"] == "down", post
        assert "gdp-2nd" not in out["events"], "GDP revision treated as a first release"
        logged = json.load(open(os.path.join(tmp, "site", "data", "direction", "log.json")))["rows"]
        assert {(r["id"], r["asset"]) for r in logged} >= {("cpi-oct", "gold")}, logged
        assert not any("hit" in r for r in logged), "scored a call before the close was settled"
        print("first run:", out["proven"], "proven rules; live", out["live"]["hits"], "/", out["live"]["calls"])

        # 2. History extended from the calendar with no FRED key: Oct CPI appended as the next period
        last = P.series_store.load("CPILFESL", True)["rows"][-1]
        assert last[0] == "2026-10-01" and last[2] == "2026-11-12", last
        prev = P.series_store.load("CPILFESL", True)["rows"][-2]
        assert abs((last[1] / prev[1] - 1) * 100 - 0.6) < 1e-9
        headline = P.series_store.load("CPIAUCSL", True)["rows"][-1]
        assert headline[2] == "2026-11-12"

        # 3. Same day, later run with nothing new: no refit, no FRED refresh, no duplicate log rows
        P.LOGLINES.clear()
        fred2 = Fred(fred_fetch)
        assert P.run(now=dt.datetime(2026, 11, 12, 10, 20, tzinfo=NY), fred=fred2)
        assert not any("fitting" in x or "first fit" in x for x in P.LOGLINES), P.LOGLINES
        assert fred2.calls == 0, "refetched history that was fresh"
        again = json.load(open(os.path.join(tmp, "site", "data", "direction", "log.json")))["rows"]
        assert len(again) == len(logged)

        # 4. After the close: the post-release lean is withdrawn, nothing new is logged, and the calls are scored
        assert P.run(now=dt.datetime(2026, 11, 12, 17, 30, tzinfo=NY), fred=Fred(fred_fetch, key=""))
        out = json.load(open(os.path.join(tmp, "site", "data", "direction", "current.json")))
        assert "cpi-oct" not in out["events"] and "cpi-nov" in out["events"]
        scored = json.load(open(os.path.join(tmp, "site", "data", "direction", "log.json")))["rows"]
        assert len(scored) == len(logged) and all("hit" in r for r in scored if r["asset"] in ("gold", "nq")), scored
        assert out["live"]["calls"] >= 1

        # 5. A gap in the calendar never shifts the history: a release two periods ahead is not appended
        added = P.series_store.extend_from_events(
            [{"id": "x", "date": "2027-01-13", "time": "08:30", "title": "CPI inflation (Dec)", "actual": "0.3%"}],
            P.D.MODELS, P.RELEASES, P.kind_for(importlib.import_module("engine").kind_of),
            importlib.import_module("engine").title_period, P.D.figure, log=lambda *a: None)
        assert added == 0
        print("predict tests passed")
    finally:
        sys.path.pop(0)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
