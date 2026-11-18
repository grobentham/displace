"""News-outcome engine: how gold, the Nasdaq-100 and other markets have closed after each US release.

Runs after engine.py in GitHub Actions. Uses direction.py (the tested model) and publishes
site/data/direction/current.json, which the News calendar reads.

For every upcoming high-impact release it publishes
  - a scenario map: if the figure comes in hotter, in line or cooler than expected, how often each market
    closed higher that day and the typical size of the move (the historical record, for every release);
  - a lean, only for release x market rules that passed every out-of-sample test in direction.py.
After a release, it publishes the lean for that day's close (before the close only), logs it in
site/data/direction/log.json and scores it against the actual close, so the live record is public.

Everything is historical statistics, not advice. The engine never raises: if anything fails, the last good
file stays live and the reason is written to the log.
"""
import datetime as dt
import hashlib
import json
import os
import sys
import traceback
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import direction as D  # noqa: E402
import moves as MV  # noqa: E402
import nowcast  # noqa: E402
import prices  # noqa: E402
import quality as qa  # noqa: E402
import series_store  # noqa: E402
from catalog import NAMES, RELEASES  # noqa: E402

NY = ZoneInfo("America/New_York")
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
OUT = os.path.join(DATA, "direction", "current.json")
LOG_PATH = os.path.join(DATA, "direction", "log.json")
MODEL_PATH = os.path.join(HERE, "cache", "direction", "model.json")
CLOSE = dt.time(16, 0)
SETTLED = dt.time(17, 15)  # gold settles at 17:00 NY, after the stock close
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
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def now_ny():
    v = os.environ.get("ENGINE_NOW")
    return dt.datetime.fromisoformat(v).astimezone(NY) if v else dt.datetime.now(NY)


def kind_for(kind_of):
    def k(e):
        kind = kind_of(e)
        if kind == "gdp" and series_store.event_period("gdp", e, lambda *_: dt.date(2000, 1, 1)) is None:
            return None  # second and third GDP estimates are revisions; the model only knows first releases
        return kind
    return k


def fingerprint(paths):
    """Hash of the data itself (not fetch timestamps), so a refresh that brings nothing new doesn't refit."""
    h = hashlib.sha256()
    for p in sorted(paths):
        c = load(p, {})
        h.update(os.path.basename(p).encode())
        h.update(json.dumps(c.get("rows", c.get("closes", c.get("past"))), sort_keys=True).encode())
    return h.hexdigest()[:16]


def input_files():
    out = []
    for base in (series_store.CACHE_DIR, prices.CACHE_DIR):
        if os.path.isdir(base):
            out += [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".json")]
    return out + [nowcast.CACHE]


def release_close(e):
    return dt.datetime.combine(dt.date.fromisoformat(e["date"]), CLOSE, NY)


def release_time(e):
    h, m = map(int, (e.get("time") or "00:00").split(":"))
    return dt.datetime.combine(dt.date.fromisoformat(e["date"]), dt.time(h, m), NY)


def live_window(live, events, now):
    """Post-release leans are only meaningful between the release and that day's close."""
    by_id = {e["id"]: e for e in events}
    out = {}
    for eid, v in live.items():
        e = by_id.get(eid)
        if v["stage"] == "post" and (not e or not (release_time(e) <= now < release_close(e))):
            continue
        out[eid] = v
    return out


def scenarios(model):
    """Historical record by surprise bucket for every release x market (proven or not)."""
    out = {}
    for k, km in model.get("kinds", {}).items():
        out[k] = {"name": NAMES.get(k, k), "metric": km["metric"], "n": km["n"], "since": km["since"],
                  "basis": km.get("basis", "trend"), "assets": {}}
        for a, m in km["assets"].items():
            out[k]["assets"][a] = {b: {"n": c["n"], "up": c["pUp"], "med": c["med"], "q1": c["q1"], "q3": c["q3"]}
                                   for b, c in m["cells"].items() if c["n"]}
    return out


def expectations(events, kind_of, title_period, log=log):
    """Cleveland Fed nowcasts as the expected core CPI / core PCE: past releases for training, upcoming ones
    from the latest nowcast for that month. Kinds with too little nowcast history stay on the trend basis."""
    past, latest = nowcast.load(log=log)
    records = dict(past)
    for e in events:
        k = kind_of(e)
        if k in ("cpi", "pce") and (k, e["date"]) not in records:
            # upcoming, or released before the Cleveland Fed marked it: the latest nowcast for that month
            per = title_period(e, k)
            if per and (k, per.strftime("%Y-%m")) in latest:
                records[(k, e["date"])] = latest[(k, per.strftime("%Y-%m"))]
    D.BASIS.clear()
    for k in ("cpi", "pce"):
        if sum(1 for kk, _ in past if kk == k) >= 60:
            D.BASIS[k] = "nowcast"
    return records


def release_days():
    """{kind: [release dates]} from the first-release history (the date each figure was published)."""
    out = {}
    for k, cfg in D.MODELS.items():
        rows = series_store.load(cfg["head"][0], True)["rows"]
        out[k] = sorted({r[2] for r in rows if r[2]})
    return out


def summary(model, live, log_rows, px, now):
    rules, bt_calls, bt_hits = {}, 0, 0
    for k, km in model.get("kinds", {}).items():
        for a, m in km["assets"].items():
            bt = m["bt"]
            rules[f"{k}:{a}"] = {"calls": bt["calls"], "hits": bt["hits"], "proven": bool(bt.get("proven")),
                                 "why": bt.get("why", ""), "brierSkill": bt["brierSkill"], "reliability": bt["reliability"]}
            if bt.get("proven"):
                bt_calls += bt["calls"]
                bt_hits += bt["hits"]
    rec = D.score(log_rows, px)
    return {"asof": now.isoformat(timespec="minutes"), "modelAsof": model.get("asof"), "version": 2,
            "assets": model.get("assets", {}), "regime": model.get("regime", {}), "sources": model.get("sources", {}),
            "proven": sum(1 for r in rules.values() if r["proven"]), "rules": rules,
            "backtest": {"calls": bt_calls, "hits": bt_hits}, "live": rec, "scenarios": scenarios(model),
            "events": live, "disclaimer": DISCLAIMER}


