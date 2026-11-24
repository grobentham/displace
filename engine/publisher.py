"""Deterministic research publishing from the validated candidate data snapshot.
Immutable report objects and a regenerated catalogue/RSS; no LLM, no inferred causation.
"""
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from email.utils import format_datetime
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"site/data"
OUT=DATA/"publications"
BASE="https://grobentham.github.io/displace/"
SOURCES={"macro":"macro/current.json","signals":"signals/current.json",
         "relationships":"relationships/current.json","open":"open/current.json"}
POLICY="Deterministic snapshot reports, not trading recommendations. Observation dates differ by source. Historical results and descriptive monitoring are not validated forecasts. Source hashes identify inputs at generation time; linked live data may later change."

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def load(path):
    return json.loads(path.read_text())

def write(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(content,encoding="utf-8")
    os.replace(tmp,path)

def jsonwrite(path,obj):
    write(path,json.dumps(obj,indent=2,allow_nan=False,ensure_ascii=False)+"\n")

def number(x,digits=2):
    return f"{x:.{digits}f}" if type(x) in (int,float) and math.isfinite(x) else "Unavailable"

def block(title,lines):
    return {"title":title,"lines":lines}

def source_refs(docs,keys):
    return [{"path":SOURCES[k],"asof":docs[k].get("asof"),"sha256":digest(docs[k])} for k in keys]

def report(rid,kind,title,now,docs,keys,sections):
    return {"version":1,"id":rid,"kind":kind,"title":title,"generated_at":now.isoformat(timespec="seconds"),
            "sources":source_refs(docs,keys),"sections":sections,"limitations":POLICY}

def macro_block(doc):
    lines=[]
    for i in doc["indices"]:
        if i["status"]=="available" and i["score"] is not None:
            dates=", ".join(c["id"]+" "+c["observation_date"] for c in i["components"])
            lines.append(i["id"]+" — "+i["name"]+": "+number(i["score"])+"/100. Observations: "+dates+".")
        else:
            missing=", ".join(c["id"]+" ("+c["status"]+")" for c in i["components"] if c["status"]!="available")
            lines.append(i["id"]+" — unavailable. "+(missing or "Required inputs incomplete")+".")
    return block("Macroeconomic conditions — "+doc["asof"],lines)

def signals_block(doc):
    active=[s for s in doc["states"] if s["status"]=="active"]
    unavailable=sum(s["status"]=="unavailable" for s in doc["states"])
    lines=[f"{len(active)} active monitoring conditions; {unavailable} unavailable rules. A threshold alert is not a prediction."]
    for s in active:
        lines.append(s["label"]+": "+number(s["score"])+"/100 ("+s["severity"]+"). First detected "+str(s["first_detected"])+".")
    return block("Statistical early warnings",lines)

def relationships_block(doc):
    rows=[p for p in doc["pairs"] if p["status"]=="available"]
    flagged=[p for p in rows if p["flags"]]
    labels={s["id"]:s["label"] for s in doc["series"]}
    lines=[f"{len(rows)} of {len(doc['pairs'])} pairs available; {len(flagged)} available pairs have monitoring flags."]
    for p in sorted(flagged,key=lambda x:(-len(x["flags"]),x["a"],x["b"])):
        lines.append(labels[p["a"]]+" / "+labels[p["b"]]+": "+", ".join(f.replace("_"," ") for f in p["flags"])+
                     "; 60-observation correlation "+number(p["correlations"]["60"])+
                     "; shift "+number(p["shift60"])+"; residual z "+number((p.get("divergence") or {}).get("z"))+
                     "; latest matched end "+str(p["latest"])+".")
    return block("Cross-market relationships",lines)

def accountability_block(doc,rows=None):
    subset=doc["forecasts"] if rows is None else rows
    counts=Counter(r["status"] for r in subset)
    lines=[f"{len(subset)} recorded daily forecasts in scope; {counts['verified_resolved']} verified resolved. Counts are not a measure of all possible scheduled forecasts."]
    lines.extend(k.replace("_"," ")+": "+str(v) for k,v in sorted(counts.items()))
    import evidence
    for m in sorted({r["market"] for r in subset}):
        metric=evidence.metrics([r for r in subset if r["market"]==m])
        lines.append(m.upper()+": verified N="+str(metric["n"])+"; Brier "+number(metric["brier"],4)+
                     "; baseline "+number(metric["base_brier"],4)+"; Brier skill "+number(metric["brier_skill"],4)+".")
    return block("Forecast accountability",lines)

def candidates(docs,now):
    day=now.date()
    stamp=day.isoformat()
    o=docs["open"]
    # The first successful candidate after noon UTC is archived; no fabricated backfill.
    if now.hour>=12:
        yield report("daily-"+stamp,"daily","Daily financial intelligence — "+stamp,now,docs,
            ["macro","signals","relationships","open"],[macro_block(docs["macro"]),signals_block(docs["signals"]),
            relationships_block(docs["relationships"]),accountability_block(o)])
    for event in docs["signals"]["events"]:
        # Emit only actual recorded events; timestamp is observation time, not original release.
        lines=[event["label"]+" — "+event["type"].replace("_"," ")+".",
               "Observed "+event["observed_at"]+"; score "+number(event["score"])+"/100.",
               "Severity: "+str(event["severity"] or "cleared")+"."]
        lines.extend(c["id"]+": "+number(c["value"],4)+"; observation "+str(c["observation_date"])+"; score "+number(c["score"]) for c in event["evidence"])
        yield report("signal-"+event["id"],"signal",event["label"]+" — "+event["type"].replace("_"," "),now,docs,["signals"],[block("Recorded transition",lines)])
    for b in o["research"]:
        rid="research-"+digest({k:b[k] for k in ("family","kind","start","end","plan_hash")})
        lines=[b["family"]+" · "+b["kind"]+" · "+b["start"]+" to "+b["end"]+" (exclusive).",
               str(b["total"])+" registered tests; "+str(b["promoted"])+" promoted models."]
        lines.extend(k.replace("_"," ")+": "+str(v) for k,v in sorted(b["statuses"].items()))
        if b["family"] in ("Discovery v1","Discovery v2"):
            lines.append("Legacy paired-week candidate status is under methodological review and is not a validated or profitable trading edge. See the public research correction. Full results: "+b["source"]+".")
        else:
            lines.append("Corrected method (overall rate difference, 28-day clustered errors). History seen before registration is descriptive only; candidates need 30 prospective blocks. Not a trading edge. Full results: "+b["source"]+".")
        yield report(rid,"research",b["family"]+" — "+b["kind"]+" research batch",now,docs,["open"],[block("Research results",lines)])
    # First observed snapshot per new UTC week/month. Filter by completed target dates.
    # These are as-of reviews, not final settlement claims; unresolved outcomes remain explicit.
    end_week=day-dt.timedelta(days=day.weekday())
    start_week=end_week-dt.timedelta(days=7)
    end_month=day.replace(day=1)
    start_month=(end_month-dt.timedelta(days=1)).replace(day=1)
    for kind,start,end in [("weekly",start_week,end_week),("monthly",start_month,end_month)]:
        rows=[r for r in o["forecasts"] if start.isoformat()<=r["for"]<end.isoformat()]
        if not rows:
            continue
        title=("Weekly accountability review" if kind=="weekly" else "Monthly model evidence review")
        yield report(kind+"-"+start.isoformat(),kind,title+" — "+start.isoformat(),now,docs,["open"],
            [block("Review period",[start.isoformat()+" to "+end.isoformat()+" (exclusive), by target date.",
             "Frozen as-of snapshot; later settlements appear in Displace Open, not rewritten here."]),accountability_block(o,rows)])

def validate_report(r):
    if not re.fullmatch(r"[a-z0-9-]{1,100}",r["id"]) or r["kind"] not in ("daily","signal","research","weekly","monthly"):
        raise ValueError("Invalid report identifier or type")
    if not r["title"] or not r["sections"] or not r["sources"]:
        raise ValueError("Incomplete report")
    if dt.datetime.fromisoformat(r["generated_at"]).tzinfo is None:
        raise ValueError("Report timestamp lacks timezone")
    for s in r["sources"]:
        if s["path"] not in SOURCES.values() or not re.fullmatch(r"[0-9a-f]{64}",s["sha256"]):
            raise ValueError("Invalid source evidence")
    for b in r["sections"]:
        if not b["title"] or not b["lines"] or any(not isinstance(x,str) or not x for x in b["lines"]):
            raise ValueError("Invalid text section")

def catalog(reports):
    return {"version":1,"reports":[{"id":r["id"],"kind":r["kind"],"title":r["title"],"generated_at":r["generated_at"],
            "sha256":digest(r),"path":"reports/"+r["id"]+".json"} for r in sorted(reports,key=lambda r:(r["generated_at"],r["id"]),reverse=True)]}

def rss(cat):
    root=ET.Element("rss",version="2.0")
    ch=ET.SubElement(root,"channel")
    for k,v in {"title":"Displace Research","link":BASE+"publications.html","description":"Source-linked automated financial research and accountability reports."}.items():
        ET.SubElement(ch,k).text=v
    for r in cat["reports"][:50]:
        item=ET.SubElement(ch,"item")
        url=BASE+"publications.html?id="+r["id"]
        for k,v in {"title":r["title"],"link":url,"guid":url,"description":r["kind"].capitalize()+" research report. Read the full source-linked evidence.",
                    "pubDate":format_datetime(dt.datetime.fromisoformat(r["generated_at"]))}.items():
            ET.SubElement(item,k).text=v
    return ET.tostring(root,encoding="unicode",xml_declaration=True)+"\n"

def check(data):
    root=data/"publications"
    cat=load(root/"index.json")
    reports=[]
    for path in sorted((root/"reports").glob("*.json")):
        r=load(path)
        validate_report(r)
        if path.stem!=r["id"]:
            raise ValueError("Report path mismatch")
        reports.append(r)
    if cat!=catalog(reports):
        raise ValueError("Catalogue or report hash mismatch")
    if (root/"feed.xml").read_text()!=rss(cat):
        raise ValueError("RSS differs from catalogue")
    return []

def publish(docs,now,root):
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    now=now.astimezone(dt.timezone.utc)
    folder=root/"reports"
    folder.mkdir(parents=True,exist_ok=True)
    # Existing catalogue is an integrity record: never silently replace old reports.
    if (root/"index.json").exists():
        check(root.parent)
    for r in candidates(docs,now):
        validate_report(r)
        path=folder/(r["id"]+".json")
        if not path.exists():
            jsonwrite(path,r)
    reports=[load(p) for p in sorted(folder.glob("*.json"))]
    cat=catalog(reports)
    jsonwrite(root/"index.json",cat)
    write(root/"feed.xml",rss(cat))
    check(root.parent)
    return cat

def main():
    docs={k:load(DATA/p) for k,p in SOURCES.items()}
    # Check the upstream candidate evidence before generating any prose.
    import evidence
    import signals
    import relationships
    errors=evidence.check(docs["open"])+signals.check(docs["signals"],load(signals.PLAN))+relationships.check(docs["relationships"],load(relationships.PLAN))
    if errors:
        raise ValueError("; ".join(errors))
    out=publish(docs,dt.datetime.now(dt.timezone.utc),OUT)
    print("publishing:",len(out["reports"]),"archived reports")

if __name__=="__main__":
    main()
