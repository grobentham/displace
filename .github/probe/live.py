import sys, json, subprocess
r = subprocess.run([sys.executable, "-u", "engine/predict.py"], capture_output=True, text=True)
for l in r.stdout.splitlines(): print("RUN", l)
print("RUN stderr", r.stderr[-2000:])
d = json.load(open("site/data/direction/current.json"))
for g, gm in d["groups"].items():
    for k, s in gm.items():
        bt = s["bt"]
        print(f"LIVE {g:9} {k:6} n={s['n']:4} since {s['since']} b={s['b']:+.3f} k={s['k']:.2f} | OOS calls {bt['hits']}/{bt['calls']} = {bt['rate']:.3f} of {bt['tested']} tested, brier {bt['brierSkill']:+.3f}, halves {bt['halves']}, p={bt['pval']:.4f} -> {'PROVEN' if s['proven'] else s['why']}")
for eid, v in d["events"].items():
    calls = {k: (c.get('dir'), c.get('p')) for k, c in v.get('hot', {}).items() if c.get('dir')}
    print("LIVE ev", eid, v["stage"], v["kind"], v["consensus"]["title"], v["consensus"]["forecast"], "hot leans:", calls)
s = json.dumps(d)
for i in range(0, len(s), 3000): print(f"JSON|{i//3000:04d}|{s[i:i+3000]}")
