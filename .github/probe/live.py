import sys, json, math, time, statistics, datetime as dt, urllib.request, bisect
from zoneinfo import ZoneInfo
sys.path.insert(0, "engine")
import prices, series_store as S
NY = ZoneInfo("America/New_York")
TV = {"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
def get(u, h):
    for i in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=40).read()
        except Exception as e: err = e; time.sleep(3)
    raise err
t0 = time.time(); ev = []
d = dt.date(2010, 1, 1)
while d < dt.date(2026, 11, 19):
    n = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    ev += json.loads(get(f"https://economic-calendar.tradingview.com/events?from={d}T00:00:00.000Z&to={n}T00:00:00.000Z&countries=US", TV))["result"]
    d = n
print(f"LIVE tv events {len(ev)} in {time.time()-t0:.0f}s")
# kind: [(title regex exact, sign, weight)]
K = {"cpi": [("Core Inflation Rate MoM", 1, 2), ("Inflation Rate MoM", 1, 1)],
     "ppi": [("PPI MoM", 1, 2), ("Core PPI MoM", 1, 1)],
     "pce": [("Core PCE Price Index MoM", 1, 2)],
     "nfp": [("Non Farm Payrolls", 1, 2), ("Unemployment Rate", -1, 1), ("Average Hourly Earnings MoM", 1, 1)],
     "retail": [("Retail Sales MoM", 1, 2), ("Retail Sales Control Group", 1, 1)],
     "claims": [("Initial Jobless Claims", -1, 1)],
     "jolts": [("JOLTs Job Openings", 1, 1)],
     "gdp": [("GDP Growth Rate QoQ Adv", 1, 1)],
     "ism-m": [("ISM Manufacturing PMI", 1, 1)], "ism-s": [("ISM Services PMI", 1, 1)],
     "umich": [("Michigan Consumer Sentiment Prel", 1, 1)],
     "durables": [("Durable Goods Orders MoM", 1, 1), ("Durable Goods Orders Ex Transp MoM", 1, 1)],
     "homes": [("New Home Sales", 1, 1)], "conf": [("CB Consumer Confidence", 1, 1)],
     "adp": [("ADP Employment Change", 1, 1)], "philly": [("Philadelphia Fed Manufacturing Index", 1, 1)],
     "empire": [("NY Empire State Manufacturing Index", 1, 1)]}
by = {}
for e in ev:
    if e.get("actual") is None or e.get("forecast") is None: continue
    when = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(NY)
    by.setdefault(e["title"], []).append((when, float(e["actual"]) - float(e["forecast"])))
for t in by: by[t].sort()
events = []  # (when, kind, z_hawk)
for k, comps in K.items():
    slots = {}
    for title, sign, w in comps:
        hist = []
        for when, s in by.get(title, []):
            sc = statistics.median([abs(x) for x in hist]) * 1.4826 if len(hist) >= 12 else None
            hist.append(s)
            if sc:
                z = max(-4, min(4, s / sc))
                slots.setdefault(when, []).append((sign * z, w))
    for when, zs in slots.items():
        zz = sum(z * w for z, w in zs) / sum(w for _, w in zs)
        events.append((when, k, zz))
events.sort()
print("LIVE events with consensus z:", len(events), {k: sum(1 for e in events if e[1] == k) for k in K})
PRIOR = {"usd": 1, "y2": 1, "gold": -1, "nq": -1}
daily = {}
for a in ("gold", "nq"):
    c = prices._load(a)["closes"]; dd = sorted(c); daily[a] = (dd, c, "pct")
for a, sid in (("usd", "DTWEXBGS"), ("y2", "DGS2")):
    rows = S.load(sid, False)["rows"]; c = {r[0]: r[1] for r in rows}; daily[a] = (sorted(c), c, "bp" if a == "y2" else "pct")
def dmove(a, day):
    dd, c, u = daily[a]
    if day not in c: return None
    i = bisect.bisect_left(dd, day)
    if i == 0: return None
    return (c[day] - c[dd[i-1]]) * 100 if u == "bp" else (c[day] / c[dd[i-1]] - 1) * 100
def binp(h, n): return sum(math.comb(n, i) for i in range(h, n + 1)) / 2 ** n if n else 1
groups = {"all": None, "big3": {"cpi", "nfp", "pce"}, "inflation": {"cpi", "ppi", "pce"}, "labor": {"nfp", "claims", "jolts", "adp"}, "activity": {"retail", "ism-m", "ism-s", "gdp", "durables"}}
print("LIVE ===== DAILY CLOSE, consensus surprise")
for a in ("gold", "nq", "usd", "y2"):
    for name, ks in groups.items():
        for th in (0.0, 1.0):
            sel = [(w, k, z, m) for w, k, z in events if (ks is None or k in ks) and abs(z) >= th and w.hour < 16 for m in [dmove(a, w.date().isoformat())] if m]
            n = len(sel); h = sum((z * PRIOR[a] > 0) == (m > 0) for _, _, z, m in sel)
            e1 = [s for s in sel if s[0].year < 2018]; e2 = [s for s in sel if s[0].year >= 2018]
            h1 = sum((z * PRIOR[a] > 0) == (m > 0) for _, _, z, m in e1); h2 = sum((z * PRIOR[a] > 0) == (m > 0) for _, _, z, m in e2)
            if n >= 20: print(f"LIVE d {a:4} {name:9} |z|>={th}: {h}/{n}={h/n:.3f} p={binp(h,n):.4f} | <2018 {h1/max(len(e1),1):.2f} n{len(e1)} | 2018+ {h2/max(len(e2),1):.2f} n{len(e2)}")
bars = {}
for sym, a in (("GC%3DF", "gold"), ("NQ%3DF", "nq")):
    r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=730d&interval=1h", {"User-Agent": "Mozilla/5.0"}))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    bars[a] = [(dt.datetime.fromtimestamp(t, NY), o, c) for t, o, c in zip(r["timestamp"], q["open"], q["close"]) if o and c]
def hmove(a, rel, hours):
    b = bars[a]; ts = [x[0] for x in b]
    i = bisect.bisect_right(ts, rel - dt.timedelta(minutes=1)) - 1   # bar containing the release (starts before it)
    if i < 1: return None
    start = b[i - 1][2] if (rel - b[i][0]) >= dt.timedelta(minutes=30) and False else b[i][1]  # open of the bar containing the release
    j = bisect.bisect_right(ts, rel + dt.timedelta(hours=hours) - dt.timedelta(hours=1))
    if j - 1 <= i or j - 1 >= len(b): return None
    return (b[j - 1][2] / start - 1) * 100
print("LIVE ===== INTRADAY (1h bars since mid-2024), consensus surprise; move from the open of the bar holding the release")
for a in ("gold", "nq"):
    for hrs in (1, 2):
        for name, ks in groups.items():
            for th in (0.0, 1.0):
                sel = [(k, z, m) for w, k, z in events if (ks is None or k in ks) and abs(z) >= th and w > bars[a][0][0] + dt.timedelta(days=2) for m in [hmove(a, w, hrs)] if m]
                n = len(sel); h = sum((z * PRIOR[a] > 0) == (m > 0) for _, z, m in sel)
                if n >= 15: print(f"LIVE i {a:4} +{hrs}h {name:9} |z|>={th}: {h}/{n}={h/n:.3f} p={binp(h,n):.4f}")
