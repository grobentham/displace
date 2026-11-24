import datetime as dt
import json
import random
import copy
import discovery_v2 as V
import macro as M

def test_macro():
    today=dt.date(2026,11,24)
    rows=[((today-dt.timedelta(days=300-i)).isoformat(),i) for i in range(301)]
    spec={"id":"test","transform":"level","frequency":"daily","sign":1}
    assert M.component(spec,rows,today)["score"]==100
    assert M.component(dict(spec,sign=-1),rows,today)["score"]==0
    assert M.component(spec,rows,today+dt.timedelta(days=30))["status"]=="stale"
    assert M.component(spec,rows[:2],today)["score"] is None
    assert M.transform([("2025-01-01",100),("2026-01-01",104)],"yoy",today)[0][1]>3.99
    plan=json.loads(M.PLAN.read_text())
    assert len(M.calculate(plan,{},today)["indices"])==6
    assert all(i["score"] is None for i in M.calculate(plan,{},today)["indices"])

def test_macro_plan_v2():
    """Plan v2: no series in two indices; a monthly reading's age counts from the end of its month; per-series window."""
    plan=json.loads(M.PLAN.read_text())
    ids=[c["id"] for i in plan["indices"] for c in i["components"]]
    assert plan["version"]==2 and len(ids)==len(set(ids))
    rows=[(f"{2011+i//12:04d}-{i%12+1:02d}-01",100*(1.002**i)) for i in range(15*12+9)]   # to 2026-09-01
    spec={"id":"CPI","transform":"yoy","frequency":"monthly","sign":1}
    today=dt.date(2026,11,24)
    old=M.component(spec,rows,today,windows={"monthly":(60,75)},age_from="observation")
    new=M.component(spec,rows,today,windows={"monthly":(60,75)},age_from="period_end")
    assert old["status"]=="stale" and old["age_days"]==84          # September counted from 1 Sep
    assert new["status"]=="available" and new["age_days"]==55      # ...and from 30 Sep
    d=[((today-dt.timedelta(days=800-i)).isoformat(),float(i)) for i in range(801)]
    sp={"id":"HY","transform":"level","frequency":"daily","sign":1}
    assert M.component(sp,d,today,windows={"daily":(1260,10)})["status"]=="insufficient_history"
    assert M.component(dict(sp,window=750),d,today,windows={"daily":(1260,10)})["score"]==100

def test_discovery():
    plan=json.loads(V.PLAN.read_text())
    rnd=random.Random(9)
    rows=[]
    d=dt.date(2019,1,1)
    close=100.
    while d<dt.date(2027,7,1):
        if d.weekday()<5:
            old=close
            close*=1+rnd.uniform(-.02,.02)
            rows.append((d.isoformat(),[old,max(old,close)+rnd.random(),min(old,close)-rnd.random(),close]))
        d+=dt.timedelta(days=1)
    data={m:rows for m in plan["markets"]}
    first=V.run(plan,data,dt.date(2026,11,24))
    assert len(first["batches"])==1
    assert len(first["batches"][0]["results"])==192
    assert all(not r["promoted"] for r in first["batches"][0]["results"])
    assert all(abs(r["family_adjusted_alpha"]-.05/192)<1e-12 for r in first["batches"][0]["results"] if "family_adjusted_alpha" in r)
    before=copy.deepcopy(first)
    assert V.run(plan,data,dt.date(2027,5,31),first)==before
    after=V.run(plan,data,dt.date(2027,6,2),first)
    assert len(after["batches"])==2 and after["batches"][0]==before["batches"][0]
    assert V.run(plan,{},dt.date(2026,11,24))["batches"]==[]

if __name__=="__main__":
    test_macro()
    test_macro_plan_v2()
    test_discovery()
    print("macro and expanded discovery tests passed")
