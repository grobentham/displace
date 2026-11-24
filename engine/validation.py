"""Second implementation of discovery V2 diagnostics; not an independent external audit."""
import datetime as dt
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
from statistics import NormalDist

ROOT=Path(__file__).resolve().parent.parent
PLAN=ROOT/"research/validation-plan-v1.json"
DISCOVERY=ROOT/"research/discovery-plan-v2.json"
DATA=ROOT/"site/data"
OUT=DATA/"validation/current.json"

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def load(p):
    return json.loads(p.read_text())

def sample(rows):
    """Construct predictors without reading the outcome candle; outcome is attached afterwards."""
    out=[]
    for i in range(20,len(rows)-1):
        history=rows[i-20:i+1]
        nxt,future=rows[i+1]
        dates=[dt.date.fromisoformat(d) for d,_ in history]+[dt.date.fromisoformat(nxt)]
        if any(not 1<=(b-a).days<=4 for a,b in zip(dates,dates[1:])):
            continue
        vals=[v for _,v in history]
        v,prev=vals[-1],vals[-2]
        widths=sorted((x[1]-x[2])/x[3] for x in vals[:-1])
        median=(widths[9]+widths[10])/2
        width=(v[1]-v[2])/v[3]
        loc=(v[3]-v[2])/(v[1]-v[2])
        flags=dict(zip(("previous_up","previous_down","wide_range","narrow_range","momentum_5_up","momentum_5_down",
                        "momentum_20_up","momentum_20_down","close_near_high","close_near_low","inside_day","outside_day"),
                       (v[3]>prev[3],v[3]<prev[3],width>median,width<median,v[3]>vals[-6][3],v[3]<vals[-6][3],
                        v[3]>vals[0][3],v[3]<vals[0][3],loc>=.8,loc<=.2,
                        v[1]<prev[1] and v[2]>prev[2],v[1]>prev[1] and v[2]<prev[2])))
        out.append((nxt,flags,{"next_positive_close":int(future[3]>v[3]),
                              "next_range_expansion":int((future[1]-future[2])/future[3]>width)},
                    10000*(future[3]/future[0]-1)))
    return out

def marginal(rows,condition,outcome,plan,alpha):
    data=[(d,int(f[condition]),y[outcome]) for d,f,y,_ in rows]
    n1=sum(f for _,f,_ in data)
    n0=len(data)-n1
    out={"n":len(data),"condition_n":n1,"comparison_n":n0,"effect":None,"interval":None,"blocks":0,"status":"insufficient_data"}
    if min(n1,n0)<plan["min_group"]:
        return out
    p=sum(f*y for _,f,y in data)/n1
    q=sum((1-f)*y for _,f,y in data)/n0
    out.update(condition_rate=p,comparison_rate=q,effect=p-q)
    groups={}
    for d,f,y in data:
        key=dt.date.fromisoformat(d).toordinal()//plan["block_days"]
        groups[key]=groups.get(key,0)+(y-p)/n1 if f else groups.get(key,0)-(y-q)/n0
    k=len(groups)
    out["blocks"]=k
    if k<plan["min_blocks"]:
        out["status"]="descriptive_only"
        return out
    se=math.sqrt(k/(k-1)*sum(x*x for x in groups.values()))
    z=NormalDist().inv_cdf(1-alpha/2)
    lo,hi=p-q-z*se,p-q+z*se
    out.update(interval=[max(-1,lo),min(1,hi)],standard_error=se,
               status="marginal_candidate" if se>0 and (lo>0 or hi<0) else "inconclusive")
    return out

def costs(rows,condition,split,costs):
    train=[ret for d,f,_,ret in rows if d<split and f[condition]]
    test=[ret for d,f,_,ret in rows if d>=split and f[condition]]
    baseline=[ret for d,_,_,ret in rows if d>=split]
    if min(len(train),len(test))<25 or not baseline:
        return None
    direction=1 if sum(train)>0 else -1
    return {"direction":"long" if direction==1 else "short","train_n":len(train),"test_n":len(test),
            "gross_bps":direction*sum(test)/len(test),
            "unconditional_gross_bps":direction*sum(baseline)/len(baseline),
            "net_bps":{str(c):direction*sum(test)/len(test)-c for c in costs},
            "classification":"exploratory open-to-close proxy, not a backtested executable strategy"}

def close(a,b):
    return isinstance(a,(float,int)) and isinstance(b,(float,int)) and math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9)

