import datetime as dt
import json
import math
import random
import relationships as R

def main():
    today=dt.date(2026,11,24)
    a=R.changes([("2026-11-20",100),("2026-11-23",110)],"log_return_pct",today,4)
    assert abs(a[("2026-11-20","2026-11-23")]-100*math.log(1.1))<1e-9
    b=R.changes([("2026-11-19",100),("2026-11-23",110)],"log_return_pct",today,4)
    assert not R.aligned(a,b) # same end date, different start
    assert not R.changes([("2026-11-10",100),("2026-11-23",110)],"log_return_pct",today,4)
    assert not R.changes([("2026-11-23",100),("2026-11-25",110)],"log_return_pct",today,4)
    assert R.changes([("2026-11-23",3),("2026-11-24",3.25)],"basis_point_change",today,4)[("2026-11-23","2026-11-24")]==25
    assert R.corr([("a","b",1,3),("b","c",2,6),("c","d",3,9)])==1
    assert R.corr([("a","b",1,3),("b","c",1,6)]) is None
    rnd=random.Random(7)
    rows=[("2026-01-01",str(i).zfill(3),x,2*x+rnd.uniform(-.1,.1)) for i,x in enumerate([rnd.uniform(-1,1) for _ in range(60)])]
    div=R.residual(rows+[("060","061",.5,10)],60)
    assert div["z"]>10 and div["training_end"]=="059"
    plan=json.loads(R.PLAN.read_text())
    dates=[(today-dt.timedelta(days=300-i)).isoformat() for i in range(301)]
    prices=[(d,100+math.sin(i/3)+i/5) for i,d in enumerate(dates)]
    data={s["id"]:prices for s in plan["series"]}
    out=R.run(plan,data,today)
    assert len(out["pairs"])==66 and not R.check(out,plan)
    assert all(p["status"]=="available" for p in out["pairs"])
    stale=R.run(plan,data,today+dt.timedelta(days=20))
    assert all(p["status"]=="stale" and not p["flags"] for p in stale["pairs"])
    assert not R.check(stale,plan)
    missing=R.run(plan,{},today)
    assert all(p["status"]=="insufficient_data" for p in missing["pairs"])
    assert not R.check(missing,plan)
    print("relationship tests passed")

if __name__=="__main__":
    main()
