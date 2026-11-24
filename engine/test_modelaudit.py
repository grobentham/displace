import datetime as dt
import json
import random
import modelaudit as M

def main():
    plan=json.loads(M.PLAN.read_text())
    rnd=random.Random(19)
    rows=[]
    d=dt.date(2015,1,1)
    p=100.
    while d<dt.date(2020,1,1):
        if d.weekday()<5:
            old=p
            p*=1+rnd.uniform(-.02,.02)
            rows.append((d.isoformat(),[old,max(old,p)+.5,min(old,p)-.5,p]))
        d+=dt.timedelta(days=1)
    s=M.samples(rows,plan)
    assert len(s)>1000 and M.samples(rows[:100],plan)==s[:len(M.samples(rows[:100],plan))]
    changed=list(rows[:100])
    d,v=changed[-1]
    changed[-1]=(d,[v[0],v[1]+1,v[2],v[3]])
    assert M.samples(changed,plan)[-1]["x"]==M.samples(rows[:100],plan)[-1]["x"]
    assert M.replay(rows,plan)["n"]>100
    assert M.replay([],plan)["status"]=="insufficient_data"
    doc=M.run(plan,{"nq":rows},{},{"qualification":"suspended_pending_validation"},dt.datetime.now(dt.timezone.utc))
    assert not M.check(doc,plan)
    assert not M.valid([100,95,90,100])
    assert M.interval_score(1,0,2)==2 and M.interval_score(3,0,2)==12
    print("price-only replay tests passed")
if __name__=="__main__":
    main()
