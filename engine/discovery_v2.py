"""Version 2 discovery; v1 outputs remain untouched."""
import datetime as dt
import json
import os
import statistics as st
from pathlib import Path
import discovery as D

PLAN = D.ROOT / "research/discovery-plan-v2.json"
OUT = D.ROOT / "site/data/research/discovery-v2.json"

def observations(rows, outcome):
    out = []
    for i in range(20,len(rows)-1):
        d,v = rows[i]
        nxt,f = rows[i+1]
        prev = rows[i-1][1]
        if any((dt.date.fromisoformat(rows[j+1][0])-dt.date.fromisoformat(rows[j][0])).days not in range(1,5) for j in range(i-20,i+1)):
            continue
        width=(v[1]-v[2])/v[3]
        med=st.median((x[1]-x[2])/x[3] for _,x in rows[i-20:i])
        loc=(v[3]-v[2])/(v[1]-v[2])
        flags={"previous_up":v[3]>prev[3],"previous_down":v[3]<prev[3],
               "wide_range":width>med,"narrow_range":width<med,
               "momentum_5_up":v[3]>rows[i-5][1][3],"momentum_5_down":v[3]<rows[i-5][1][3],
               "momentum_20_up":v[3]>rows[i-20][1][3],"momentum_20_down":v[3]<rows[i-20][1][3],
               "close_near_high":loc>=.8,"close_near_low":loc<=.2,
               "inside_day":v[1]<prev[1] and v[2]>prev[2],
               "outside_day":v[1]>prev[1] and v[2]<prev[2]}
        if outcome=="next_positive_close":
            y=int(f[3]>v[3])
        elif outcome=="next_range_expansion":
            y=int((f[1]-f[2])/f[3]>width)
        else:
            raise ValueError("Unknown outcome")
        out.append((nxt,flags,y))
    return out

def run(plan,datasets,today,previous=None):
    h=D.digest(plan)
    out=previous if previous is not None else {"version":2,"plan_hash":h,"batches":[]}
    if out["plan_hash"]!=h:
        raise ValueError("Registered plan changed; use a new version")
    if dt.date.fromisoformat(plan["prospective_start"])<=dt.date.fromisoformat(plan["registered_at"]):
        raise ValueError("Prospective start must follow registration")
    for key in ("markets","conditions","outcomes"):
        if not plan[key] or len(set(plan[key]))!=len(plan[key]):
            raise ValueError("Empty or duplicate family")
    done={(b["kind"],b["start"],b["end"]) for b in out["batches"]}
    adjusted=dict(plan,alpha=plan["alpha"]/len(plan["outcomes"]))
    for kind,start,end in D.periods(plan,today):
        if (kind,start,end) in done or any(not datasets.get(m) or datasets[m][-1][0]<end for m in plan["markets"]):
            continue
        results,hashes=[],{}
        for market in plan["markets"]:
            rows=[(d,v) for d,v in datasets[market] if d<end]
            hashes[market]=D.digest(rows)
            for outcome in plan["outcomes"]:
                obs=observations(rows,outcome)
                for condition in plan["conditions"]:
                    r=D.evaluate(obs,condition,start,end,adjusted)
                    r.update(market=market,outcome=outcome)
                    if kind=="historical" and r["status"]=="candidate_for_review":
                        r["status"]="exploratory_candidate"
                    results.append(r)
        out["batches"].append({"kind":kind,"start":start,"end":end,"computed_on":today.isoformat(),
                               "dataset_hashes":hashes,"results":results,"policy":plan["policy"]})
    return out

def main():
    import bias
    now=dt.datetime.now(dt.timezone.utc).astimezone(bias.NY)
    plan=json.loads(PLAN.read_text())
    datasets={m:bias.clean(m,bias.finished(bias.load_cache(m)["days"],now)) for m in plan["markets"]}
    previous=json.loads(OUT.read_text()) if OUT.exists() else None
    out=run(plan,datasets,now.date(),previous)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("discovery v2:",len(out["batches"]),"frozen batches")

if __name__=="__main__":
    main()
