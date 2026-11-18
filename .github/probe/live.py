import sys, os, json, math, datetime as dt, urllib.request, time
from zoneinfo import ZoneInfo
sys.path.insert(0, "engine")
import direction as D, series_store as S, nowcast, prices
from catalog import RELEASES
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
def get(u):
    for i in range(3):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read()
        except Exception as e: err = e; time.sleep(2)
    raise err
class NoNet:
    def vintages(self, *a): raise OSError
    def snapshot(self, *a): raise OSError
    def daily(self, *a): raise OSError
now = dt.datetime(2026, 11, 18, 18, 0, tzinfo=NY)
S.Store._daily = lambda self, sid: S.load(sid, False)
store = S.Store(now, S.model_modes(D.MODELS), log=lambda *a: None, source=NoNet())
past, latest, daily_nc = nowcast.load(log=lambda *a: None)
records = dict(past)
for k in ("cpi", "pce"):
    for period, _, rt in S.load(D.MODELS[k]["head"][0], True)["rows"]:
        if rt and (k, rt) not in records:
            v = nowcast.before(daily_nc, k, period[:7], rt)
            if v is not None: records[(k, rt)] = v
D.BASIS.update({"cpi": "nowcast", "pce": "nowcast"})
fed, infl = D.regimes(store)
px = {"usd": D.Px([(d, v) for d, v, _ in store("DTWEXBGS", D.START)], "pct")}
other = {k: {o[2] for o in (store(D.MODELS[k]["head"][0], "2008-01-01", True) or [])} for k in D.HIGH}
pts = {}
for k in D.MODELS:
    others = set().union(*[v for kk, v in other.items() if kk != k])
    pts[k] = D.build_points(k, store, records, px, others, fed, infl)[0]
SIGN = {"cpi": 1, "ppi": 1, "pce": 1, "nfp": 1, "retail": 1, "durables": 1, "claims": -1, "jolts": 1, "gdp": 1, "umich": 1, "homes": 1}
bars = {}
for sym, a in (("GC%3DF", "gold"), ("NQ%3DF", "nq")):
    for iv, rng in (("1h", "730d"), ("5m", "60d")):
        r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}"))["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        bars[(a, iv)] = [(dt.datetime.fromtimestamp(t, NY), o, c) for t, o, c in zip(r["timestamp"], q["open"], q["close"]) if o and c]
        print("LIVE bars", a, iv, len(bars[(a, iv)]), bars[(a, iv)][0][0], bars[(a, iv)][-1][0], "step", bars[(a, iv)][1][0] - bars[(a, iv)][0][0])
def price_at(b, when, after):
    """open of the first bar starting at/after `when` (after=True) or close of the last bar ending at/before it."""
    if after:
        for t, o, c in b:
            if t >= when: return o, t
    else:
        best = None
        for t, o, c in b:
            if t < when: best = (c, t)
            else: break
        return best
    return None
def react(a, iv, rel, minutes, pre=0):
    b = bars[(a, iv)]
    step = b[1][0] - b[0][0]
    p0 = price_at(b, rel - dt.timedelta(minutes=pre), False)   # last close before the release
    p1 = price_at(b, rel + dt.timedelta(minutes=minutes) - step, False)
    if not p0 or not p1 or p1[1] < rel or (rel - p0[1]) > step + dt.timedelta(minutes=pre) : return None
    return (p1[0] / p0[0] - 1) * 100
def binp(h, n): return sum(math.comb(n, i) for i in range(h, n + 1)) / 2 ** n if n else 1
for iv, wins in (("1h", (60, 120)), ("5m", (5, 15, 30, 60))):
    for a in ("gold", "nq"):
        for w in wins:
            for name, ks in (("all", None), ("big3", {"cpi", "nfp", "pce"}), ("inflation", {"cpi", "ppi", "pce"}), ("labor", {"nfp", "claims", "jolts"})):
                for th in (0.0, 1.0):
                    n = h = 0; mags = []
                    for k, p in pts.items():
                        if ks and k not in ks: continue
                        hh, mm = map(int, RELEASES[k]["time"].split(":"))
                        for x in p:
                            z = SIGN[k] * x["z"]
                            if abs(z) < th: continue
                            rel = dt.datetime.combine(dt.date.fromisoformat(x["date"]), dt.time(hh, mm), NY)
                            if rel < bars[(a, iv)][0][0] + dt.timedelta(days=1): continue
                            m = react(a, iv, rel, w)
                            if m is None or m == 0: continue
                            n += 1; h += (z < 0) == (m > 0); mags.append(abs(m))
                    if n >= 8:
                        print(f"LIVE {iv} {a:4} +{w:3}m {name:9} |z|>={th}: {h}/{n} = {h/n:.3f} p={binp(h,n):.3f} med|move|={sorted(mags)[len(mags)//2]:.3f}%")
