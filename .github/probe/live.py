import urllib.request, re
UA={"User-Agent":"Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
h=urllib.request.urlopen(urllib.request.Request("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",headers=UA),timeout=40).read().decode("utf8","replace")
print("LIVE len",len(h))
for y in ("2026","2027"):
    i=h.find(f"{y} FOMC Meetings"); print("LIVE",y,"at",i)
    print("LIVE snippet",re.sub(r"\s+"," ",h[i:i+2500]) if i>0 else "")
print("LIVE classes",sorted(set(re.findall(r'class="(fomc-meeting[^"]*)"',h))))
