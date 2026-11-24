"""Descriptive current-vintage US macro indices; never a recession probability."""
import datetime as dt
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/"research/macro-plan-v2.json"   # v1 kept for the record
OUT=ROOT/"site/data/macro/current.json"
CACHE=ROOT/"engine/cache/macro"
FREQ={"daily":(252,10),"weekly":(156,21),"monthly":(60,75)}

def percentile(x,history):
    return 100*(sum(y<x for y in history)+.5*sum(y==x for y in history))/len(history)

def transform(rows,mode,today):
    clean={d:float(v) for d,v,*_ in rows if d<=today.isoformat() and type(v) in (int,float) and math.isfinite(v)}
    if mode=="level":
        return sorted(clean.items())
    if mode!="yoy":
        raise ValueError("Unknown transform")
    months={d[:7]:(d,v) for d,v in sorted(clean.items())}
    out=[]
    for m,(d,v) in sorted(months.items()):
        prior=months.get(f"{int(m[:4])-1:04d}"+m[4:])
        if prior and prior[1]>0 and v>0:
            out.append((d,100*(v/prior[1]-1)))
    return out

def period_end(d,frequency):
    """Last day of the period a reading covers: FRED dates a monthly reading on the 1st of its month."""
    d=dt.date.fromisoformat(d)
    if frequency=="monthly":
        return dt.date(d.year+(d.month==12),d.month%12+1,1)-dt.timedelta(days=1)
    return d

def component(spec,rows,today,windows=None,age_from="observation"):
    n,max_age=(windows or FREQ)[spec["frequency"]]
    n=spec.get("window",n)            # a shorter window where the source's history is shorter (plan v2: credit spreads)
    obs=transform(rows,spec["transform"],today)
    result=dict(spec,source="https://fred.stlouisfed.org/series/"+spec["id"],score=None,status="insufficient_history")
    if not obs:
        return result
    d,value=obs[-1]
    age=(today-(period_end(d,spec["frequency"]) if age_from=="period_end" else dt.date.fromisoformat(d))).days
    result.update(observation_date=d,value=round(value,4),age_days=age,history_n=min(n,len(obs)-1))
    if age>max_age:
        result["status"]="stale"
    elif len(obs)>=n+1:
        p=percentile(value,[v for _,v in obs[-n-1:-1]])
        result.update(score=round(p if spec["sign"]==1 else 100-p,2),status="available")
    return result

def calculate(plan,datasets,today):
    indices=[]
    for spec in plan["indices"]:
        parts=[component(c,datasets.get(c["id"],[]),today,plan.get("windows"),plan.get("age_from","observation"))
               for c in spec["components"]]
        scores=[p["score"] for p in parts if p["score"] is not None]
        score=round(sum(scores)/len(scores),2) if len(scores)==len(parts) and scores else None
        indices.append({"id":spec["id"],"name":spec["name"],"score":score,"status":"available" if score is not None else "unavailable","components":parts})
    return {"version":plan["version"],"asof":today.isoformat(),"policy":plan["policy"],"indices":indices}

def fetch(sid,now):
    import publicdata
    CACHE.mkdir(parents=True,exist_ok=True)
    path=CACHE/(sid+".json")
    prior=json.loads(path.read_text()) if path.exists() else {"rows":[]}
    try:
        stamp=dt.datetime.fromisoformat(prior.get("checked","2000-01-01T00:00:00+00:00"))
        if now-stamp<dt.timedelta(hours=12):
            return prior["rows"]
    except (TypeError,ValueError):
        pass
    try:
        body=publicdata.download(publicdata.FRED+"/graph/fredgraph.csv?"+urlencode({"id":sid,"cosd":"2010-01-01"}))
        rows=publicdata.read_csv(body,sid,"2010-01-01")
        if len(rows)<20:
            raise ValueError("Source too short")
        prior={"rows":rows,"fetched":now.isoformat()}
    except (OSError,ValueError) as e:
        print("macro source",sid,"unavailable:",str(e))
    prior["checked"]=now.isoformat()
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(prior,allow_nan=False,separators=(",",":")))
    os.replace(tmp,path)
    return prior["rows"]

def main():
    now=dt.datetime.now(dt.timezone.utc)
    plan=json.loads(PLAN.read_text())
    ids=sorted({c["id"] for i in plan["indices"] for c in i["components"]})
    with ThreadPoolExecutor(max_workers=4) as pool:
        datasets=dict(zip(ids,pool.map(lambda sid:fetch(sid,now),ids)))
    out=calculate(plan,datasets,now.date())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("macro:",sum(i["score"] is not None for i in out["indices"]),"available indices")

if __name__=="__main__":
    main()
