"""Tests for engine/intraday.py: Iron Brain's live plans, witnessed and scored by Displace's rules."""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intraday as I

UTC = dt.timezone.utc


def t(h, m):                                    # a reading on 25 Nov 2026, New York = UTC-5
    return dt.datetime(2026, 11, 25, h + 5, m, tzinfo=UTC)


ORB = {"date": "2026-11-25", "market": "nq", "id": "orb-0930", "name": "ORB 09:30", "lockedAt": "2026-11-25 09:47",
       "state": "orders", "buyStop": 21010.0, "sellStop": 20990.0}
FILL = dict(ORB, state="signal", dir="LONG", entry=21010.0, stop=20980.0, at="09:45", filledAt="2026-11-25 10:05")
DRIVE = {"date": "2026-11-25", "market": "nq", "id": "drive-v2", "lockedAt": "2026-11-25 10:13", "state": "signal",
         "dir": "SHORT", "entry": 21000.0, "stop": 21040.0, "at": "10:00"}


def run(*readings):
    store = {"records": {}}
    for now, rows in readings:
        I.observe(store, rows, now)
    return {r["id"]: r for r in I.report(store, t(17, 0))["records"]}, store


def test_counted_trade():
    """Orders locked before the fill, seen live, then the result: counted, with points and R."""
    recs, _ = run((t(9, 50), [ORB]), (t(10, 10), [FILL]), (t(11, 0), [dict(FILL, stage="target", exit=21070.0, resultPts=60.0)]))
    r = recs["orb-0930"]
    assert r["status"] == "counted" and r["lag"] == 0 and r["r"] == 2.0, r


def test_late_lock_and_unwitnessed():
    """Locked 13 minutes after its entry minute: scored apart, with the lag. First seen finished: unwitnessed."""
    done = dict(DRIVE, stage="stopped", exit=21040.0, resultPts=-40.0)
    recs, _ = run((t(10, 20), [DRIVE]), (t(12, 0), [done]))
    assert recs["drive-v2"]["status"] == "late_lock" and recs["drive-v2"]["lag"] == 13 and recs["drive-v2"]["r"] == -1.0
    recs, _ = run((t(12, 0), [done]))
    assert recs["drive-v2"]["status"] == "unwitnessed"


def test_changed_levels_and_other_states():
    """A locked level that changes after it was seen is flagged; no trade, expired orders and pending are kept apart."""
    recs, store = run((t(9, 50), [ORB]), (t(10, 0), [dict(ORB, buyStop=21020.0)]))
    assert recs["orb-0930"]["status"] == "altered" and store["records"]["2026-11-25|nq|orb-0930"]["changed"][0]["was"] == 21010.0
    none = {"date": "2026-11-25", "market": "nq", "id": "drive-v2", "lockedAt": "2026-11-25 10:12", "state": "none",
            "note": "No trade today: the setup's conditions weren't met."}
    recs, _ = run((t(10, 20), [none, ORB]))
    assert recs["drive-v2"]["status"] == "no_trade" and recs["orb-0930"]["status"] == "pending"
    recs, _ = run((t(9, 50), [ORB]), (t(14, 30), [dict(ORB, stage="expired")]))
    assert recs["orb-0930"]["status"] == "expired"
    recs, _ = run((t(9, 50), [dict(ORB, date="2026-11-24")]))
    assert recs == {}                            # before the witness started: not recorded


def test_report_and_files():
    """The scorecard: counted trades only, the claim threshold, the late group's lag; files round-trip."""
    rows = [(t(9, 50), [ORB]), (t(10, 10), [FILL]), (t(11, 0), [dict(FILL, stage="stopped", exit=20980.0, resultPts=-30.0)])]
    store = {"records": {}}
    for now, rs in rows:
        I.observe(store, rs, now)
    doc = I.report(store, t(17, 0))
    s = doc["strategies"]["orb-0930"]
    assert s["trades"] == 1 and s["points"] == -30.0 and s["mean_r"] == -1.0 and "too few" in s["verdict"]
    assert s["counts"]["counted"] == 1 and sum(s["counts"].values()) == 1 and s["late"]["trades"] == 0
    d = tempfile.mkdtemp()
    I.write(d + "/w.json", store)
    assert I.load(d + "/w.json") == store and I.load(d + "/missing.json") == {"version": 1, "records": {}}


if __name__ == "__main__":
    test_counted_trade()
    test_late_lock_and_unwitnessed()
    test_changed_levels_and_other_states()
    test_report_and_files()
    print("intraday tests passed")
