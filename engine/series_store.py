"""Cached history for the direction engine.

Two kinds of series are kept in engine/cache/series/ (committed by the workflow):

  <ID>.initial.json   every period as FIRST published, with the date it was published
                      ([period, value, release date]). This is what a trader saw on release day, so the model
                      never learns from later revisions.
  <ID>.json           daily market series ([date, value, ""]): fed funds, yields, dollar.

Where the data comes from, best first:
  1. The official FRED/ALFRED API, when the FRED_API_KEY secret is set (free key). Refreshed weekly for
     release series and every few hours for market series.
  2. Keyless fallbacks for market series: Treasury yield curve (DGS2, DGS10) and the New York Fed (DFF).
  3. For release series, the engine's own calendar: every confirmed figure the engine publishes is appended,
     so once the history has been loaded once, it stays current without FRED. A figure is only appended when
     it is for exactly the next period, so a missed release can never shift the history out of line.
"""
import datetime as dt
import json
import os

import agencies
import fredapi

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache", "series")
FETCH_FROM = "2007-01-01"
INITIAL_REFRESH = dt.timedelta(days=6)
DAILY_REFRESH = dt.timedelta(hours=4)

# catalog transform -> multiplier turning the published figure into the FRED series' own units
UNITS = {"pct": 1, "pctlevel": 1, "level1": 1, "rate": 1, "claims": 1, "claimsM": 1, "diffPersons": 1,
         "diff": 1e-3, "thousands": 1e-3, "millions": 1e-3}
STEP = {"claims": "week", "gdp": "quarter"}
CHANGED = set()  # series extended or refreshed during this run


def _path(sid, initial):
    return os.path.join(CACHE_DIR, f"{sid}{'.initial' if initial else ''}.json")


def load(sid, initial):
    try:
        with open(_path(sid, initial)) as fh:
            c = json.load(fh)
        if isinstance(c.get("rows"), list):
            return c
    except (OSError, ValueError):
        pass
    return {"source": "", "fetched": "", "rows": []}


def save(sid, initial, c):
    os.makedirs(CACHE_DIR, exist_ok=True)
    c["rows"] = [list(r) for r in c["rows"]]
    with open(_path(sid, initial), "w") as fh:
        json.dump(c, fh, separators=(",", ":"))
    CHANGED.add(sid)


RETRY_AFTER_FAILURE = dt.timedelta(hours=6)


def _age(c, now):
    try:
        return now - dt.datetime.fromisoformat(c["fetched"])
    except (TypeError, ValueError, KeyError):
        return dt.timedelta(days=9999)


def _backing_off(c, now):
    try:
        return now - dt.datetime.fromisoformat(c["tried"]) < RETRY_AFTER_FAILURE
    except (TypeError, ValueError, KeyError):
        return False


def _fallback_daily(sid, today):
    try:
        rows = agencies.market_observations(sid, FETCH_FROM if sid != "DFF" else "2020-01-01", today)
    except Exception:
        return None
    return [(d, float(v), "") for d, v, _ in rows] if rows else None


