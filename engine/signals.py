"""Deterministic, versioned macro alert monitor with hysteresis.
No market predictions, no historical backdating, no LLM calls.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "research/signals-plan-v1.json"
MACRO = ROOT / "site/data/macro/current.json"
OUT = ROOT / "site/data/signals/current.json"

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def score_ok(x):
    return type(x) in (float, int) and math.isfinite(x) and 0 <= x <= 100

def validate_plan(plan):
    ids = set()
    for r in plan["rules"]:
        if r["id"] in ids or r["direction"] not in ("high", "low"):
            raise ValueError("Invalid or duplicate signal rule")
        ids.add(r["id"])
        a,b,c = r["enter"], r["exit"], r["extreme"]
        if not all(score_ok(x) for x in (a,b,c)):
            raise ValueError("Invalid thresholds")
        if not (b < a < c if r["direction"] == "high" else c < a < b):
            raise ValueError("Invalid hysteresis or extreme threshold")

def crosses(score, threshold, direction):
    return score >= threshold if direction == "high" else score <= threshold

def valid_index(index, macro_date, today):
    if not index or index.get("status") != "available" or not score_ok(index.get("score")):
        return False
    if macro_date != today.isoformat():
        return False
    parts = index.get("components", [])
    max_age = {"daily":10, "weekly":21, "monthly":75}
    if not parts:
        return False
    try:
        return all(c["status"] == "available" and score_ok(c["score"]) and
                   0 <= (today-dt.date.fromisoformat(c["observation_date"])).days <= max_age[c["frequency"]]
                   for c in parts)
    except (KeyError, ValueError, TypeError):
        return False

def evidence(index):
    return [{"id":c["id"],"observation_date":c.get("observation_date"),"value":c.get("value"),
             "score":c.get("score"),"source":"https://fred.stlouisfed.org/series/"+c["id"]} for c in index["components"]]

def run(plan, macro, now, previous=None):
    validate_plan(plan)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    now = now.astimezone(dt.timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    plan_hash = digest(plan)
    old = previous or {"plan_hash":plan_hash,"states":[],"events":[]}
    if old["plan_hash"] != plan_hash:
        raise ValueError("Registered signal plan changed; preserve prior history and create a new version")
    if old.get("asof") and now < dt.datetime.fromisoformat(old["asof"]):
        raise ValueError("Refusing to backdate alert history")
    prior = {s["id"]:s for s in old["states"]}
    events = list(old["events"])
    indices = {i["id"]:i for i in macro.get("indices",[])}
    states = []
    for rule in plan["rules"]:
        key = rule["id"]
        before = prior.get(key, {})
        index = indices.get(rule["index"])
        state = {"id":key,"index":rule["index"],"label":rule["label"],"direction":rule["direction"],
                 "enter":rule["enter"],"exit":rule["exit"],"extreme":rule["extreme"],
                 "active":before.get("active",False),"first_detected":before.get("first_detected"),
                 "last_evaluated":before.get("last_evaluated"),"last_fingerprint":before.get("last_fingerprint"),
                 "severity":before.get("severity"),"score":None,"status":"unavailable","evidence":[]}
        if not valid_index(index,macro.get("asof"),now.date()):
            states.append(state)
            continue
        score = index["score"]
        inputs = evidence(index)
        fp = digest({"score":score,"evidence":inputs})
        active = state["active"]
        if active:
            next_active = not crosses(score,rule["exit"],"low" if rule["direction"]=="high" else "high")
        else:
            next_active = crosses(score,rule["enter"],rule["direction"])
        severity = ("extreme" if crosses(score,rule["extreme"],rule["direction"]) else "elevated") if next_active else None
        event_type = None
        if fp != before.get("last_fingerprint"):
            if not active and next_active:
                event_type = "initial_detection" if before.get("last_fingerprint") is None else "activated"
                state["first_detected"] = stamp
            elif active and not next_active:
                event_type = "cleared"
                state["first_detected"] = None
            elif active and next_active and severity != before.get("severity"):
                event_type = "severity_changed"
            state["last_evaluated"] = stamp
            state["last_fingerprint"] = fp
        state.update(active=next_active,severity=severity,score=score,status="active" if next_active else "normal",evidence=inputs)
        if event_type:
            event = {"rule_id":key,"index":rule["index"],"label":rule["label"],"type":event_type,
                     "observed_at":stamp,"score":score,"severity":severity,"evidence":inputs,
                     "plan_hash":plan_hash,"input_hash":fp}
            event["id"] = digest(event)
            if not any(e["id"]==event["id"] for e in events):
                events.append(event)
        states.append(state)
    return {"version":1,"plan_hash":plan_hash,"asof":stamp,"macro_asof":macro.get("asof"),
            "policy":plan["policy"],"states":states,"events":events}

def check(doc,plan):
    validate_plan(plan)
    bad=[]
    if doc.get("version")!=1 or doc.get("plan_hash")!=digest(plan):
        bad.append("signal plan mismatch")
    rules={r["id"]:r for r in plan["rules"]}
    states=doc["states"]
    if len(states)!=len(rules) or {s["id"] for s in states}!=set(rules):
        bad.append("missing or duplicate rule states")
    for s in states:
        if s["status"] not in ("active","normal","unavailable") or type(s["active"]) is not bool:
            bad.append("invalid rule state")
        elif s["status"]=="unavailable" and s["score"] is not None:
            bad.append("unavailable rule must not expose a score")
        elif s["status"]!="unavailable" and (not score_ok(s["score"]) or s["active"]!=(s["status"]=="active") or not s["evidence"]):
            bad.append("invalid available score or evidence")
    seen=set()
    last=""
    for e in doc["events"]:
        payload={k:v for k,v in e.items() if k!="id"}
        if e["id"] in seen or e["id"]!=digest(payload) or e["rule_id"] not in rules or e["plan_hash"]!=doc["plan_hash"]:
            bad.append("invalid or duplicate history event")
        if not score_ok(e["score"]) or not e["evidence"] or e["observed_at"]<last or e["type"] not in ("initial_detection","activated","cleared","severity_changed"):
            bad.append("invalid event evidence, chronology or type")
        seen.add(e["id"])
        last=e["observed_at"]
    return bad

def main():
    plan=json.loads(PLAN.read_text())
    macro=json.loads(MACRO.read_text())
    previous=json.loads(OUT.read_text()) if OUT.exists() else None
    out=run(plan,macro,dt.datetime.now(dt.timezone.utc),previous)
    errors=check(out,plan)
    if errors:
        raise ValueError("; ".join(errors))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("signals:",sum(s["status"]=="active" for s in out["states"]),"active;",
          sum(s["status"]=="unavailable" for s in out["states"]),"unavailable;",
          len(out["events"]),"recorded transitions")

if __name__=="__main__":
    main()
