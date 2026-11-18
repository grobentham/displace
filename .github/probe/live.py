import sys, time, datetime as dt, urllib.request
sys.path.insert(0, "engine")
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
def t(u, n=5):
    for i in range(n):
        s=time.time()
        try:
            b=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40).read(); print(f"LIVE {u[:70]} try{i} OK {time.time()-s:.1f}s {len(b)}B")
        except Exception as e: print(f"LIVE {u[:70]} try{i} FAIL {time.time()-s:.1f}s {e!r}")
        time.sleep(1)
t("https://alfred.stlouisfed.org/series/downloaddata?seid=CPILFESL")
t("https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPILFESL&cosd=2025-09-01&coed=2026-10-24&vintage_date=2026-10-24")
t("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF&cosd=2026-10-01")
import publicdata
for i in range(3):
    s=time.time()
    try: publicdata.download("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2&cosd=2026-10-01", tries=1); print(f"LIVE engine-downloader OK {time.time()-s:.1f}s")
    except Exception as e: print(f"LIVE engine-downloader FAIL {e!r}")
import series_store as S
src=S.Public()
for sid, mode in (("CPILFESL","pct"),("PAYEMS","diff"),("ICSA","level")):
    try:
        v=src.vintages(sid); rows=[]; s=time.time()
        for x in [y for y in v if y>="2026-06-01"]:
            S.chain(rows,x,src.snapshot(sid,x,(dt.date.fromisoformat(x)-dt.timedelta(days=420)).isoformat()),mode)
        print(f"LIVE {sid} {len(v)} vintages, chained {len(rows)} in {time.time()-s:.1f}s")
        for i in range(1,len(rows)):
            a,b=rows[i-1],rows[i]; ch=(b[1]/a[1]-1)*100 if mode=="pct" else b[1]-a[1] if mode=="diff" else b[1]
            print(f"LIVE   {b[0]} published {b[2]} -> {ch:.3f}")
    except Exception as e: print("LIVE", sid, "FAIL", repr(e))
import prices
for m in ("gold","nq"):
    r,s=prices.closes(m,"2026-01-01"); print("LIVE",m,s,r[-2:] if r else None)