def compare(result,original,matched):
    if not matched:
        return "different_input_vintage"
    fields=("n","condition_n","comparison_n")
    if any(result[k]!=original[k] for k in fields):
        return "mismatch"
    for k in ("condition_rate","comparison_rate","effect"):
        if k in original and not close(result.get(k),original[k]):
            return "mismatch"
    return "reproduced"

def evaluate(plan,registered,archive,datasets,now):
    if archive["plan_hash"]!=digest(registered):
        raise ValueError("Discovery plan mismatch")
    combos=set(itertools.product(registered["markets"],registered["conditions"],registered["outcomes"]))
    alpha=plan["alpha"]/len(combos)
    batches=[]
    for b in archive["batches"]:
        originals={(r["market"],r["condition"],r["outcome"]):r for r in b["results"]}
        if len(originals)!=len(b["results"]) or set(originals)!=combos:
            raise ValueError("Missing or duplicate frozen experiments")
        results=[]
        for market in registered["markets"]:
            rows=[(d,v) for d,v in datasets.get(market,[]) if d<b["end"]]
            matched=bool(rows) and digest(rows)==b["dataset_hashes"].get(market)
            observations=[r for r in sample(rows) if b["start"]<=r[0]<b["end"]]
            for condition in registered["conditions"]:
                for outcome in registered["outcomes"]:
                    old=originals[market,condition,outcome]
                    r=marginal(observations,condition,outcome,plan,alpha)
                    reproduction=compare(r,old,matched)
                    weekly=old.get("weekly_effect")
                    original_effect=old.get("effect")
                    diagnostic=(abs(weekly-original_effect) if weekly is not None and original_effect is not None else None)
                    r.update(market=market,condition=condition,outcome=outcome,original_status=old["status"],
                             original_effect=original_effect,original_weekly_effect=weekly,estimand_gap=diagnostic,
                             reproduction=reproduction,matched_dataset=matched,promoted=False,
                             cost_proxy=costs(observations,condition,plan["split"],plan["cost_bps"]) if outcome=="next_positive_close" and b["kind"]=="historical" else None)
                    results.append(r)
        batches.append({"kind":b["kind"],"start":b["start"],"end":b["end"],"results":results})
    return {"version":1,"asof":now.isoformat(),"plan_hash":digest(plan),"discovery_plan_hash":digest(registered),
            "family_alpha":alpha,"batches":batches,"policy":plan["policy"],
            "unresolved":["No independent vendor feed or point-in-time snapshot archive.",
            "No exact futures exchange-session calendar, contract-roll or fill simulation.",
            "Historical splits are exploratory; no prospective evidence is promoted.",
            "Within-week conditioning can answer a different question from unconditional marginal association.",
            "Only Discovery V2 is recalculated; other engines need separate validation."]}

def check(doc,plan,registered):
    if doc["plan_hash"]!=digest(plan) or doc["discovery_plan_hash"]!=digest(registered):
        raise ValueError("Validation registry mismatch")
    keys=set(itertools.product(registered["markets"],registered["conditions"],registered["outcomes"]))
    for b in doc["batches"]:
        actual=[(r["market"],r["condition"],r["outcome"]) for r in b["results"]]
        if len(actual)!=len(keys) or set(actual)!=keys:
            raise ValueError("Incomplete validation family")
        for r in b["results"]:
            if r["promoted"] is not False or r["condition_n"]+r["comparison_n"]!=r["n"]:
                raise ValueError("Invalid validation accounting")
            if r["interval"] is not None and not -1<=r["interval"][0]<=r["interval"][1]<=1:
                raise ValueError("Invalid interval")
            if r["reproduction"]=="mismatch":
                # A negative result is published, never silently discarded or treated as model approval.
                if not r["matched_dataset"]:
                    raise ValueError("Mismatch without matched inputs")
    return []

def main():
    import bias
    plan=load(PLAN)
    registered=load(DISCOVERY)
    now=dt.datetime.now(dt.timezone.utc)
    datasets={m:bias.clean(m,bias.finished(bias.load_cache(m)["days"],now.astimezone(bias.NY))) for m in registered["markets"]}
    out=evaluate(plan,registered,load(DATA/"research/discovery-v2.json"),datasets,now)
    check(out,plan,registered)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("validation:",sum(len(b["results"]) for b in out["batches"]),"diagnostics; no promotion")

if __name__=="__main__":
    main()
