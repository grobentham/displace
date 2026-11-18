import time, urllib.request, re
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
def get(u,t=40):
    s=time.time(); r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=t); b=r.read(5_000_000); return b,time.time()-s
def show(k,u):
    try:
        b,t=get(u); print(f"PROBE {k} OK {len(b)}B {t:.1f}s :: {b[:500]!r}")
        return b
    except Exception as e:
        print(f"PROBE {k} FAIL {e!r}")
# 1. multiple vintages in one ALFRED CSV
show("alfred_multi_comma","https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPILFESL&cosd=2026-06-01&coed=2026-11-13&vintage_date=2026-09-11,2026-10-24,2026-11-10")
show("alfred_multi_repeat","https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPILFESL&cosd=2026-06-01&coed=2026-11-13&vintage_date=2026-09-11&vintage_date=2026-10-24")
# 2. downloaddata form structure
try:
    b,t=get("https://alfred.stlouisfed.org/series/downloaddata?seid=CPILFESL")
    h=b.decode("utf8","replace")
    for m in re.finditer(r"<form[^>]*>",h): print("PROBE form",m.group(0)[:300])
    names=sorted(set(re.findall(r'name="([^"]+)"',h))); print("PROBE names",names[:80])
    for sel in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>',h,re.S):
        opts=re.findall(r'<option[^>]*value="([^"]*)"',sel.group(2)); print("PROBE select",sel.group(1),len(opts),opts[:5],opts[-3:])
    i=h.find("nitial"); print("PROBE initial ctx",h[max(0,i-400):i+400].replace("\n"," ")[:800])
except Exception as e: print("PROBE dd FAIL",repr(e))
# 3. vintage dates list
show("alfred_vintagedates","https://alfred.stlouisfed.org/series?seid=CPILFESL")
# 4. FRED timing repeated (DNS/latency)
for i in range(4):
    try:
        b,t=get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2&cosd=2026-10-01",t=30); print(f"PROBE fred_timing {i} {t:.1f}s {len(b)}B")
    except Exception as e: print("PROBE fred_timing FAIL",repr(e))
for u in ["https://api.bls.gov/publicAPI/v1/timeseries/data/CUSR0000SA0L1E","https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value=2026","https://www.chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv"]:
    show("retry_"+u.split('/')[2],u)
