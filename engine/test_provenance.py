import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path
import provenance as P

def main():
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        def git(*args):
            subprocess.run(["git",*args],cwd=root,check=True,capture_output=True)
        git("init");git("config","user.name","test");git("config","user.email","test@example.com")
        for path in [".github/workflows/engine.yml"]+["site/data/"+p for p in P.OUTPUTS]:
            f=root/path;f.parent.mkdir(parents=True,exist_ok=True);f.write_text("{}")
        path="engine/cache/macro/CPI.json"
        f=root/path;P.write(f,{"rows":[["2025-01-01",1],["2025-02-01",2]]})
        git("add",".");git("commit","-m","initial")
        P.write(f,{"rows":[["2025-01-01",1.5],["2025-03-01",3]]})
        now=dt.datetime(2026,11,24,tzinfo=dt.timezone.utc)
        manifest=P.build(root,"123-1",now)
        assert len(manifest["observation_changes"])==1
        delta=manifest["observation_changes"][0]
        assert [delta[k] for k in ("new_to_cache","revised","removed")]==[1,1,1]
        assert not P.check(root,manifest)
        P.write(root/P.ARCHIVE/"123-1.json",manifest);P.write(root/P.PUBLIC,P.public_summary(manifest))
        git("add",".");git("commit","-m","capture")
        P.verify_commit(root)
        assert P.build(root,"124-1",now+dt.timedelta(days=1))["previous"]["sha256"]==P.digest(manifest)
        f.write_text("{}")
        try:
            P.check(root,manifest)
            raise AssertionError("changed data accepted")
        except ValueError:
            pass
        assert not P.check(root,manifest,"HEAD")
    import publication as PUB
    row={"market":"nq","candle":"2026-11-24"}
    original=PUB.identity(row)
    row["inputProvenance"]={"capture_id":"123-1","clean_candles_sha256":"a"*64}
    assert PUB.identity(row)!=original
    old=PUB.identity(row)
    row["inputProvenance"]["clean_candles_sha256"]="b"*64
    assert PUB.identity(row)!=old
    print("provenance tests passed")
if __name__=="__main__":
    main()
