import time, urllib.request, json
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
def get(u):
    for i in range(3):
        try: return urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40).read()
        except Exception as e: err=e; time.sleep(2)
    raise err
ff=json.loads(get("https://nfs.faireconomy.media/ff_calendar_thisweek.json"))
for e in ff:
    if e["country"]=="USD": print("LIVE FF", e["date"], "|", e["title"], "|", e["impact"], "| f=", e["forecast"], "| p=", e["previous"])
for k in ("month","quarter"):
    d=json.loads(get(f"https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/nowcast_{k}.json?sc_lang=en"))
    print("LIVE CLEVE", k, type(d).__name__, len(d))
    def walk(x, path="", depth=0):
        if depth>4: return
        if isinstance(x, dict):
            print("LIVE  ", path, "dict keys:", list(x)[:12])
            for kk in list(x)[:3]: walk(x[kk], path+"/"+str(kk), depth+1)
        elif isinstance(x, list):
            print("LIVE  ", path, f"list[{len(x)}]", json.dumps(x[0])[:300] if x else "")
            if x: walk(x[0], path+"[0]", depth+1)
    walk(d)
    if isinstance(d, list): print("LIVE  last", json.dumps(d[-1])[:1500])
