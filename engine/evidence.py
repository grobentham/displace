"""Public evidence snapshot. No historical observation is treated as a live prediction."""
import datetime as dt
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
import publication as P
from publication import cutoff
import discovery as D

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"site/data"
OUT=DATA/"open/current.json"
STATES=("void","late","unknown_eligibility","unverified","verified_pending","verified_resolved","verified_invalid_outcome","verified_overdue")

def numeric_prob(x):
    return type(x) in (int,float) and math.isfinite(x) and 0<=x<=1

def binary(x):
    return type(x) in (int,bool) and x in (0,1)

def valid_outcome(r):
    return (r.get("day")==r.get("for") and all(binary(r.get(k)) for k in ("up","highTaken","lowTaken","inRange"))
            and all(numeric_prob(r.get(k)) for k in ("p_up","base_up","p_high","p_low")))

def ledger(rows,receipts,now):
    out=[]
    seen=set()
    for row,path in rows:
        key=(row["market"],row["candle"])
        if key in seen:
            raise ValueError("Duplicate forecast in active/archive records: "+str(key))
        seen.add(key)
        identity=P.identity(row)
        rec=receipts.get(identity)
        try:
            start=cutoff(row)
            verified=P.verified(row,receipts,start)
        except (ValueError,TypeError,KeyError):
            verified=False
            start=None
        if row.get("void"):
            status="void"
        elif row.get("eligible") is False:
            status="late"
        elif row.get("eligible") is not True:
            status="unknown_eligibility"
        elif not verified:
            status="unverified"
        elif row.get("scored"):
            status="verified_resolved" if valid_outcome(row) else "verified_invalid_outcome"
        elif now.date()>dt.date.fromisoformat(row["for"])+dt.timedelta(days=3):
            status="verified_overdue"
        else:
            status="verified_pending"
        item={k:row.get(k) for k in ("market","candle","for","logged","tier","bias","p_up","base_up","p_high","p_low","range_lo","range_hi","up","highTaken","lowTaken","inRange","day","correction")}
        item.update({k: row[k] for k in ("range_points", "prior_levels") if k in row})
        item.update(id=identity,status=status,source=path,receipt=rec,target_start=start.isoformat() if start else None)
        out.append(item)
    return sorted(out,key=lambda r:(r["for"],r["market"],r["candle"]))

def metrics(rows):
    done=[r for r in rows if r["status"]=="verified_resolved"]
    n=len(done)
    result={"n":n,"brier":None,"base_brier":None,"brier_skill":None,"range_coverage":None,
            "level_brier":None,"tested_direction_n":0,"tested_direction_accuracy":None,"calibration":[]}
    if not n:
        return result
    brier=sum((r["p_up"]-r["up"])**2 for r in done)/n
    baseline=sum((r["base_up"]-r["up"])**2 for r in done)/n
    calls=[r for r in done if r["tier"]=="tested" and r["bias"] in ("long","short")]
    result.update(brier=brier,base_brier=baseline,brier_skill=1-brier/baseline if baseline else None,
                  range_coverage=sum(r["inRange"] for r in done)/n,
                  level_brier=sum((r["p_high"]-r["highTaken"])**2+(r["p_low"]-r["lowTaken"])**2 for r in done)/(2*n),
                  tested_direction_n=len(calls),
                  tested_direction_accuracy=sum((r["bias"]=="long")==bool(r["up"]) for r in calls)/len(calls) if calls else None)
    for i in range(10):
        sample=[r for r in done if min(9,int(r["p_up"]*10))==i]
        if sample:
            result["calibration"].append({"lo":i/10,"hi":(i+1)/10,"n":len(sample),
                "mean_probability":sum(r["p_up"] for r in sample)/len(sample),
                "observed_rate":sum(r["up"] for r in sample)/len(sample)})
    return result

def research_summary(docs):
    out=[]
    for name,path,doc in docs:
        for b in doc["batches"]:
            counts=Counter(r["status"] for r in b["results"])
            out.append({"family":name,"source":path,"kind":b["kind"],"start":b["start"],"end":b["end"],
                        "total":len(b["results"]),"statuses":dict(counts),"promoted":sum(r.get("promoted") is True for r in b["results"]),
                        "plan_hash":doc["plan_hash"]})
    return out

