import copy
import datetime as dt
import json
import signals as S

PLAN=json.loads(S.PLAN.read_text())
UTC=dt.timezone.utc
T=dt.datetime(2026,11,24,12,tzinfo=UTC)

def macro(score, now=T, valid=True):
    return {"asof":now.date().isoformat(),"indices":[{"id":"D-STRESS","score":score,
            "status":"available" if valid else "unavailable",
            "components":[{"id":"VIXCLS","status":"available","score":score,"frequency":"daily",
                           "observation_date":now.date().isoformat(),"value":score}]}]}

def state(doc):
    return next(s for s in doc["states"] if s["id"]=="stress_high")

def main():
    a=S.run(PLAN,macro(81),T)
    assert state(a)["active"] and len(a["events"])==1
    assert a["events"][0]["type"]=="initial_detection" and not S.check(a,PLAN)
    b=S.run(PLAN,macro(81),T+dt.timedelta(minutes=1),a)
    assert len(b["events"])==1 and state(b)["last_evaluated"]==state(a)["last_evaluated"]
    c=S.run(PLAN,macro(75),T+dt.timedelta(minutes=2),b)
    assert state(c)["active"] and len(c["events"])==1
    d=S.run(PLAN,macro(91),T+dt.timedelta(minutes=3),c)
    assert state(d)["severity"]=="extreme" and d["events"][-1]["type"]=="severity_changed"
    e=S.run(PLAN,macro(None,valid=False),T+dt.timedelta(minutes=4),d)
    assert state(e)["active"] and state(e)["status"]=="unavailable" and len(e["events"])==2
    f=S.run(PLAN,macro(65),T+dt.timedelta(minutes=5),e)
    assert not state(f)["active"] and f["events"][-1]["type"]=="cleared"
    g=S.run(PLAN,macro(80),T+dt.timedelta(minutes=6),f)
    assert state(g)["active"] and g["events"][-1]["type"]=="activated"
    assert not S.check(g,PLAN)
    stale=macro(99)
    stale["indices"][0]["components"][0]["observation_date"]="2026-10-01"
    assert state(S.run(PLAN,stale,T))["status"]=="unavailable"
    stale_day=S.run(PLAN,macro(99),T+dt.timedelta(days=1))
    assert state(stale_day)["status"]=="unavailable"
    tampered=copy.deepcopy(g)
    tampered["events"][0]["score"]=1
    assert S.check(tampered,PLAN)
    try:
        S.run(dict(PLAN,policy="changed"),macro(90),T,g)
        raise AssertionError("modified plan accepted")
    except ValueError:
        pass
    try:
        S.run(PLAN,macro(90),T-dt.timedelta(days=1),g)
        raise AssertionError("backdated alert accepted")
    except ValueError:
        pass
    print("statistical signals tests passed")

if __name__=="__main__":
    main()
