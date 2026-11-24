"""Offline tests for the registered discovery runner and publication receipts."""
import datetime as dt
import copy
import json
from pathlib import Path
import random
import discovery as D
import publication as P

def test_discovery():
    plan = json.loads(D.PLAN.read_text())
    random.seed(13)
    rows = []
    d = dt.date(2019, 1, 1)
    close = 100.
    while d < dt.date(2027,4,1):
        if d.weekday() < 5:
            old=close
            close *= 1+random.uniform(-.01,.01)
            rows.append((d.isoformat(),[old,max(old,close)+1,min(old,close)-1,close]))
        d += dt.timedelta(days=1)
    data = {m:rows for m in plan["markets"]}
    first = D.run(plan,data,dt.date(2026,11,24))
    assert len(first["batches"]) == 1
    assert len(first["batches"][0]["results"]) == 8
    assert all(not r["promoted"] for r in first["batches"][0]["results"])
    saved = copy.deepcopy(first)
    assert D.run(plan,data,dt.date(2026,12,1),first) == saved
    after = D.run(plan,data,dt.date(2027,3,2),first)
    assert len(after["batches"]) == 2 and after["batches"][0] == saved["batches"][0]
    changed = dict(plan, min_group=5)
    try:
        D.run(changed,data,dt.date(2027,3,2),after)
        raise AssertionError("changed plan accepted")
    except ValueError:
        pass
    assert D.run(plan,{},dt.date(2026,11,24))["batches"] == []

def test_receipt():
    t = dt.datetime(2026,11,24,22,30,tzinfo=dt.timezone.utc)
    cutoff = t+dt.timedelta(minutes=30)
    r = {"market":"nq","candle":"2026-11-24","for":"2026-11-25","logged":t.isoformat(),"eligible":True,"p_up":.55}
    rec = P.record([r],{},t+dt.timedelta(minutes=5),"run1")
    assert P.verified(r,rec,cutoff)
    assert not P.verified(dict(r,p_up=.56),rec,cutoff)
    assert not P.verified(r,{},cutoff)
    assert not P.verified(r,P.record([r],{},cutoff,"run2"),cutoff)
    assert P.record([r],rec,cutoff,"run2") == rec

if __name__ == "__main__":
    test_discovery()
    test_receipt()
    print("discovery and receipt tests passed")
