import sys, time, datetime as dt, traceback
sys.path.insert(0, "engine")
import series_store as S, publicdata
src = S.Public()
for sid in ("CPILFESL", "ICSA"):
    v = [x for x in src.vintages(sid) if x >= "2008-06-01"]
    picks = v[:3] + ([x for x in v if x >= "2024-06-13"][:3] if sid == "ICSA" else [])
    for x in picks:
        st = (dt.date.fromisoformat(x) - dt.timedelta(days=420)).isoformat()
        t = time.time()
        try:
            r = src.snapshot(sid, x, st); print(f"LIVE {sid} {x} OK {len(r)} rows {time.time()-t:.1f}s last={r[-1] if r else None}")
        except Exception as e:
            print(f"LIVE {sid} {x} FAIL {time.time()-t:.1f}s {e!r}")
            from urllib.parse import urlencode
            url = f"{publicdata.ALFRED}/graph/alfredgraph.csv?" + urlencode({"id": sid, "cosd": st, "coed": x, "vintage_date": x})
            try: print("LIVE   body:", publicdata.download(url, tries=1)[:300])
            except Exception as e2: print("LIVE   raw FAIL", repr(e2))