def make(rows,receipts,events,research,now,models,legacy=None):
    records=ledger(rows,receipts,now)
    counts=Counter(r["status"] for r in records)
    by={m:metrics([r for r in records if r["market"]==m]) for m in sorted({r["market"] for r in records})}
    historical=[r for r in events if r.get("eligible") is not True]
    return {"version":1,"asof":now.isoformat(),"scope":"Recorded forecasts only; not all possible scheduled forecasts. No receipt before the target start means no prospective credit.",
            "forecast_counts":{s:counts[s] for s in STATES},"total":len(records),"by_market":by,"forecasts":records,
            "corrections":[{"id":r["id"],"market":r["market"],"target":r["for"],"original_range":[r["range_lo"],r["range_hi"]],
                            "correction":r["correction"],"source":r["source"]} for r in records if r["correction"]],
            "event_observations":{"total":len(events),"historical_only":len(historical),"historical_resolved":sum("hit" in r for r in historical),
                                  "source":"direction/log.json","policy":"Post-release reaction windows are historical observations, excluded from prospective accuracy."},
            "research":research_summary(research),"legacy_research":legacy or {},
            "models":models,"limitations":["Publication receipts certify a successful Pages deployment timestamp, not delivery to every browser.",
            "The publication cutoff uses exchange session opens, including holiday schedules. Special session hours can change by exchange advisory.",
            "Overdue means target date plus three calendar days; it is a monitoring heuristic, not proof of a missing settlement.",
            "Prospective scores exclude invalid, late, unverified and unresolved records. Small samples do not establish an edge.",
            "Historical research, descriptive macro indicators and monitoring thresholds are not prospective predictions.",
            "Research plans and code hashes identify current implementations; historical records do not all carry model or dataset versions.",
            "Data provider revisions, missing observations and futures rolls may affect calculations. Data rights and commercial compliance remain outstanding."]}

def check(doc):
    problems=[]
    ids=[r["id"] for r in doc["forecasts"]]
    counts=Counter(r["status"] for r in doc["forecasts"])
    if len(ids)!=len(set(ids)) or doc["total"]!=len(ids) or doc["forecast_counts"]!={s:counts[s] for s in STATES} or sum(counts.values())!=sum(doc["forecast_counts"].values()):
        problems.append("forecast accounting mismatch")
    for market,summary in doc["by_market"].items():
        expected=metrics([r for r in doc["forecasts"] if r["market"]==market])
        if summary!=expected:
            problems.append("score mismatch: "+market)
    if set(doc["by_market"])!={r["market"] for r in doc["forecasts"]}:
        problems.append("market coverage mismatch")
    if any(sum(b["statuses"].values())!=b["total"] or b["promoted"]>b["total"] for b in doc["research"]):
        problems.append("research accounting mismatch")
    if len(doc["corrections"])!=sum(bool(r["correction"]) for r in doc["forecasts"]):
        problems.append("correction accounting mismatch")
    return problems

def load(path):
    return json.loads(path.read_text())

def main():
    paths=[DATA/"bias/log.json"]+sorted((DATA/"bias/archive").glob("log-*.json"))
    rows=[(r,path.relative_to(DATA).as_posix()) for path in paths for r in load(path)["entries"]]
    research=[("Discovery v1","research/discovery.json",load(DATA/"research/discovery.json")),
              ("Discovery v2","research/discovery-v2.json",load(DATA/"research/discovery-v2.json")),
              ("Discovery v3","research/discovery-v3.json",load(DATA/"research/discovery-v3.json")
               if (DATA/"research/discovery-v3.json").exists() else {"batches":[]})]
    registry=[
        ("Daily market bias and range","engine/bias.py",None,"Base-rate or tested by market; live evidence counted separately"),
        ("Economic event reactions","engine/surprise.py",None,"Historical reaction window; not prospective"),
        ("Discovery v1","engine/discovery.py","research/discovery-plan-v1.json","Retired 24 Nov 2026: biased within-week estimator; results kept"),
        ("Discovery v2","engine/discovery_v2.py","research/discovery-plan-v2.json","Retired 24 Nov 2026: biased within-week estimator; results kept"),
        ("Discovery v3","engine/discovery_v3.py","research/discovery-plan-v3.json","History descriptive only; prospective from Dec 2026, candidates need 30 blocks"),
        ("Macro indices","engine/macro.py","research/macro-plan-v2.json","Descriptive current-vintage indicators"),
        ("Early warnings","engine/signals.py","research/signals-plan-v1.json","Descriptive threshold monitoring"),
        ("Financial relationships","engine/relationships.py","research/relationships-plan-v1.json","Descriptive correlations and residuals"),
        ("Iron Brain live plans","engine/intraday.py",None,"Live intraday plans witnessed from 25 Nov 2026; counted only if locked before entry, seen live and unchanged")]
    models=[{"name":name,"code":path,"code_sha256":hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
             "plan":plan,"plan_hash":D.digest(load(ROOT/plan)) if plan else None,"classification":classification}
            for name,path,plan,classification in registry]
    old=load(ROOT/"research/results-2026-11-24.json")
    legacy={"source":"research/results-2026-11-24.json","registered":old["registered"],
            "verdict":old["verdict"],"note":old["note_on_process"],"tests":sum(len(v) for v in old["results"].values())}
    out=make(rows,P.load(),load(DATA/"direction/log.json")["rows"],research,dt.datetime.now(dt.timezone.utc),models,legacy)
    errors=check(out)
    if errors:
        raise ValueError("; ".join(errors))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("open:",out["total"],"recorded forecasts;",out["forecast_counts"]["verified_resolved"],"verified resolved")

if __name__=="__main__":
    main()
