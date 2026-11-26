"""The final check before anything is published, after every engine has run.

    python engine/gate.py            validate the outputs; put back the last good version of any that fail
    python engine/gate.py --report   at the end of the run: summary, and a red job if any step failed

What it checks (site/data):
  - every JSON file parses (a half-written file never reaches the site);
  - the daily bias (bias/current.json): probabilities between 0 and 1, an expected range that is a real
    high-minus-low (not below zero, low <= typical <= high), each day's high at or above its low, finite numbers;
  - the forecast log (bias/log.json): every entry not marked void passes the same forecast checks, and no market has
    two entries for one candle.
A file that fails is restored from the last commit (the last good publication) and the failure is recorded in
site/data/engine/health.json, so the site never shows an invalid result and the run says what went wrong.
"""
import glob
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
sys.path.insert(0, HERE)
import guard as G  # noqa: E402


def finite(o, path="$"):
    """Paths of any NaN or infinite numbers inside o."""
    if isinstance(o, float) and not math.isfinite(o):
        return [path]
    if isinstance(o, dict):
        return [p for k, v in o.items() for p in finite(v, f"{path}.{k}")]
    if isinstance(o, list):
        return [p for i, v in enumerate(o) for p in finite(v, f"{path}[{i}]")]
    return []


def prob(v):
    return type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1


def check_bias(doc):
    bad = finite(doc)[:5]
    for m, v in (doc.get("markets") or {}).items():
        for k in ("p_up", "base_up"):
            if not prob(v.get(k)):
                bad.append(f"{m}.{k} = {v.get(k)} is not a probability")
        for side, t in (v.get("takes") or {}).items():
            if not prob(t.get("p")):
                bad.append(f"{m}.takes.{side}.p = {t.get('p')} is not a probability")
        r = v.get("range") or {}
        lo, pt, hi = r.get("lo"), r.get("points"), r.get("hi")
        if None in (lo, pt, hi) or not (0 <= lo <= pt <= hi):
            bad.append(f"{m}.range {lo} / {pt} / {hi} is not a valid high-minus-low range")
        lv = v.get("levels") or {}
        if lv and not lv.get("high", 0) >= lv.get("low", 0):
            bad.append(f"{m}.levels high {lv.get('high')} is below low {lv.get('low')}")
    return bad


def check_log(doc):
    import bias as B
    bad, seen = [], set()
    for e in doc.get("entries", []):
        key = (e.get("market"), e.get("candle"))
        if key in seen:
            bad.append(f"duplicate forecast {key}")
        seen.add(key)
        if not e.get("void"):
            bad += [f"{key}: {p}" for p in B.problems(e)]
    return bad


def forecast_view_errors(data):
    """Check the served forecast against the ledger and its shareable brief."""
    from pathlib import Path
    import publication as P

    root = Path(data)
    bias = json.loads((root / "bias/current.json").read_text(encoding="utf-8"))
    markets = bias["markets"]
    entries = json.loads((root / "bias/log.json").read_text(encoding="utf-8"))["entries"]
    rows = {(row["market"], row["candle"]): row for row in entries}
    errors = []
    for market, view in markets.items():
        row = rows.get((market, view["candle"]))
        if (not row or not P.matches(row, view) or view.get("forecast_at") != row["logged"] or
                view.get("forecast_id") != P.identity(row)):
            errors.append(f"{market} outlook differs from its forecast ledger record")
    nq = markets.get("nq")
    if nq:
        day = nq["session"]["date"]
        brief_dir = root / "briefs/mnq"
        for path in (brief_dir / f"{day}.json", brief_dir / "latest.json"):
            brief = json.loads(path.read_text(encoding="utf-8"))
            if (brief["date"] != day or brief["asof"] != nq["forecast_at"] or
                    brief.get("forecast_id") != nq["forecast_id"] or
                    any(brief["range"][key] != nq["range"][key] for key in ("points", "lo", "hi")) or
                    any(brief["levels"][side] != {"price": nq["levels"][side], "probability": nq["takes"][side]["p"]}
                        for side in ("high", "low")) or
                    any(brief["session"][key] != nq["session"][key] for key in ("open", "close", "halts"))):
                errors.append(f"{path.name} differs from the published NQ forecast")
    return errors


CHECKS = {os.path.join("bias", "current.json"): check_bias, os.path.join("bias", "log.json"): check_log}

