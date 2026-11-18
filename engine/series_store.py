"""Cached history for the news-outcome engine. Free public sources only, no API keys.

Two kinds of series are kept in engine/cache/series/ (committed by the workflow):

  <ID>.initial.json   every period as FIRST published, with the date it was published
                      ([period, level, release date]). This is what traders saw on release day, so the model
                      never learns from later revisions.
  <ID>.json           daily market series ([date, value, ""]): fed funds, yields, dollar, EUR/USD.

First releases come from ALFRED, the St. Louis Fed's public archive of every past edition of each series:
  1. its download page lists every date the series was published (each one is a release date);
  2. for each date, the series as it stood that day (a "vintage") shows the newly added period.
The change for that period (m/m %, or the payrolls gain) is taken within that same vintage and chained onto
the stored history, so each step is exactly the figure published that morning, even when earlier months
were revised at the same time. The history loads in the background over the first runs (a time budget per
run, resumable) and refreshes weekly. Between refreshes, the engine's own confirmed calendar figures are
appended, but only for exactly the next period, so a missed release never shifts the history.

Daily series come from FRED's public CSV downloads, with the Treasury yield curve and the New York Fed as
fallbacks.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
import re
import time
from urllib.parse import urlencode

import agencies
import publicdata

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "cache", "series")
FETCH_FROM = "2007-01-01"
HISTORY_FROM = "2008-06-01"  # first vintage to read; the model starts in 2010 and needs a warm-up
INITIAL_REFRESH = dt.timedelta(days=6)
DAILY_REFRESH = dt.timedelta(hours=4)
RETRY_AFTER_FAILURE = dt.timedelta(minutes=50)  # roughly the next scheduled run
BUDGET_SECONDS = 9 * 60  # per run, shared by every series still loading
WORKERS = 4
SKIP_AFTER = 3  # a past vintage that fails on this many separate runs is skipped
BATCH = 24

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


def _since(stamp, now):
    try:
        return now - dt.datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return dt.timedelta(days=9999)


# ----------------------------------------------------------------- public sources
class Public:
    """Keyless St. Louis Fed downloads. Replaced by a fake in the tests."""

    def vintages(self, sid):
        body = publicdata.download(f"{publicdata.ALFRED}/series/downloaddata?seid={sid}").decode("utf-8", "replace")
        block = re.search(r'name="form\[selected_vintage_dates\]\[\]"[^>]*>(.*?)</select>', body, re.S)
        dates = re.findall(r'value="(\d{4}-\d\d-\d\d)"', block.group(1)) if block else []
        if not dates:
            raise ValueError(f"no vintage dates listed for {sid}")
        return sorted(set(dates))

    def snapshot(self, sid, vintage, start):
        url = f"{publicdata.ALFRED}/graph/alfredgraph.csv?" + urlencode(
            {"id": sid, "cosd": start, "coed": vintage, "vintage_date": vintage})
        rows = publicdata.read_csv(publicdata.download(url), f"{sid}_{vintage.replace('-', '')}", start, vintage)
        return [(d, v) for d, v, _ in rows]

    def daily(self, sid, start):
        url = f"{publicdata.FRED}/graph/fredgraph.csv?" + urlencode({"id": sid, "cosd": start})
        return [(d, v) for d, v, _ in publicdata.read_csv(publicdata.download(url), sid, start)]


def _fallback_daily(sid, today):
    try:
        rows = agencies.market_observations(sid, FETCH_FROM if sid != "DFF" else "2020-01-01", today)
    except Exception:
        return None
    return [(d, float(v)) for d, v, _ in rows] if rows else None


def chain(rows, vintage, snap, mode):
    """Append the periods first published in `snap` (one vintage) to `rows`. Returns how many were added."""
    last = rows[-1][0] if rows else None
    added = 0
    for i, (period, value) in enumerate(snap):
        if last is not None and period <= last:
            continue
        if last is None and i != len(snap) - 1:
            continue  # the very first stored row is the newest period of the first vintage
        prev = snap[i - 1] if i else None
        if rows and mode in ("pct", "diff"):
            if not prev or prev[0] != rows[-1][0] or not prev[1]:
                continue  # the vintage doesn't carry the prior period: can't take the published change
            level = rows[-1][1] * value / prev[1] if mode == "pct" else rows[-1][1] + value - prev[1]
        else:
            level = value
        rows.append([period, level, vintage])
        last = period
        added += 1
    return added


class Store:
    """fetch_obs(series, start, initial=False) for direction.fit, backed by the cache."""

    def __init__(self, now, modes, log=print, source=None, cutoff=None, budget=BUDGET_SECONDS):
        self.now, self.today, self.log = now, now.date(), log
        self.modes = modes  # series -> transform used by the model ("pct", "diff" or "level")
        self.src = source or Public()
        self.cutoff = cutoff  # daily rows on or after this date are left out (today's close not settled yet)
        self.deadline = time.monotonic() + budget
        self.sources = {}
        self.loading = set()

    # --- first releases
    def _initial(self, sid):
        c = load(sid, True)
        stamp = c.get("fetched") if c.get("complete") else ""
        if _since(stamp, self.now) < INITIAL_REFRESH or _since(c.get("tried"), self.now) < RETRY_AFTER_FAILURE:
            return c
        if time.monotonic() > self.deadline:
            if not c.get("complete"):
                self.loading.add(sid)
            return c
        mode = self.modes.get(sid, "level")
        try:
            vint = [v for v in self.src.vintages(sid) if v > c.get("through", "") and v >= HISTORY_FROM]
        except Exception as e:
            self.log(f"history: ALFRED vintage list for {sid} unavailable ({e}); using cached history")
            c["tried"] = self.now.isoformat(timespec="minutes")
            save(sid, True, c)
            return c
        rows, failed = c["rows"], False

        def start(v):
            return (dt.date.fromisoformat(v) - dt.timedelta(days=420)).isoformat()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for b in range(0, len(vint), BATCH):
                if time.monotonic() > self.deadline or failed:
                    break
                batch = vint[b:b + BATCH]
                snaps = list(pool.map(lambda v: self._snap(sid, v, start(v)), batch))
                for v, snap in zip(batch, snaps):
                    for wait in (3, 8):  # brief hiccups are common: retry on the spot, one at a time
                        if snap is not None:
                            break
                        time.sleep(wait)
                        snap = self._snap(sid, v, start(v))
                    if snap is None:
                        fails = c.setdefault("fails", {})
                        fails[v] = fails.get(v, 0) + 1
                        if fails[v] < SKIP_AFTER:
                            failed = True  # stop at the gap so the history stays in order; resume next run
                            break
                        self.log(f"history: {sid} vintage {v} failed on {fails[v]} runs; skipping it")
                        c["through"] = v
                        continue
                    chain(rows, v, snap, mode)
                    c["through"] = v
                c["rows"] = rows
                save(sid, True, c)
        done = c.get("through", "") >= (vint[-1] if vint else "")
        c["source"] = "ALFRED first releases" + (" + Displace calendar" if "calendar" in c.get("source", "") else "")
        if done:
            c["complete"] = True
            c["fetched"] = self.now.isoformat(timespec="minutes")
            c.pop("tried", None)
        else:
            self.loading.add(sid)
            if failed:
                c["tried"] = self.now.isoformat(timespec="minutes")
            self.log(f"history: {sid} loaded through {c.get('through', 'nothing yet')}; continuing next run")
        save(sid, True, c)
        return c

    def _snap(self, sid, v, start):
        try:
            return self.src.snapshot(sid, v, start)
        except Exception:
            return None

    # --- daily market series
    def _daily(self, sid):
        c = load(sid, False)
        if _since(c.get("fetched"), self.now) < DAILY_REFRESH or _since(c.get("tried"), self.now) < RETRY_AFTER_FAILURE:
            return c
        got, label = None, ""
        try:
            got, label = self.src.daily(sid, FETCH_FROM), f"FRED {sid}"
        except Exception:
            got = None
        if not got or len(got) < 20:
            got, label = _fallback_daily(sid, self.today), "Treasury / New York Fed"
        if got and len(got) > 20:
            merged = {r[0]: [r[0], r[1], ""] for r in c["rows"]}
            merged.update({d: [d, v, ""] for d, v in got})
            c = {"source": label, "rows": [merged[d] for d in sorted(merged)], "fetched": self.now.isoformat(timespec="minutes")}
        else:
            c["tried"] = self.now.isoformat(timespec="minutes")
            self.log(f"history: no source answered for {sid}; using cached history")
        save(sid, False, c)
        return c

    def __call__(self, sid, start, initial=False):
        c = self._initial(sid) if initial else self._daily(sid)
        if initial and not c.get("complete"):
            return None  # a half-loaded history would train the model on a stale, shortened sample
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


def model_modes(models):
    """series -> transform for every series a model uses."""
    modes = {}
    for cfg in models.values():
        modes[cfg["head"][0]] = cfg["head"][1]
        for sid, mode, _ in cfg["comps"]:
            modes[sid] = mode
    return modes


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
        if kind not in models or not e.get("actual"):
            continue
        period = event_period(kind, e, title_period)
        if not period:
            continue
        for i, (label, sid, tf) in enumerate(releases[kind]["comps"]):
            mode = modes.get((kind, sid))
            if not mode or tf not in UNITS:
                continue
            c = load(sid, True)
            if not c["rows"] or not c.get("complete"):
                continue  # history must be fully loaded once before it can be extended
            last = c["rows"][-1]
            if e["date"] <= last[2] or period <= last[0]:
                continue
            if period != next_period(kind, last[0]):
                log(f"history: {sid} skips from {last[0]} to {period}; waiting for the weekly refresh")
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
