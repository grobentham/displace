import time, urllib.request, urllib.parse, re, io, zipfile
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
u="https://alfred.stlouisfed.org/series/downloaddata?seid=CPILFESL"
h=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=40).read().decode("utf8","replace")
sel=re.search(r'<select[^>]*name="form\[file_type\]"[^>]*>(.*?)</select>',h,re.S).group(1)
print("PROBE file_type options", re.findall(r'<option[^>]*value="([^"]*)"[^>]*>\s*([^<]+)',sel))
hid=re.findall(r'<input[^>]*type="hidden"[^>]*>',h); print("PROBE hidden",hid[:5])
vint=re.findall(r'<option[^>]*value="(\d{4}-\d\d-\d\d)"',re.search(r'name="form\[selected_vintage_dates\]\[\]"[^>]*>(.*?)</select>',h,re.S).group(1))
for ft in ("1","2","3","4"):
    data=[("form[obs_start_date]","2024-01-01"),("form[obs_end_date]","2026-11-01"),("form[units]","lin"),("form[file_format]","csv"),("form[file_type]",ft),("form[download_data]","")]+[("form[selected_vintage_dates][]",v) for v in vint if v>="2024-01-01"]
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,data=urllib.parse.urlencode(data).encode(),headers=UA),timeout=60)
        b=r.read(); ct=r.headers.get("Content-Type"); print(f"PROBE post ft={ft} {ct} {len(b)}B disp={r.headers.get('Content-Disposition')}")
        if b[:2]==b"PK":
            z=zipfile.ZipFile(io.BytesIO(b))
            for n in z.namelist():
                t=z.read(n).decode("utf8","replace"); print(f"PROBE   zip {n} :: {t[:600]!r}")
        else: print(f"PROBE   body :: {b[:600]!r}")
    except Exception as e: print("PROBE post FAIL",ft,repr(e))
