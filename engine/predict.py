"""News-outcome engine v4: how gold, the Nasdaq-100, the dollar and the 2-year yield react to US data surprises.

Runs after engine.py in GitHub Actions and publishes site/data/direction/current.json for the News calendar.

  tv.py        consensus forecasts and first-reported figures since 2010 (TradingView, free)
  bars.py      hourly gold and Nasdaq-100 futures bars, archived since mid-2024 (Yahoo, free)
  prices.py    daily gold and Nasdaq-100 closes; series_store.py: dollar index and 2-year yield (FRED, free)
  surprise.py  the tested model: per market and theme, first 2 hours and the close
  moves.py     expected size of the day's move

For every upcoming release it publishes the scenario map (above / near / below consensus) and, for rules that
passed every out-of-sample test, a lean for each market. Once a figure is out, it publishes the lean for that
release, logs it in site/data/direction/log.json and scores it when the window closes, so the live record is
public. Everything is historical statistics, not advice. The engine never raises: on any failure the last good
file stays live.
"""
import datetime as dt
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bars  # noqa: E402
import moves as MV  # noqa: E402
import prices  # noqa: E402
import series_store  # noqa: E402
import surprise as SP  # noqa: E402
import tv  # noqa: E402
from catalog import NAMES  # noqa: E402

NY = ZoneInfo("America/New_York")
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
OUT = os.path.join(DATA, "direction", "current.json")
LOG_PATH = os.path.join(DATA, "direction", "log.json")
DUKA_PATH = os.path.join(HERE, "cache", "minutes", "dukascopy.json")
CLOSE = dt.time(16, 0)
SETTLED = dt.time(17, 15)  # gold settles at 17:00 New York, after the stock close
HORIZON_DAYS = 14
DISCLAIMER = ("Historical statistics for education. Past reactions do not guarantee future moves, and nothing "
              "here is a recommendation to buy or sell.")
LOGLINES = []


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOGLINES.append(msg)
    print(msg, flush=True)


def load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, default=str)
        fh.write("\n")
    os.replace(tmp, path)


def now_ny():
    v = os.environ.get("ENGINE_NOW")
    return dt.datetime.fromisoformat(v).astimezone(NY) if v else dt.datetime.now(NY)


# ----------------------------------------------------------------- inputs
def markets_now(now, store=None, log=log):
    """{market key: reaction source} with nothing that hasn't settled yet."""
    today = now.date().isoformat()
    cut = today if now.time() < SETTLED else "9999"
    out = {}
    for a in ("gold", "nq"):
        rows, _ = prices.closes(a, "2009-06-01", now=now.astimezone(dt.timezone.utc), log=log)
        if rows:
            out[a] = SP.Daily([r for r in rows if r[0] < cut], "pct")
    store = store or series_store.Store(now, log=log, cutoff=None if now.time() >= SETTLED else today)
    for key, sid, unit in (("usd", "DTWEXBGS", "pct"), ("y2", "DGS2", "bp")):
        rows = store(sid, "2009-06-01")
        if rows:
            out[key] = SP.Daily([(d, v) for d, v, _ in rows if d < cut], unit)
    bars.sync(now.astimezone(dt.timezone.utc), log=log)
    duka = load(DUKA_PATH, {}).get("markets", {})
    for a in ("gold", "nq"):
        hourly = None
        rows = bars.load(a)
        if rows:
            f = bars.fetched(a)
            hourly = SP.Hourly(rows, min(f.astimezone(NY), now) if f else now)
        f5 = bars.fetched(a, "5m")
        done5 = min(f5.astimezone(NY), now) if f5 else now
        rows5 = bars.load(a, "5m")
        for key, mins in (("15m", 15), ("2h", 120)):
            src = SP.Minutes(mins, duka=duka.get(a), bars5=rows5, complete_before=done5,
                             fallback=hourly if key == "2h" else None)
            out[a + key] = src
    if duka:
        log(f"minutes: Dukascopy history for {', '.join(f'{a} {len(v)}' for a, v in duka.items())} releases")
    return out


def headline(r):
    """The report's main figure (highest weight) with its consensus, for display."""
    comps = sorted(r["comps"], key=lambda c: -c.get("weight", 1))
    c = comps[0] if comps else {}
    return {"title": c.get("title"), "forecast": c.get("forecast"), "actual": c.get("actual"),
            "unit": c.get("unit"), "scale": c.get("scale")}


def match(events, rels, kind_of):
    """{calendar event id: TradingView release} for the same report on the same New York day."""
    by = {}
    for r in rels:
        by.setdefault((r["kind"], r["when"].date().isoformat()), []).append(r)
    out = {}
    for e in events:
        k = kind_of(e)
        cands = by.get((k, e["date"]))
        if not cands:
            continue
        if e.get("time"):
            h, m = map(int, e["time"].split(":"))
            t = h * 60 + m
            cands = sorted(cands, key=lambda r: abs(r["when"].hour * 60 + r["when"].minute - t))
        out[e["id"]] = cands[0]
    return out


