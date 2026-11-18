import time, urllib.request, re, json
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
def get(u,t=40):
    for i in range(3):
        try:
            s=time.time(); r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t); b=r.read(20_000_000); return b,time.time()-s,r.headers.get("Content-Type")
        except Exception as e:
            err=e; time.sleep(2)
    raise err
def show(k,u,n=400):
    try:
        b,t,ct=get(u); print(f"LIVE {k} OK {len(b)}B {t:.1f}s {ct} :: {b[:n]!r}"); return b
    except Exception as e: print(f"LIVE {k} FAIL {e!r}")
show("ff_week","https://nfs.faireconomy.media/ff_calendar_thisweek.json",600)
show("ff_xml","https://nfs.faireconomy.media/ff_calendar_thisweek.xml",300)
b=show("cleve_page","https://www.clevelandfed.org/indicators-and-data/inflation-nowcasting",100)
if b:
    h=b.decode("utf8","replace"); print("LIVE cleve links", sorted(set(re.findall(r'["\']([^"\']+\.(?:json|csv|xlsx)[^"\']*)["\']',h)))[:30])
show("gdpnow","https://www.atlantafed.org/-/media/documents/cqer/researchcq/gdpnow/GDPTrackingModelDataAndForecasts.xlsx",100)
for sym in ("GC%3DF","NQ%3DF"):
    for rng,iv in (("730d","1h"),("60d","5m"),("60d","15m")):
        b=show(f"yahoo_{sym}_{iv}",f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}",0)
        if b:
            try:
                r=json.loads(b)["chart"]["result"][0]; ts=r["timestamp"]; print(f"LIVE   {sym} {iv}: {len(ts)} bars from {time.strftime('%Y-%m-%d %H:%M',time.gmtime(ts[0]))} to {time.strftime('%Y-%m-%d %H:%M',time.gmtime(ts[-1]))} UTC")
            except Exception as e: print("LIVE   parse", repr(e))
b=show("yahoo_daily_ohlc","https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?range=5d&interval=1d",0)
if b: q=json.loads(b)["chart"]["result"][0]["indicators"]["quote"][0]; print("LIVE   ohlc keys", list(q))
