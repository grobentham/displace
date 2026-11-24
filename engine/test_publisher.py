import datetime as dt
import json
import tempfile
from pathlib import Path
import publisher as P

def main():
    now=dt.datetime(2026,11,24,12,tzinfo=dt.timezone.utc)
    docs={"macro":{"asof":"2026-11-24","indices":[{"id":"D-GROWTH","name":"Growth","status":"unavailable","score":None,"components":[{"id":"x","status":"stale"}]}]},
          "signals":{"asof":now.isoformat(),"states":[],"events":[]},
          "relationships":{"asof":"2026-11-24","pairs":[],"series":[]},
          "open":{"asof":now.isoformat(),"forecasts":[],"research":[]}}
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)/"publications"
        a=P.publish(docs,now,root)
        assert len(a["reports"])==1 and a["reports"][0]["kind"]=="daily"
        r=P.load(root/a["reports"][0]["path"])
        assert "unavailable" in r["sections"][0]["lines"][0]
        assert not P.check(root.parent)
        docs["macro"]["indices"][0]["name"]="Revised growth"
        assert P.publish(docs,now+dt.timedelta(minutes=10),root)==a
        b=P.publish(docs,now+dt.timedelta(days=1),root)
        assert len(b["reports"])==2 and b["reports"][1]==a["reports"][0]
        path=root/a["reports"][0]["path"]
        r["title"]="Tampered"
        P.jsonwrite(path,r)
        try:
            P.check(root.parent)
            raise AssertionError("tampering accepted")
        except ValueError:
            pass
    print("publisher tests passed")

if __name__=="__main__":
    main()