class Store:
    """fetch_obs(series, start, initial=False) for direction.fit, backed by the cache."""

    def __init__(self, now, log=print, fred=fredapi, cutoff=None):
        self.now, self.today, self.log, self.fred = now, now.date(), log, fred
        self.cutoff = cutoff  # daily rows on or after this date are left out (today's close not settled yet)
        self.sources = {}

    def __call__(self, sid, start, initial=False):
        c = load(sid, initial)
        due = _age(c, self.now) > (INITIAL_REFRESH if initial else DAILY_REFRESH) and not _backing_off(c, self.now)
        tried = False
        if due and self.fred.KEY:
            rows = self.fred.observations(sid, FETCH_FROM, initial=initial)
            rows = [list(r) for r in rows] if rows else rows
            if rows and len(rows) > 20:
                if initial:
                    # keep any figures appended from the calendar that FRED hasn't caught up with yet
                    have = {r[0] for r in rows}
                    rows = list(rows) + [r for r in c["rows"] if r[0] not in have and r[2] > rows[-1][2]]
                    c = {"source": "FRED/ALFRED first release", "rows": sorted(rows)}
                else:
                    merged = {r[0]: r for r in c["rows"]}
                    merged.update({r[0]: r for r in rows})
                    c = {"source": f"FRED {sid}", "rows": sorted(merged.values())}
                c["fetched"] = self.now.isoformat(timespec="minutes")
                save(sid, initial, c)
                due = False
            else:
                tried = True
                self.log(f"history: FRED unavailable for {sid}; using cached history")
        if due and not initial:
            rows = _fallback_daily(sid, self.today)
            rows = [list(r) for r in rows] if rows else rows
            if rows and len(rows) > 20:
                merged = {r[0]: r for r in c["rows"]}
                merged.update({r[0]: r for r in rows})
                c = {"source": c["source"] or "Treasury / New York Fed", "rows": sorted(merged.values()),
                     "fetched": self.now.isoformat(timespec="minutes")}
                save(sid, initial, c)
                tried = False
            else:
                tried = True
        if tried:
            c["tried"] = self.now.isoformat(timespec="minutes")
            save(sid, initial, c)
        rows = [tuple(r) for r in c["rows"] if r[0] >= start and (initial or not self.cutoff or r[0] < self.cutoff)]
        if rows:
            self.sources[sid] = c["source"]
        return rows or None


# ----------------------------------------------------------------- extending first-release history from the calendar
def _add_months(d, n):
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def next_period(kind, last_period):
    d = dt.date.fromisoformat(last_period[:10])
    step = STEP.get(kind, "month")
    if step == "week":
        return (d + dt.timedelta(days=7)).isoformat()
    return _add_months(d, 3 if step == "quarter" else 1).isoformat()


def event_period(kind, e, title_period):
    if kind == "claims":  # FRED dates weekly claims by the Saturday that ends the week, five days before release
        rel = dt.date.fromisoformat(e["date"])
        return (rel - dt.timedelta(days=(rel.weekday() - 5) % 7)).isoformat()
    if kind == "gdp" and not ("advance" in e["title"].lower() or "first" in e["title"].lower()):
        return None  # second and third estimates are revisions, not first releases
    p = title_period(e, kind)
    return p.isoformat() if p else None


def component_actual(e, i, label):
    if i == 0 and e.get("actual"):
        return e["actual"]
    for c in e.get("components") or []:
        if c.get("label") == label and c.get("actual"):
            return c["actual"]
    return None


def extend_from_events(events, models, releases, kind_of, title_period, figure, log=print):
    """Append newly confirmed figures to the first-release history. Returns how many were added."""
    modes = {}
    for kind, cfg in models.items():
        modes[(kind, cfg["head"][0])] = cfg["head"][1]
        for sid, mode, _ in cfg["comps"]:
            modes[(kind, sid)] = mode
    added = 0
    for e in sorted(events, key=lambda x: x["date"]):
        kind = kind_of(e)
        if kind not in models or not e.get("actual") or e.get("held"):
            continue
        period = event_period(kind, e, title_period)
        if not period:
            continue
        for i, (label, sid, tf) in enumerate(releases[kind]["comps"]):
            mode = modes.get((kind, sid))
            if not mode or tf not in UNITS:
                continue
            c = load(sid, True)
            if not c["rows"]:
                continue  # history must be loaded from FRED once before it can be extended
            last = c["rows"][-1]
            if e["date"] <= last[2] or period <= last[0]:
                continue
            if period != next_period(kind, last[0]):
                log(f"history: {sid} skips from {last[0]} to {period}; waiting for a full refresh")
                continue
            a = figure(component_actual(e, i, label), UNITS[tf])
            if a is None:
                continue
            if mode == "pct":
                v = last[1] * (1 + a / 100)
            elif mode == "diff":
                v = last[1] + a
            else:
                v = a
            c["rows"].append([period, v, e["date"]])
            c["source"] = c["source"].split(" + ")[0] + " + Displace calendar"
            save(sid, True, c)
            added += 1
    return added