# Minimum public contracts. Additional fields remain backward-compatible.
CONTRACTS = {
    "bias/current.json": {"markets": dict, "asof": str, "for": str},
    "bias/log.json": {"entries": list},
    "bars/nq-1h.json": {"rows": list, "market": str, "interval": str},
    "bars/nq-5m.json": {"rows": list, "market": str, "interval": str},
    "research/discovery.json": {"version": int, "batches": list, "plan_hash": str},
    "research/discovery-v2.json": {"version": int, "batches": list, "plan_hash": str},
    "research/discovery-v3.json": {"version": int, "batches": list, "plan_hash": str},
    "macro/current.json": {"version": int, "asof": str, "indices": list, "policy": str},
    "validation/models.json": {"version": int, "asof": str, "plan_hash": str, "markets": dict, "events": list, "policy": str},
    "validation/current.json": {"version": int, "asof": str, "batches": list, "plan_hash": str, "discovery_plan_hash": str, "policy": str},
    "atlas/current.json": {"version": int, "asof": str, "years": list, "countries": list, "indicators": list, "coverage": dict, "plan_hash": str, "policy": str},
    "publications/index.json": {"version": int, "reports": list},
    "open/current.json": {"version": int, "asof": str, "forecast_counts": dict, "forecasts": list, "by_market": dict, "corrections": list, "research": list, "models": list},
    "relationships/current.json": {"version": int, "asof": str, "series": list, "pairs": list, "plan_hash": str, "policy": str},
    "signals/current.json": {"version": int, "asof": str, "states": list, "events": list, "plan_hash": str, "policy": str},
    "direction/current.json": {"assets": dict, "groups": dict, "events": dict, "live": dict, "scenarios": dict},
    "direction/log.json": {"rows": list},
    "calendar/events.json": {"updated": str, "through": str, "events": list},
    "smt/current.json": {"version": int, "asof": str, "timeframes": dict, "policy": str},
    "calendar/earnings.json": {"updated": str, "events": list},
    "brief/morning.json": {"editions": list}, "brief/today.json": {"asof": str, "today": list, "recent": list},
    "engine/status.json": {"lastRun": str, "quality": dict, "sources": dict},
    "engine/quality.json": {"critical": int, "failures": list},
    "engine/health.json": {"components": dict, "updated": str},
    "fed/current.json": {"asof": str}, "history/main.json": {"series": dict},
    "history/reactions.json": {"series": dict}, "markets/latest.json": {"tiles": dict},
    "news/latest.json": {"items": list, "sourceHealth": dict},
    "outlook/current.json": {"days": list}, "config/site.json": {"proOpen": bool},
}

def strict_validate(data=DATA):
    """Fail closed on the whole candidate snapshot, never restore from unverified HEAD."""
    failures = {}
    for rel, fields in CONTRACTS.items():
        path = os.path.join(data, rel)
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
            if not isinstance(obj, dict):
                raise ValueError("expected object")
            bad = [k for k, t in fields.items() if type(obj.get(k)) is not t]
            if bad:
                failures[rel] = ["missing or wrong type: " + ", ".join(bad)]
            elif rel == "engine/quality.json" and obj["critical"]:
                failures[rel] = ["critical source quality failure"]
            elif rel == "validation/models.json":
                import modelaudit
                problems = modelaudit.check(obj, json.loads(modelaudit.PLAN.read_text()))
                if problems:
                    failures[rel] = problems
            elif rel == "validation/current.json":
                import validation
                problems = validation.check(obj, validation.load(validation.PLAN), validation.load(validation.DISCOVERY))
                if problems:
                    failures[rel] = problems
            elif rel == "atlas/current.json":
                import atlas
                problems = atlas.check(obj, atlas.load(atlas.PLAN))
                if problems:
                    failures[rel] = problems
            elif rel == "publications/index.json":
                import publisher
                problems = publisher.check(publisher.Path(data))
                if problems:
                    failures[rel] = problems
            elif rel == "open/current.json":
                import evidence
                problems = evidence.check(obj)
                if problems:
                    failures[rel] = problems
            elif rel == "relationships/current.json":
                import relationships
                problems = relationships.check(obj, json.loads(relationships.PLAN.read_text()))
                if problems:
                    failures[rel] = problems
            elif rel == "smt/current.json":
                import smt
                problems = smt.check(obj)
                if problems:
                    failures[rel] = problems
            elif rel == "signals/current.json":
                import signals
                problems = signals.check(obj, json.loads(signals.PLAN.read_text()))
                if problems:
                    failures[rel] = problems
            elif rel == "macro/current.json":
                ids = [i["id"] for i in obj["indices"]]
                if len(ids) != 6 or len(set(ids)) != 6 or any(
                    (i["score"] is not None and not (type(i["score"]) in (int,float) and 0 <= i["score"] <= 100))
                    or (i["status"] == "available") != (i["score"] is not None)
                    for i in obj["indices"]):
                    failures[rel] = ["invalid index score or state"]
            elif rel == "research/discovery-v2.json":
                if any(len(b["results"]) != 192 or any(r["promoted"] is not False for r in b["results"]) for b in obj["batches"]):
                    failures[rel] = ["incomplete experiment family or unapproved promotion"]
            elif rel == "direction/current.json":
                import predict
                problems = predict.check(obj)
                if obj.get("qualification") != "suspended_pending_validation" or obj.get("proven") != 0 or any(s.get("proven") for g in obj["groups"].values() for s in g.values()):
                    problems.append("unapproved event qualification")
                if problems:
                    failures[rel] = problems
            elif rel == "direction/log.json":
                seen = set()
                for row in obj["rows"]:
                    key = (row["id"], row["asset"])
                    if key in seen or not prob(row["p"]) or row.get("eligible") is not False:
                        failures[rel] = ["duplicate, invalid or unclassified event record"]
                    seen.add(key)
            elif rel == "bias/log.json":
                if any(type(row.get("eligible")) is not bool for row in obj["entries"]):
                    failures[rel] = ["forecast eligibility must be explicit"]
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            failures[rel] = [str(exc)]
    for path in sorted(glob.glob(os.path.join(data, "**", "*.json"), recursive=True)):
        local_rel = os.path.relpath(path, data)
        rel = local_rel.replace(os.sep, "/")
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
            bad = finite(obj)
            if local_rel in CHECKS:
                bad += CHECKS[local_rel](obj)
            if bad:
                failures.setdefault(rel, []).extend(bad[:10])
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            failures[rel] = [str(exc)]
    try:
        bad = forecast_view_errors(data)
        if bad:
            failures["forecast views"] = bad
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        failures["forecast views"] = [str(exc)]
    return failures

