"""Cross-market descriptive relationships, no LLM or predictive model promotion."""
import datetime as dt
import itertools
import json
import math
import os
import statistics as st
from pathlib import Path
import discovery as D

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/"research/relationships-plan-v1.json"
OUT=ROOT/"site/data/relationships/current.json"

def changes(rows,mode,today,max_gap):
    clean={}
    for d,v in rows:
        if d<=today.isoformat() and type(v) in (int,float) and math.isfinite(v):
            clean[d]=v
    ordered=sorted(clean.items())
    result={}
    for (a,x),(b,y) in zip(ordered,ordered[1:]):
        if not 1 <= (dt.date.fromisoformat(b)-dt.date.fromisoformat(a)).days <= max_gap:
            continue
        if mode=="log_return_pct":
            if x<=0 or y<=0:
                continue
            value=100*math.log(y/x)
        elif mode=="basis_point_change":
            value=100*(y-x)
        elif mode=="point_change":
            value=y-x
        else:
            raise ValueError("Unknown transformation")
        if math.isfinite(value):
            result[(a,b)]=value
    return result

def aligned(x,y):
    return [(a,b,x[(a,b)],y[(a,b)]) for a,b in sorted(x.keys()&y.keys())]

def corr(rows):
    if len(rows)<2:
        return None
    x=[r[2] for r in rows]
    y=[r[3] for r in rows]
    mx,my=st.mean(x),st.mean(y)
    vx=sum((v-mx)**2 for v in x)
    vy=sum((v-my)**2 for v in y)
    if vx<=0 or vy<=0:
        return None
    return max(-1.,min(1.,sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(vx*vy)))

def residual(rows,window):
    if len(rows)<window+1:
        return None
    prior=rows[-window-1:-1]
    x=[r[2] for r in prior]
    y=[r[3] for r in prior]
    mx,my=st.mean(x),st.mean(y)
    vx=sum((v-mx)**2 for v in x)
    if vx<=1e-20:
        return None
    beta=sum((a-mx)*(b-my) for a,b in zip(x,y))/vx
    intercept=my-beta*mx
    errors=[b-intercept-beta*a for a,b in zip(x,y)]
    sigma=math.sqrt(sum(e*e for e in errors)/(window-2))
    if sigma<=1e-10:
        return None
    a,b=rows[-1][2:]
    expected=intercept+beta*a
    z=(b-expected)/sigma
    if not all(math.isfinite(v) for v in (beta,expected,z)):
        return None
    return {"z":round(z,4),"observed":round(b,6),"fitted":round(expected,6),
            "beta":round(beta,6),"training_n":window,"training_end":prior[-1][1]}

def run(plan,datasets,today):
    specs={s["id"]:s for s in plan["series"]}
    if len(specs)!=len(plan["series"]):
        raise ValueError("Duplicate series")
    transformed={k:changes(datasets.get(k,[]),s["transform"],today,plan["max_gap_days"]) for k,s in specs.items()}
    pairs=[]
    for a,b in itertools.combinations(specs,2):
        rows=aligned(transformed[a],transformed[b])
        latest=rows[-1][1] if rows else None
        age=(today-dt.date.fromisoformat(latest)).days if latest else None
        status="stale" if age is not None and age>plan["max_age_days"] else "insufficient_data"
        metrics={str(n):None for n in plan["windows"]}
        prior60=None
        shift=None
        div=None
        if age is not None and age<=plan["max_age_days"]:
            for n in plan["windows"]:
                if len(rows)>=n:
                    value=corr(rows[-n:])
                    metrics[str(n)]=round(value,4) if value is not None else None
            if metrics["60"] is not None:
                status="available"
            if len(rows)>=120:
                value=corr(rows[-120:-60])
                if value is not None and metrics["60"] is not None:
                    prior60=round(value,4)
                    shift=round(metrics["60"]-prior60,4)
            div=residual(rows,plan["divergence_window"])
        flags=[]
        if shift is not None and abs(shift)>=plan["correlation_shift_threshold"]:
            flags.append("correlation_shift")
        if div is not None and abs(div["z"])>=plan["divergence_threshold"]:
            flags.append("unusual_residual")
        pairs.append({"a":a,"b":b,"status":status,"latest":latest,"age_days":age,"paired_n":len(rows),
                      "correlations":metrics,"prior60":prior60,"shift60":shift,"divergence":div,"flags":flags})
    return {"version":1,"plan_hash":D.digest(plan),"asof":today.isoformat(),"series":plan["series"],
            "policy":plan["policy"],"pairs":pairs}

def check(doc,plan):
    bad=[]
    if doc["version"]!=1 or doc["plan_hash"]!=D.digest(plan) or doc["series"]!=plan["series"]:
        bad.append("registered relationship plan mismatch")
    ids=[s["id"] for s in plan["series"]]
    expected=set(itertools.combinations(ids,2))
    actual=[(p["a"],p["b"]) for p in doc["pairs"]]
    if len(actual)!=len(expected) or set(actual)!=expected:
        bad.append("missing or duplicate pairs")
    for p in doc["pairs"]:
        if p["status"] not in ("available","stale","insufficient_data"):
            bad.append("invalid pair status")
        if set(p["correlations"])!={str(n) for n in plan["windows"]}:
            bad.append("invalid windows")
        if any(v is not None and (type(v) not in (int,float) or not -1<=v<=1) for v in p["correlations"].values()):
            bad.append("correlation out of bounds")
        if p["status"]=="stale" and (any(v is not None for v in p["correlations"].values()) or p["divergence"] is not None or p["flags"]):
            bad.append("stale metrics not suppressed")
        if p["divergence"] and p["divergence"]["training_end"]>=p["latest"]:
            bad.append("divergence uses current or future observation")
    return bad

def main():
    import bias
    import macro
    import series_store
    plan=json.loads(PLAN.read_text())
    now=dt.datetime.now(dt.timezone.utc)
    ny=now.astimezone(bias.NY)
    datasets={}
    for s in plan["series"]:
        key=s["id"]
        if s["kind"]=="futures":
            datasets[key]=[(d,v[3]) for d,v in bias.clean(key,bias.finished(bias.load_cache(key)["days"],ny))]
        elif s["kind"]=="macro":
            path=macro.CACHE/(key+".json")
            datasets[key]=[(d,v) for d,v,*_ in json.loads(path.read_text())["rows"]] if path.exists() else []
        elif s["kind"]=="series":
            datasets[key]=[(d,v) for d,v,*_ in series_store.load(key)["rows"]]
        else:
            raise ValueError("Unknown source kind")
    out=run(plan,datasets,ny.date())
    errors=check(out,plan)
    if errors:
        raise ValueError("; ".join(errors))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("relationships:",sum(p["status"]=="available" for p in out["pairs"]),"available of",len(out["pairs"]))

if __name__=="__main__":
    main()
