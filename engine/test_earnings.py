import datetime as dt, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import earnings as E

TODAY = dt.date(2026, 11, 18)
SEED = [{"t": "AVGO", "date": "2026-12-09", "session": "AMC", "period": "Q4 FY26"}, {"t": "NVDA", "date": "2026-11-17", "session": "AMC", "time": "16:20"}]

def fake(rows_by_day):
    return lambda d: rows_by_day.get(d.isoformat(), [])

def test_seed_wins_over_calendar():
    f = fake({"2026-12-10": [{"symbol": "AVGO", "time": "time-after-hours"}], "2026-12-07": [{"symbol": "COST", "time": "time-after-hours", "fiscalQuarterEnding": "Nov/2026"}]})
    ev, ok = E.build(SEED, TODAY, days=30, fetch=f, pause=0)
    ids = [e["id"] for e in ev]
    assert ok and "20261209-earn-avgo" in ids and "20261210-earn-avgo" not in ids
    avgo = next(e for e in ev if e["id"].endswith("avgo"))
    assert avgo["status"] == "confirmed" and avgo["time"] == "16:05" and avgo["impact"] == "earnings" and avgo["tier"] == "mega"
    cost = next(e for e in ev if e["id"].endswith("cost"))
    assert cost["status"] == "scheduled" and cost["session"] == "AMC" and "Nov 2026" in cost["title"]

def test_ignores_unwatched_and_weekends():
    seen = []
    def f(d): seen.append(d); return [{"symbol": "ZZZZ", "time": ""}]
    ev, ok = E.build([], TODAY, days=14, fetch=f, pause=0)
    assert all(d.weekday() < 5 for d in seen) and ev == []

def test_unreachable_keeps_previous_and_seed():
    prev = [E.event("COST", "2026-12-10", "AMC", "scheduled", E.SRC_NQ), E.event("AAPL", "2026-02-01", "AMC", "scheduled", E.SRC_NQ)]
    ev, ok = E.build(SEED, TODAY, days=30, fetch=lambda d: None, pause=0, previous=prev)
    ids = [e["id"] for e in ev]
    assert not ok and "20261210-earn-cost" in ids and "20261209-earn-avgo" in ids and "20260201-earn-aapl" not in ids

def test_time_unknown_has_no_time():
    ev, _ = E.build([], TODAY, days=10, fetch=fake({"2026-11-19": [{"symbol": "AMD", "time": "time-not-supplied"}]}), pause=0)
    assert ev[0]["time"] == "" and ev[0]["session"] == ""

def test_weekend_seed_is_not_special():
    ev, _ = E.build([{"t": "TSLA", "date": "2026-12-12", "session": "AMC"}], TODAY, days=3, fetch=fake({}), pause=0)
    assert ev and ev[0]["date"] == "2026-12-12"

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
