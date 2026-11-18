import json, subprocess, sys
r = subprocess.run([sys.executable, "-u", "engine/predict.py"], capture_output=True, text=True)
for l in r.stdout.splitlines():
    if not any(x in l for x in ("not enough history", "using cached history")): print("RUN", l)
print("RUN stderr", r.stderr[-1500:])
d = json.load(open("site/data/direction/current.json"))
m = json.load(open("engine/cache/direction/model.json"))["model"]
print("LIVE basis", d.get("basis"))
for k in ("cpi", "pce", "nfp", "retail", "ppi", "claims"):
    km = m["kinds"].get(k)
    if not km: print("LIVE", k, "missing"); continue
    for a in ("gold", "nq", "usd", "y2"):
        x = km["assets"].get(a)
        if x:
            bt, c = x["bt"], x["cells"]
            print(f"LIVE dir {k:7} n={km['n']} basis={km.get('basis')} {a:4} {bt['hits']}/{bt['calls']} {bt['rate']:.2f} bs={bt['brierSkill']:+.3f} hot↑{c['hot']['pUp']:.2f}(n{c['hot']['n']}) cool↑{c['cool']['pUp']:.2f}(n{c['cool']['n']}) {'PROVEN' if bt['proven'] else bt['why'][:40]}")
mv = d.get("moves") or {}
print("LIVE markets", json.dumps(mv.get("markets")))
for k, v in (mv.get("kinds") or {}).items():
    for a, s in v.items():
        print(f"LIVE move {k:8} {a:4} n={s['n']} mult={s['mult']} band={s['lo']}-{s['hi']} medRange={s['medRange']} bt={s['bt']} {'PROVEN' if s['proven'] else s['why']}")
for eid, v in d["events"].items():
    print("LIVE ev", eid, v["stage"], v.get("basis"), v.get("expect"), json.dumps(v.get("move"))[:300])
print("LIVE proven", [k for k, r in d["rules"].items() if r["proven"]])
open("probe_current.json", "w").write(json.dumps(d))
print("LIVE JSONSIZE", len(json.dumps(d)))
