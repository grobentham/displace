import datetime as dt
import math
import random
import validation as V
import discovery_v2 as D

def main():
    plan=V.load(V.PLAN)
    registered=V.load(V.DISCOVERY)
    rnd=random.Random(2026)
    rows=[]
    d=dt.date(2019,1,1)
    price=100.
    while d<dt.date(2026,11,5):
        if d.weekday()<5:
            start=price
            price*=1+rnd.uniform(-.02,.02)
            rows.append((d.isoformat(),[start,max(start,price)+.2,min(start,price)-.2,price]))
        d+=dt.timedelta(days=1)
    original=D.observations(rows,"next_positive_close")
    independent=V.sample(rows)
    assert [(d,f,y["next_positive_close"]) for d,f,y,_ in independent]==original
    assert V.sample(rows[:100])==independent[:len(V.sample(rows[:100]))]
    # Change the next candle; the predictor must not change.
    altered=list(rows[:100])
    d,v=altered[-1]
    altered[-1]=(d,[v[0],v[1]*1.1,v[2]*.9,v[3]*1.05])
    assert V.sample(altered)[-1][1]==V.sample(rows[:100])[-1][1]
    data={m:rows for m in registered["markets"]}
    frozen=D.run(registered,data,dt.date(2026,11,24))
    out=V.evaluate(plan,registered,frozen,data,dt.datetime(2026,11,24,tzinfo=dt.timezone.utc))
    assert len(frozen["batches"])==1, "fixture must include a completed candle on or after the exclusive end"
    assert len(out["batches"][0]["results"])==192
    assert all(r["reproduction"]=="reproduced" for r in out["batches"][0]["results"])
    assert not V.check(out,plan,registered)
    empty=V.evaluate(plan,registered,frozen,{},dt.datetime(2026,11,24,tzinfo=dt.timezone.utc))
    assert all(r["reproduction"]=="different_input_vintage" for r in empty["batches"][0]["results"])
    null=V.null_control(plan)
    assert null["replications"]==100
    assert abs(null["mean_marginal_effect"])<.03
    assert null["mean_weekly_effect"]<-.10
    assert null==V.null_control(plan)
    print("validation tests passed")
if __name__=="__main__":
    main()