def run(now=None, source=None, budget=series_store.BUDGET_SECONDS):
    import engine as E  # calendar helpers (kind_of, title_period); importing does not run the engine
    now = now or now_ny()
    today = now.date()
    store = series_store.Store(now, series_store.model_modes(D.MODELS), log=log, source=source, budget=budget,
                               cutoff=None if now.time() >= SETTLED else today.isoformat())
    kind_of = kind_for(E.kind_of)
    cal = load(os.path.join(DATA, "calendar", "events.json"), {"events": []})
    events = cal.get("events", [])

    settled = today.isoformat()

    def closed_only(got):
        """Drop today's bar until every market has closed, so a partial day never trains or scores a call."""
        rows, src = got
        if rows and now.time() < SETTLED:
            rows = [r for r in rows if r[0] < settled]
        return (rows, src) if rows else (None, "")
    price_fns = {a: (lambda s, a=a: closed_only(prices.closes(a, s, now=now.astimezone(dt.timezone.utc), log=log)))
                 for a in ("gold", "nq")}
    log_rows = load(LOG_PATH, {"rows": []}).get("rows", [])
    cached = load(MODEL_PATH, {})
    # Touch every input once so caches refresh, then refit only when something changed or the model is a day old.
    model, px = None, {}
    fp_before = fingerprint(input_files())
    # most-traded releases first, so they are ready first while the history loads over the first runs
    store("DFF", "2008-01-01")
    order = [k for k in ("cpi", "nfp", "pce", "retail", "ppi", "gdp", "claims") if k in D.MODELS]
    order += [k for k in D.MODELS if k not in order]
    for k in order:
        cfg = D.MODELS[k]
        for sid in [cfg["head"][0]] + [c[0] for c in cfg["comps"]]:
            store(sid, "2008-01-01", initial=True)
    added = series_store.extend_from_events(events, D.MODELS, RELEASES, kind_of, E.title_period, D.figure, log=log)
    if added:
        log(f"history: appended {added} confirmed figure(s) from the calendar")
    records = expectations(events, kind_of, E.title_period)
    fp = fingerprint(input_files())
    refit = (not cached.get("model") or cached.get("fingerprint") != fp or cached.get("day") != today.isoformat())
    if refit:
        log("direction: fitting (inputs changed)" if cached.get("model") else "direction: first fit")
        t0 = dt.datetime.now()
        # Core CPI and core PCE surprises are measured against the Cleveland Fed nowcast (history since 2013),
        # the other releases against their recent trend; the same basis is used live.
        model, px = D.fit(store, None, records, today, log=log,
                          live_rows=[r for r in log_rows if "hit" in r], price_fns=price_fns)
        log(f"direction: fit took {(dt.datetime.now() - t0).seconds}s")
        if model and model.get("kinds"):
            save(MODEL_PATH, {"fingerprint": fingerprint(input_files()), "day": today.isoformat(), "model": model})
        else:
            model = cached.get("model")
            log("direction: fit produced no model; keeping the last good model")
    else:
        model = cached["model"]
    if not px:
        for a, (series, unit, name, _) in D.ASSETS.items():
            rows = price_fns[a](D.START)[0] if a in price_fns else [(d, v) for d, v, _ in (store(series, D.START) or [])]
            if rows and len(rows) > 250:
                px[a] = D.Px(rows, unit)
    if not model or not model.get("kinds"):
        log("direction: no model yet; the release history is still loading from ALFRED (a few runs)")
        return False
    if fp_before != fp:
        log("direction: history or prices updated this run")

    live = live_window(D.apply(model, events, kind_of, today, records=records), events, now)
    # expected move size for gold and the Nasdaq-100 on each release day
    mv = {}
    try:
        cut = today.isoformat() if now.time() < SETTLED else "9999"
        rows = {a: [r for r in prices.ranges(a, "2007-01-01") if r[0] < cut] for a in ("gold", "nq")}
        mv = MV.fit({a: r for a, r in rows.items() if r}, release_days(), today)
        for v in live.values():
            v["move"] = MV.for_event(mv, v["kind"])
    except Exception as ex:
        log(f"moves: failed ({ex!r}); expected moves omitted this run")
    D.log_calls(log_rows, {k: v for k, v in live.items() if v["stage"] == "post"})
    QA = qa.Report()
    ok = D.check(QA, model, live)
    if not ok:
        log("direction: quality checks failed; keeping the last good file")
        with open(os.path.join(HERE, "QUALITY_FAIL"), "a") as fh:
            fh.write("\nDirection engine checks failed:\n")
            for c in QA.critical_fail[:10]:
                fh.write(f"- {c['name']}: {c['detail']}\n")
        return False
    out = summary(model, live, log_rows, px, now)
    out["moves"] = mv
    out["basis"] = dict(D.BASIS)
    out["loading"] = sorted(store.loading)
    out["log"] = LOGLINES[-20:]
    save(LOG_PATH, {"rows": log_rows[-2000:]})
    save(OUT, out)
    log(f"direction: published {len(live)} release(s), {out['proven']} proven rule(s), "
        f"live record {out['live']['hits']}/{out['live']['calls']}")
    return True


def main():
    try:
        run()
    except Exception:
        log("direction: unexpected error; the last good file stays live")
        traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
