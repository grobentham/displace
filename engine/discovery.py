"""Configuration-driven, non-LLM research registry and scheduled batch runner.
Historical study is exploratory. Prospective blocks are frozen on first complete run.
No auto-promotion, no parameter selection, no trading recommendations.
"""
import datetime as dt
import hashlib
import json
import math
import os
import statistics as st
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "research/discovery-plan-v1.json"
OUT = ROOT / "site/data/research/discovery.json"
CONDITIONS = {"previous_up", "previous_down", "wide_range", "narrow_range"}

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def month_add(d, months):
    n = d.year * 12 + d.month - 1 + months
    return dt.date(n // 12, n % 12 + 1, 1)

def periods(plan, today):
    yield ("historical", plan["historical"]["start"], plan["historical"]["end"])
    start = dt.date.fromisoformat(plan["prospective_start"])
    while True:
        end = month_add(start, plan["block_months"])
        if end > today:
            break
        yield ("prospective", start.isoformat(), end.isoformat())
        start = end

def observations(rows):
    # Each condition is computed from finished candles prior to the outcome.
    out = []
    for i in range(20, len(rows) - 1):
        d, v = rows[i]
        nxt, future = rows[i + 1]
        if (dt.date.fromisoformat(nxt) - dt.date.fromisoformat(d)).days > 4:
            continue
        if (dt.date.fromisoformat(d) - dt.date.fromisoformat(rows[i-1][0])).days > 4:
            continue
        ranges = [(x[1] - x[2]) / x[3] for _, x in rows[i-20:i]]
        med = st.median(ranges)
        width = (v[1] - v[2]) / v[3]
        prev = rows[i-1][1][3]
        flags = {"previous_up": v[3] > prev, "previous_down": v[3] < prev,
                 "wide_range": width > med, "narrow_range": width < med}
        out.append((nxt, flags, int(future[3] > v[3])))
    return out

def evaluate(obs, condition, start, end, plan):
    data = [(d, f[condition], y) for d, f, y in obs if start <= d < end]
    yes = [y for _, flag, y in data if flag]
    no = [y for _, flag, y in data if not flag]
    result = {"condition": condition, "n": len(data), "condition_n": len(yes), "comparison_n": len(no),
              "status": "insufficient_data", "promoted": False}
    if min(len(yes), len(no)) < plan["min_group"]:
        return result
    p, q = st.mean(yes), st.mean(no)
    result.update({"condition_rate": p, "comparison_rate": q, "effect": p-q})
    # Non-overlapping calendar weeks; only weeks with observations in both groups.
    weeks = {}
    for d, flag, y in data:
        year, week, _ = dt.date.fromisoformat(d).isocalendar()
        weeks.setdefault((year, week), {True: [], False: []})[flag].append(y)
    diffs = [st.mean(w[True])-st.mean(w[False]) for w in weeks.values() if w[True] and w[False]]
    result["paired_weeks"] = len(diffs)
    if len(diffs) < plan["min_blocks"]:
        result["status"] = "descriptive_only"
        return result
    alpha = plan["alpha"] / (len(plan["markets"]) * len(plan["conditions"]))
    z = NormalDist().inv_cdf(1-alpha/2)
    effect = st.mean(diffs)
    se = st.stdev(diffs) / math.sqrt(len(diffs))
    lo, hi = effect-z*se, effect+z*se
    result.update({"weekly_effect": effect, "approx_interval": [max(-1,lo), min(1,hi)],
                   "family_adjusted_alpha": alpha,
                   "status": "candidate_for_review" if se > 0 and (lo>0 or hi<0) else "inconclusive"})
    return result

def run(plan, datasets, today, previous=None):
    if set(plan["conditions"]) - CONDITIONS or len(set(plan["conditions"])) != len(plan["conditions"]):
        raise ValueError("Invalid registered conditions")
    if len(set(plan["markets"])) != len(plan["markets"]):
        raise ValueError("Duplicate markets")
    if dt.date.fromisoformat(plan["prospective_start"]) <= dt.date.fromisoformat(plan["registered_at"]):
        raise ValueError("Prospective data must begin after registration")
    h = digest(plan)
    out = previous if previous is not None else {"version": 1, "plan_hash": h, "batches": []}
    if out["plan_hash"] != h:
        raise ValueError("Registered plan changed: create a new version and preserve prior results")
    done = {(b["kind"], b["start"], b["end"]) for b in out["batches"]}
    for kind, start, end in periods(plan, today):
        if (kind,start,end) in done:
            continue
        # Wait until all providers have data past the evaluation end; do not freeze a partial period.
        if any(not datasets.get(m) or datasets[m][-1][0] < end for m in plan["markets"]):
            continue
        results, hashes = [], {}
        for market in plan["markets"]:
            rows = [(d,v) for d,v in datasets[market] if d < end]
            # Require sufficient historical coverage; missing provider days remain a documented limitation.
            obs = observations(rows)
            hashes[market] = digest(rows)
            for condition in plan["conditions"]:
                r = evaluate(obs,condition,start,end,plan)
                if kind == "historical" and r["status"] == "candidate_for_review":
                    r["status"] = "exploratory_candidate"
                r["market"] = market
                results.append(r)
        out["batches"].append({"kind":kind,"start":start,"end":end,"dataset_hashes":hashes,
                               "computed_on":today.isoformat(),"results":results,"policy":plan["policy"]})
    return out

def main():
    import bias
    plan = json.loads(PLAN.read_text())
    now = dt.datetime.now(dt.timezone.utc)
    datasets = {m: bias.clean(m, bias.finished(bias.load_cache(m)["days"], now.astimezone(bias.NY)))
                for m in plan["markets"]}
    previous = json.loads(OUT.read_text()) if OUT.exists() else None
    out = run(plan,datasets,now.astimezone(bias.NY).date(),previous)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out,indent=2,allow_nan=False))
    os.replace(tmp,OUT)
    print("discovery:",len(out["batches"]),"frozen batches")

if __name__ == "__main__":
    main()