def strict_main():
    failures = strict_validate()
    health = G.load().get("components", {})
    failed = [name for name, row in health.items()
              if row.get("run") == G.run_id() and row.get("state") == "failed"]
    if failed:
        failures["engine failures"] = failed
    G.mark("gate", "failed" if failures else "ok", json.dumps(failures)[:1400])
    print(json.dumps(failures, indent=2))
    return 1 if failures else 0


def restore(path):
    """Put back the last committed version of a file (the last good publication); False if there is none."""
    rel = os.path.relpath(path, ROOT)
    r = subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def validate(data=DATA, fix=True):
    failures = {}
    for tmp in glob.glob(os.path.join(data, "**", "*.tmp"), recursive=True):
        os.remove(tmp)                          # left by a write that crashed half-way; never published
    for path in sorted(glob.glob(os.path.join(data, "**", "*.json"), recursive=True)):
        rel = os.path.relpath(path, data)
        if rel == os.path.join("engine", "health.json"):
            continue
        try:
            doc = json.load(open(path))
        except ValueError as e:
            failures[rel] = [f"not valid JSON ({e})"]
            continue
        check = CHECKS.get(rel)
        if check:
            bad = check(doc)
            if bad:
                failures[rel] = bad
    for rel, bad in failures.items():
        put_back = fix and restore(os.path.join(data, rel))
        G.mark(f"output:{rel}", "failed", ("restored the last good version. " if put_back else "could not restore. ")
               + "; ".join(bad[:8]))
        print(f"gate: {rel} FAILED ({'restored' if put_back else 'not restored'}): {'; '.join(bad[:3])}")
    G.mark("gate", "ok" if not failures else "failed", f"{len(failures)} output(s) failed" if failures else "")
    print(f"gate: {len(failures)} invalid output(s)")
    return failures


def report():
    doc = G.load()
    rows = [(n, c) for n, c in sorted(doc.get("components", {}).items()) if c.get("run") == G.run_id()]
    failed = [n for n, c in rows if c["state"] == "failed"]
    lines = ["| Step | State | Seconds | Note |", "| --- | --- | --- | --- |"] + \
            [f"| {n} | {c['state']} | {c.get('seconds') or ''} | {(c.get('note') or '').splitlines()[-1][:120] if c.get('note') else ''} |"
             for n, c in rows]
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a") as fh:
            fh.write("## Engine health\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))
    if failed:
        print(f"::error::{len(failed)} step(s) failed: {', '.join(failed)}. The site kept the last good files.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(report() if "--report" in sys.argv else strict_main() if "--strict" in sys.argv else (1 if validate() else 0))