# ----------------------------------------------------------------- outputs
def live_calls(model, events, rels, kind_of, now):
    """Pre-release scenarios and post-release leans for calendar events in the window."""
    m = match(events, rels, kind_of)
    out = {}
    for e in events:
        r = m.get(e["id"])
        if not r or r["kind"] not in tv.GROUP_OF:
            continue
        g = r["group"]
        days = (dt.date.fromisoformat(e["date"]) - now.date()).days
        if days < 0 or days > HORIZON_DAYS:
            continue
        head = headline(r)
        base = {"kind": r["kind"], "group": g, "date": e["date"], "when": r["when"].isoformat(), "basis": "consensus",
                "consensus": head}
        if r["z"] is not None and r["when"] <= now:
            if now >= dt.datetime.combine(r["when"].date(), CLOSE, NY):
                continue  # the day's window has closed; the outcome is in the log
            side = "hot" if r["z"] >= SP.BIN else "cool" if r["z"] <= -SP.BIN else "inline"
            calls, hist = {}, {}
            for key in model["markets"]:
                c = SP.call(model, g, key, r["z"])
                h = None if c and c.get("dir") else SP.hist_bias(model, r["kind"], key, side)
                mins = SP.MINUTES.get(SP.MARKETS[key][2])
                if mins and now > r["when"] + dt.timedelta(minutes=mins):
                    c, h = {"none": True, "why": f"the first {SP.MARKETS[key][2]} have passed"}, None
                if c:
                    calls[key] = c
                if h:
                    hist[key] = h
            out[e["id"]] = {**base, "stage": "post", "z": round(r["z"], 2), "bin": side, "calls": calls, "hist": hist}
        elif r["when"] > now:
            out[e["id"]] = {**base, "stage": "pre",
                            "hot": {k: c for k in model["markets"] if (c := SP.call(model, g, k, 1.0))},
                            "cool": {k: c for k in model["markets"] if (c := SP.call(model, g, k, -1.0))},
                            "hist": {side: {k: h for k in model["markets"] if (h := SP.hist_bias(model, r["kind"], k, side))}
                                     for side in ("hot", "inline", "cool")}}
    return out


def log_calls(log_rows, live, now):
    have = {(r["id"], r["asset"]) for r in log_rows}
    for eid, v in live.items():
        if v["stage"] != "post":
            continue
        when = dt.datetime.fromisoformat(v["when"])
        picks = [(a, c, "tested") for a, c in v["calls"].items()] + [(a, h, "hist") for a, h in v.get("hist", {}).items()]
        for a, c, tier in picks:
            if not c.get("dir") or (eid, a) in have:
                continue
            mins = SP.MINUTES.get(SP.MARKETS[a][2])
            if mins and now > when + dt.timedelta(minutes=mins):
                continue
            have.add((eid, a))
            log_rows.append({"id": eid, "date": v["date"], "when": v["when"], "kind": v["kind"], "group": v["group"],
                             "asset": a, "dir": c["dir"], "p": c["p"], "z": v["z"], "tier": tier,
                             "logged": now.isoformat(timespec="minutes")})
    return log_rows


def summary(model, live, record):
    rules, bt_calls, bt_hits = {}, 0, 0
    for g, gm in model["groups"].items():
        for key, s in gm.items():
            bt = s["bt"]
            if s.get("proven"):
                bt_calls += bt["calls"]
                bt_hits += bt["hits"]
            for kind in tv.GROUPS[g]:
                rules[f"{kind}:{key}"] = {"calls": bt["calls"], "hits": bt["hits"], "proven": bool(s.get("proven")),
                                          "why": s.get("why", ""), "brierSkill": bt["brierSkill"], "group": g}
    scen = {}
    for kind, sc in model["scenarios"].items():
        title = next((t for t, _, _ in tv.REPORTS[kind]), kind)
        scen[kind] = {"name": NAMES.get(kind, kind), "metric": title, "n": sc["n"], "since": "2010", "basis": "consensus",
                      "assets": sc["assets"], **({"decision": sc["decision"]} if sc.get("decision") else {})}
    return {"asof": model["asof"], "version": 4, "assets": model["markets"],
            "proven": sum(1 for gm in model["groups"].values() for s in gm.values() if s.get("proven")),
            "rules": rules, "groups": {g: {k: {kk: s[kk] for kk in ("b", "k", "n", "since", "bt", "proven", "why")}
                                           for k, s in gm.items()} for g, gm in model["groups"].items()},
            "backtest": {"calls": bt_calls, "hits": bt_hits}, "live": record, "scenarios": scen,
            "events": live, "disclaimer": DISCLAIMER, "basis": "consensus"}


