"""Atlas: annual World Development Indicators, with explicit year and source coverage."""
import datetime as dt
import hashlib
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/"research/atlas-plan-v1.json"
CACHE=ROOT/"engine/cache/atlas"
OUT=ROOT/"site/data/atlas/current.json"
API="https://api.worldbank.org/v2/country/"

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def load(path):
    return json.loads(path.read_text())

def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,allow_nan=False,separators=(",",":"))+"\n")
    os.replace(tmp,path)

def fetch_indicator(spec,plan,year,download):
    countries={c["id"] for c in plan["countries"]}
    url=API+";".join(sorted(countries))+"/indicator/"+spec["code"]+"?"
    page=1
    rows={}
    updated=None
    while True:
        params={"format":"json","source":2,"date":f"{plan['start_year']}:{year}","per_page":1000,"page":page}
        body=json.loads(download(url+urlencode(params),timeout=20,tries=2,max_bytes=4000000))
        if not isinstance(body,list) or len(body)!=2 or not isinstance(body[0],dict) or not isinstance(body[1],list):
            raise ValueError("Unexpected World Bank response")
        meta=body[0]
        pages=int(meta["pages"])
        if int(meta["page"])!=page or pages<1 or pages>20:
            raise ValueError("Invalid pagination")
        if page==1:
            updated=meta.get("lastupdated")
            total=int(meta["total"])
        elif int(meta["total"])!=total or meta.get("lastupdated")!=updated:
            raise ValueError("World Bank changed during pagination")
        for row in body[1]:
            country=row["countryiso3code"]
            date=int(row["date"])
            if country not in countries or row["indicator"]["id"]!=spec["code"] or not plan["start_year"]<=date<=year:
                raise ValueError("Unexpected economy, indicator or year")
            value=row["value"]
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                raise ValueError("Invalid observation")
            key=(country,date)
            if key in rows:
                raise ValueError("Duplicate observation")
            rows[key]=value
        if page>=pages:
            break
        page+=1
    if len(rows)!=total or not any(v is not None for v in rows.values()):
        raise ValueError("Incomplete or empty provider response")
    return {"provider_updated":updated,"rows":[[c,y,v] for (c,y),v in sorted(rows.items())]}

def age_hours(stamp,now):
    try:
        return (now-dt.datetime.fromisoformat(stamp)).total_seconds()/3600
    except (TypeError,ValueError):
        return math.inf

def refresh(spec,plan,now,download,cache=CACHE):
    path=cache/(spec["id"]+".json")
    old=load(path) if path.exists() else {"rows":[],"fetched":None,"attempted":None}
    config_hash=digest({"spec":spec,"countries":plan["countries"],"start_year":plan["start_year"]})
    if old.get("config_hash")!=config_hash:
        old={"rows":[],"fetched":None,"attempted":None}
    if 0<=age_hours(old.get("fetched"),now)<24*plan["refresh_days"]:
        return old
    if 0<=age_hours(old.get("attempted"),now)<plan["retry_hours"]:
        return old
    stamp=now.isoformat(timespec="seconds")
    try:
        new=fetch_indicator(spec,plan,now.year,download)
        old=dict(new,fetched=stamp,attempted=stamp,status="available",config_hash=config_hash)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print("atlas source",spec["id"],"unavailable:",str(exc)[:200])
        old=dict(old,attempted=stamp,status="cached_after_error" if old["rows"] else "unavailable",config_hash=config_hash)
    write(path,old)
    return old

def build(plan,cache,now):
    years=list(range(plan["start_year"],now.year+1))
    countries=[]
    sources=[]
    lookups={}
    for spec in plan["indicators"]:
        doc=cache.get(spec["id"],{})
        age=age_hours(doc.get("fetched"),now)
        state=("unavailable" if not doc.get("rows") else "stale_cache" if age<0 or age>24*plan["stale_cache_days"] else
               "cached_after_error" if doc.get("status")=="cached_after_error" else "available")
        sources.append(dict(spec,status=state,fetched=doc.get("fetched"),attempted=doc.get("attempted"),
                            provider_updated=doc.get("provider_updated"),source="https://data.worldbank.org/indicator/"+spec["code"]))
        lookups[spec["id"]]={(c,y):v for c,y,v in doc.get("rows",[]) if y in years}
    for c in plan["countries"]:
        metrics={}
        for source in sources:
            key=source["id"]
            values=[[y,lookups[key].get((c["id"],y))] for y in years]
            observed=[r for r in values if r[1] is not None]
            latest=observed[-1] if observed else None
            metrics[key]={"history":values,"latest":latest,"status":source["status"] if latest else "missing"}
        countries.append(dict(c,metrics=metrics))
    coverage={s["id"]:{str(y):sum(c["metrics"][s["id"]]["history"][y-years[0]][1] is not None for c in countries)
                        for y in years} for s in sources}
    return {"version":1,"plan_hash":digest(plan),"asof":now.isoformat(timespec="seconds"),"years":years,
            "countries":countries,"indicators":sources,"coverage":coverage,"policy":plan["policy"]}

def check(doc,plan):
    if doc["version"]!=1 or doc["plan_hash"]!=digest(plan):
        raise ValueError("Atlas plan mismatch")
    now=dt.datetime.fromisoformat(doc["asof"])
    years=list(range(plan["start_year"],now.year+1))
    if now.tzinfo is None or doc["years"]!=years:
        raise ValueError("Invalid Atlas years")
    ids=[c["id"] for c in plan["countries"]]
    keys=[i["id"] for i in plan["indicators"]]
    if [c["id"] for c in doc["countries"]]!=ids or [i["id"] for i in doc["indicators"]]!=keys:
        raise ValueError("Atlas coverage mismatch")
    for c in doc["countries"]:
        if set(c["metrics"])!=set(keys):
            raise ValueError("Missing metric")
        for key,m in c["metrics"].items():
            if [v[0] for v in m["history"]]!=years:
                raise ValueError("Invalid history dates")
            for y,v in m["history"]:
                if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):
                    raise ValueError("Invalid history value")
            known=[r for r in m["history"] if r[1] is not None]
            if m["latest"]!=(known[-1] if known else None):
                raise ValueError("Latest observation mismatch")
    for k in keys:
        for j,y in enumerate(years):
            if doc["coverage"][k][str(y)]!=sum(c["metrics"][k]["history"][j][1] is not None for c in doc["countries"]):
                raise ValueError("Coverage count mismatch")
    return []

def main():
    from publicdata import download
    plan=load(PLAN)
    now=dt.datetime.now(dt.timezone.utc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        cache=dict(zip([i["id"] for i in plan["indicators"]],
                       pool.map(lambda i:refresh(i,plan,now,download),plan["indicators"])))
    out=build(plan,cache,now)
    check(out,plan)
    write(OUT,out)
    print("atlas:",len(out["countries"]),"economies;",len(out["indicators"]),"indicators;",
          sum(m["latest"] is not None for c in out["countries"] for m in c["metrics"].values()),"series with observations")

if __name__=="__main__":
    main()
