import datetime as dt
import json
import tempfile
from pathlib import Path
import atlas as A

def main():
    plan=A.load(A.PLAN)
    now=dt.datetime(2026,11,24,12,tzinfo=dt.timezone.utc)
    spec=plan["indicators"][0]
    calls=[]
    def fake(url,**kwargs):
        calls.append(url)
        return json.dumps([{"page":1,"pages":1,"total":3,"lastupdated":"2026-10-01"},
            [{"countryiso3code":"SGP","date":"2025","indicator":{"id":spec["code"]},"value":3.2},
             {"countryiso3code":"USA","date":"2024","indicator":{"id":spec["code"]},"value":2.5},
             {"countryiso3code":"USA","date":"2025","indicator":{"id":spec["code"]},"value":None}]]).encode()
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        d=A.refresh(spec,plan,now,fake,root)
        assert len(d["rows"])==3 and d["status"]=="available"
        assert A.refresh(spec,plan,now+dt.timedelta(days=1),fake,root)==d and len(calls)==1
        out=A.build(plan,{spec["id"]:d},now)
        assert len(out["countries"])==20 and len(out["indicators"])==8
        assert out["coverage"]["growth"]["2025"]==1 and out["coverage"]["growth"]["2024"]==1
        us=next(c for c in out["countries"] if c["id"]=="USA")
        assert us["metrics"]["growth"]["latest"]==[2024,2.5]
        assert us["metrics"]["growth"]["history"][-2]==[2025,None]
        assert not A.check(out,plan)
        def broken(*a,**kw):
            raise OSError("offline")
        cached=A.refresh(spec,plan,now+dt.timedelta(days=8),broken,root)
        assert cached["status"]=="cached_after_error" and cached["rows"]==d["rows"]
        old=A.build(plan,{spec["id"]:cached},now+dt.timedelta(days=40))
        assert old["indicators"][0]["status"]=="stale_cache"
        missing=A.build(plan,{},now)
        assert missing["coverage"]["growth"]["2025"]==0 and not A.check(missing,plan)
        out["coverage"]["growth"]["2025"]=20
        try:
            A.check(out,plan)
            raise AssertionError("bad coverage accepted")
        except ValueError:
            pass
    print("atlas tests passed")

if __name__=="__main__":
    main()
