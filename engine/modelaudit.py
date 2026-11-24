"""Separate price-only model audit; never promotes models."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/"research/model-audit-plan-v1.json"
OUT=ROOT/"site/data/validation/models.json"

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def valid(v):
    return len(v)==4 and all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in v) and v[2]<=min(v[0],v[3])<=max(v[0],v[3])<=v[1] and v[1]>v[2]

def samples(rows,plan):
    out=[]
    for i in range(21,len(rows)-1):
        block=rows[i-21:i+2]
        if not all(valid(v) for _,v in block):
            continue
        dates=[dt.date.fromisoformat(d) for d,_ in block]
        if any(not 1<=(b-a).days<=plan["max_gap_days"] for a,b in zip(dates,dates[1:])):
            continue
        prev=block[:-1]
        _,v=prev[-1]
        target,f=block[-1]
        rg=[math.log(x[1]/x[2]) for _,x in prev]
        features=[math.log(sum(rg[-k:])/k) for k in (1,5,22)]
        base=math.log(sum(rg[-20:])/20)
        loc=(v[3]-v[2])/(v[1]-v[2])
        out.append({"date":target,"year":int(target[:4]),"x":features,"base":base,"y":math.log(math.log(f[1]/f[2])),
                    "points":f[1]-f[2],"anchor":v[3],"up":int(f[3]>v[3]),
                    "high":int(f[1]>v[1]),"low":int(f[2]<v[2]),"bin":min(4,int(loc*5))})
    return out

def interval_score(y,lo,hi):
    return hi-lo+10*max(lo-y,0)+10*max(y-hi,0)

def skill(a,b):
    return float(1-np.mean(a)/np.mean(b)) if len(b) and np.mean(b)>0 else None

def replay(rows,plan):
    s=samples(rows,plan)
    years=sorted({r["year"] for r in s})
    errors={k:[] for k in ("log_model","log_base","point_model","point_base","coverage","coverage_base",
                            "interval_model","interval_base","direction","direction_base","high","high_base","low","low_base")}
    first=None
    for year in years:
        if year<plan["first_test_year"]:
            continue
        train=[r for r in s if r["year"]<year]
        test=[r for r in s if r["year"]==year]
        if len(train)<plan["min_train"] or not test:
            continue
        first=first or year
        A=np.array([[1]+r["x"] for r in train])
        y=np.array([r["y"] for r in train])
        beta=np.linalg.lstsq(A,y,rcond=None)[0]
        quant=np.quantile(y-A@beta,[.1,.5,.9])
        naive=np.quantile(y-np.array([r["base"] for r in train]),[.1,.5,.9])
        past=list(train)
        for r in test:
            fit=float(np.array([1]+r["x"])@beta)
            # Match the original log-space point metric's unadjusted fit, and
            # compare a separately named median point approximation.
            errors["log_model"].append((r["y"]-fit)**2)
            errors["log_base"].append((r["y"]-r["base"]-naive[1])**2)
            forecast=lambda x:r["anchor"]*math.expm1(math.exp(x))
            errors["point_model"].append(abs(r["points"]-forecast(fit+quant[1])))
            errors["point_base"].append(abs(r["points"]-forecast(r["base"]+naive[1])))
            for suffix,center,q in (("",fit,quant),("_base",r["base"],naive)):
                lo,hi=center+q[0],center+q[2]
                errors["coverage"+suffix].append(lo<=r["y"]<=hi)
                errors["interval"+("_model" if not suffix else "_base")].append(interval_score(r["y"],lo,hi))
            base_up=sum(t["up"] for t in train)/len(train)
            recent=past[-252:]
            p=sum(t["up"] for t in recent)/len(recent)
            errors["direction"].append((p-r["up"])**2)
            errors["direction_base"].append((base_up-r["up"])**2)
            for side in ("high","low"):
                baseline=sum(t[side] for t in train)/len(train)
                group=[t for t in train if t["bin"]==r["bin"]]
                probability=(sum(t[side] for t in group)+20*baseline)/(len(group)+20)
                errors[side].append((probability-r[side])**2)
                errors[side+"_base"].append((baseline-r[side])**2)
            past.append(r)
    n=len(errors["log_model"])
    if not n:
        return {"status":"insufficient_data","n":0,"sample_n":len(s)}
    mean=lambda k:float(np.mean(errors[k]))
    return {"status":"historical_only","n":n,"sample_n":len(s),"since":first,
            "log_mse":mean("log_model"),"log_mse_baseline":mean("log_base"),"log_mse_skill":skill(errors["log_model"],errors["log_base"]),
            "point_mae":mean("point_model"),"point_mae_baseline":mean("point_base"),"point_mae_skill":skill(errors["point_model"],errors["point_base"]),
            "coverage":mean("coverage"),"coverage_baseline":mean("coverage_base"),
            "interval_score":mean("interval_model"),"interval_score_baseline":mean("interval_base"),
            "direction_rolling_skill":skill(errors["direction"],errors["direction_base"]),
            "high_bin_skill":skill(errors["high"],errors["high_base"]),"low_bin_skill":skill(errors["low"],errors["low_base"])}

def run(plan,datasets,bias_doc,event_doc,now):
    markets={}
    for key in plan["markets"]:
        rows=datasets.get(key,[])
        r=replay(rows,plan)
        original=bias_doc.get("markets",{}).get(key,{})
        r.update(dataset_hash=digest(rows),raw_n=len(rows),invalid_ohlc=sum(not valid(v) for _,v in rows),
                 original_range_stats=original.get("vol",{}).get("stats"),original_tier=original.get("tier"))
        markets[key]=r
    events=[]
    for group,assets in event_doc.get("groups",{}).items():
        for asset,s in assets.items():
            events.append({"group":group,"asset":asset,"historical_candidate":bool(s.get("historical_candidate")),
                           "proven":bool(s.get("proven")),"historical_metrics":s["bt"]})
    return {"version":1,"asof":now.isoformat(),"plan_hash":digest(plan),"markets":markets,"events":events,
            "event_qualification":event_doc.get("qualification"),"policy":plan["policy"],
            "limitations":["Cached data can be revised or patched; exact exchange calendars, settlement and contract rolls remain unresolved.",
              "The price-only replay does not reproduce the original full model with retrospective economic calendar and cross-series inputs.",
              "The point conversion is a prior-close-anchored approximation rather than an exact high-minus-low prediction.",
              "Event statistics use a seven-calendar-day embargo and a prior base-rate benchmark but remain current-vintage and may contain overlapping outcomes.",
              "Original reported model performance and the independent benchmark use different samples and model specifications."]}

def check(doc,plan):
    if doc["plan_hash"]!=digest(plan) or set(doc["markets"])!=set(plan["markets"]):
        raise ValueError("Model audit registry mismatch")
    if doc["event_qualification"]!="suspended_pending_validation" or any(r["proven"] for r in doc["events"]):
        raise ValueError("Unapproved event qualification")
    for r in doc["markets"].values():
        if r["status"] not in ("historical_only","insufficient_data") or r["n"]>r["sample_n"]:
            raise ValueError("Invalid model replay")
        if r["status"]=="historical_only" and not all(0<=r[k]<=1 for k in ("coverage","coverage_baseline")):
            raise ValueError("Invalid interval coverage")
    return []

def main():
    import bias
    plan=json.loads(PLAN.read_text())
    now=dt.datetime.now(dt.timezone.utc)
    datasets={m:bias.clean(m,bias.finished(bias.load_cache(m)["days"],now.astimezone(bias.NY))) for m in plan["markets"]}
    data=ROOT/"site/data"
    doc=run(plan,datasets,json.loads((data/"bias/current.json").read_text()),json.loads((data/"direction/current.json").read_text()),now)
    check(doc,plan)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("model audit:",sum(r["n"] for r in doc["markets"].values()),"historical test observations; no promotion")

if __name__=="__main__":
    main()