def check(out):
    """Validate the file before publishing. Returns a list of problems (empty = fine)."""
    bad = []
    ok_dir = {"up", "down"}
    for g, gm in out.get("groups", {}).items():
        for k, s in gm.items():
            if not (0 <= s.get("k", -1) <= 1.5) or not isinstance(s.get("b"), (int, float)) or s["b"] != s["b"]:
                bad.append(f"model {g}/{k}: invalid coefficients")
    for eid, v in out.get("events", {}).items():
        calls = dict(v.get("calls") or {})
        for side in ("hot", "cool"):
            calls.update({f"{side}:{a}": c for a, c in (v.get(side) or {}).items()})
        for a, c in calls.items():
            if c.get("dir") and not (c["dir"] in ok_dir and 0.5 < c.get("p", 0) < 1):
                bad.append(f"call {eid}/{a}: {c}")
        if v.get("z") is not None and not (-10 < v["z"] < 10):
            bad.append(f"surprise {eid}: z={v['z']}")
    for kind, sc in out.get("scenarios", {}).items():
        for a, cells in sc.get("assets", {}).items():
            for b, c in cells.items():
                if not (0 <= c.get("up", -1) <= 1) or c.get("n", 0) < 1:
                    bad.append(f"scenario {kind}/{a}/{b}: {c}")
    if not out.get("assets"):
        bad.append("no markets")
    return bad


def run(now=None, kind_of=None, events=None, store=None):
    now = now or now_ny()
    if kind_of is None:
        import engine as E  # calendar helpers; importing does not run the engine
        kind_of = E.kind_of
    if events is None:
        events = load(os.path.join(DATA, "calendar", "events.json"), {"events": []}).get("events", [])
    got = tv.sync(now.date(), log=log)
    rels = tv.releases()
    log(f"tv: {got} month(s) refreshed, {sum(1 for r in rels if r['z'] is not None)} releases with a consensus surprise")
    markets = markets_now(now, store=store)
    log("markets: " + ", ".join(f"{k}" for k in markets))
    log_doc = load(LOG_PATH, {"rows": []})
    log_rows = [r for r in log_doc.get("rows", []) if "when" in r]  # rows from the old model are retired
    t0 = dt.datetime.now()
    model = SP.fit(rels, markets, now, live_rows=[r for r in log_rows if "hit" in r])
    log(f"model: fit in {(dt.datetime.now() - t0).seconds}s; proven: "
        + ", ".join(f"{g}:{k}" for g, gm in model["groups"].items() for k, s in gm.items() if s.get("proven")))
    live = live_calls(model, events, rels, kind_of, now)
    try:
        days = {}
        for r in rels:
            if r["z"] is not None:
                days.setdefault(r["kind"], []).append(r["when"].date().isoformat())
        cut = now.date().isoformat() if now.time() < SETTLED else "9999"
        rows = {a: [r for r in prices.ranges(a, "2007-01-01") if r[0] < cut] for a in ("gold", "nq")}
        mv = MV.fit({a: r for a, r in rows.items() if r}, days, now.date())
        for v in live.values():
            v["move"] = MV.for_event(mv, v["kind"])
    except Exception as ex:
        mv = {}
        log(f"moves: failed ({ex!r}); expected moves omitted this run")
    log_calls(log_rows, live, now)
    record = SP.score(log_rows, markets, now)
    out = summary(model, live, record)
    out["moves"] = mv
    problems = check(out)
    if problems:
        log(f"quality: {len(problems)} problem(s); keeping the last good file: " + "; ".join(problems[:5]))
        with open(os.path.join(HERE, "QUALITY_FAIL"), "a") as fh:
            fh.write("\nNews-outcome model output failed its checks (last good file kept):\n")
            fh.writelines(f"- {p}\n" for p in problems[:20])
        return None
    out["log"] = LOGLINES[-20:]
    save(LOG_PATH, {"version": 4, "rows": log_rows[-3000:]})
    save(OUT, out)
    log(f"published {len(live)} release(s), {out['proven']} proven rule(s), live record {record['hits']}/{record['calls']}")
    return out


def main():
    rc = 0
    try:
        run()
    except Exception:
        log("model: unexpected error; the last good file stays live")
        traceback.print_exc()
        rc = 1                                   # reported by engine/guard.py; the publish job carries on
    try:
        bars.export(DATA, log=log)  # real NQ bars for the site's MNQ backtester
    except Exception as e:
        log(f"bars: could not publish bars for the backtester ({e!r})")
        rc = rc or 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
