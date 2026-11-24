"""Discovery v3 (research/discovery-plan-v3.json): the corrected estimator and a fair range baseline.

v1 and v2 compared conditional rates inside each week and averaged the differences. When the condition is built
from the previous outcome ("previous up"), that is biased toward reversal: on independent coin flips it flags
"previous up" every time (validation.null_control). v3 uses validation.marginal: the overall difference in rates,
with standard errors clustered on 28-day blocks, Bonferroni over all 128 tests. The range outcome asks whether
tomorrow's range beats a normal day's (the median of the 20 ranges up to today), not today's own range.

The 2020-2026 history was seen before registration, so it is published as description only. From 1 Dec 2026 the
prospective sample grows; each 1 December a cumulative snapshot is computed and frozen. A test can be a candidate only
once that sample has 30 blocks (late March 2029). Nothing is promoted automatically, and v1/v2 files stay as they are.
"""
import datetime as dt
import json
import os
import statistics as st
from pathlib import Path

import validation as VA

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "research/discovery-plan-v3.json"
OUT = ROOT / "site/data/research/discovery-v3.json"


def digest(x):
    return VA.digest(x)


def sample(rows):
    """[(next session date, flags, outcomes, open-to-close bp)] using only candles up to today for the flags."""
    out = []
    for i in range(20, len(rows) - 1):
        hist = rows[i - 20:i + 1]
        nxt, f = rows[i + 1]
        dates = [dt.date.fromisoformat(d) for d, _ in hist] + [dt.date.fromisoformat(nxt)]
        if any(not 1 <= (b - a).days <= 4 for a, b in zip(dates, dates[1:])):
            continue
        vals = [v for _, v in hist]
        v, prev = vals[-1], vals[-2]
        if not v[1] > v[2]:
            continue
        width = (v[1] - v[2]) / v[3]
        normal_before = st.median((x[1] - x[2]) / x[3] for x in vals[:-1])        # the 20 days before today
        normal_now = st.median((x[1] - x[2]) / x[3] for x in vals[1:])            # the 20 days up to today
        loc = (v[3] - v[2]) / (v[1] - v[2])
        flags = {"previous_up": v[3] > prev[3], "wide_range": width > normal_before,
                 "momentum_5_up": v[3] > vals[-6][3], "momentum_20_up": v[3] > vals[0][3],
                 "close_near_high": loc >= .8, "close_near_low": loc <= .2,
                 "inside_day": v[1] < prev[1] and v[2] > prev[2], "outside_day": v[1] > prev[1] and v[2] < prev[2]}
        y = {"next_positive_close": int(f[3] > v[3]),
             "next_range_above_normal": int((f[1] - f[2]) / f[3] > normal_now)}
        out.append((nxt, flags, y, 10000 * (f[3] / f[0] - 1)))
    return out


def windows(plan, today):
    """('historical', start, end) and the cumulative prospective snapshots due by today (each 1 December)."""
    yield "historical", plan["historical"]["start"], plan["historical"]["end"]
    start = dt.date.fromisoformat(plan["prospective_start"])
    end = dt.date(start.year + 1, 12, 1)
    while end <= today:
        yield "prospective", start.isoformat(), end.isoformat()
        end = dt.date(end.year + 1, 12, 1)


def run(plan, datasets, today, previous=None):
    if plan.get("version") != 3 or len(set(plan["conditions"])) != len(plan["conditions"]):
        raise ValueError("Not the registered v3 plan")
    h = digest(plan)
    out = previous if previous is not None else {"version": 3, "plan_hash": h, "batches": []}
    if out["plan_hash"] != h:
        raise ValueError("Registered plan changed; register a new version")
    n_tests = len(plan["markets"]) * len(plan["conditions"]) * len(plan["outcomes"])
    alpha = plan["alpha"] / n_tests
    done = {(b["kind"], b["start"], b["end"]) for b in out["batches"]}
    for kind, start, end in windows(plan, today):
        if (kind, start, end) in done:
            continue
        if any(not datasets.get(m) or datasets[m][-1][0] < end for m in plan["markets"]):
            continue                                       # never freeze a period before every market has its data
        results, hashes = [], {}
        for market in plan["markets"]:
            rows = [(d, v) for d, v in datasets[market] if d < end]
            hashes[market] = digest(rows)
            obs = [r for r in sample(rows) if start <= r[0] < end]
            for condition in plan["conditions"]:
                for outcome in plan["outcomes"]:
                    r = VA.marginal(obs, condition, outcome, plan, alpha)
                    if r["status"] == "marginal_candidate":
                        r["status"] = "descriptive_difference" if kind == "historical" else "candidate_for_review"
                    if outcome == "next_range_above_normal":
                        r["note"] = "Range persistence (volatility clustering) is a known effect, not a direction edge."
                    r.update(market=market, condition=condition, outcome=outcome, promoted=False)
                    results.append(r)
        out["batches"].append({"kind": kind, "start": start, "end": end, "computed_on": today.isoformat(),
                               "tests": n_tests, "family_alpha": alpha, "dataset_hashes": hashes, "results": results,
                               "evidence": "descriptive only: seen before registration" if kind == "historical"
                               else "prospective, cumulative from " + plan["prospective_start"]})
    return out


def main():
    import bias
    now = dt.datetime.now(dt.timezone.utc).astimezone(bias.NY)
    plan = json.loads(PLAN.read_text())
    datasets = {m: bias.clean(m, bias.finished(bias.load_cache(m)["days"], now)) for m in plan["markets"]}
    previous = json.loads(OUT.read_text()) if OUT.exists() else None
    out = run(plan, datasets, now.date(), previous)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, indent=2, allow_nan=False))
    os.replace(tmp, OUT)
    print("discovery v3:", len(out["batches"]), "frozen batches")


if __name__ == "__main__":
    main()
