"""Cached daily market series for the engine: fed funds, the dollar index, 2- and 10-year Treasury yields.

Kept in engine/cache/series/<ID>.json ([date, value, ""]), committed by the workflow. Sources, best first:
FRED's public CSV downloads (no key), then the Treasury yield curve and the New York Fed. Refreshed every few
hours; a source that fails is retried after a short pause while the cached history stays in use.
"""
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
DAILY_REFRESH = dt.timedelta(hours=4)
RETRY_AFTER_FAILURE = dt.timedelta(minutes=50)  # roughly the next scheduled run

CHANGED = set()  # series extended or refreshed during this run


def _path(sid, initial=False):
    return os.path.join(CACHE_DIR, f"{sid}.json")


def load(sid, initial=False):
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
    """Keyless St. Louis Fed download. Replaced by a fake in the tests."""

    def daily(self, sid, start):
        url = f"{publicdata.FRED}/graph/fredgraph.csv?" + urlencode({"id": sid, "cosd": start})
        return [(d, v) for d, v, _ in publicdata.read_csv(publicdata.download(url), sid, start)]


def _fallback_daily(sid, today):
    try:
        rows = agencies.market_observations(sid, FETCH_FROM if sid != "DFF" else "2020-01-01", today)
    except Exception:
        return None
    return [(d, float(v)) for d, v, _ in rows] if rows else None


class Store:
    """fetch_obs(series, start, initial=False) for direction.fit, backed by the cache."""

    def __init__(self, now, log=print, source=None, cutoff=None):
        self.now, self.today, self.log = now, now.date(), log
        self.src = source or Public()
        self.cutoff = cutoff  # rows on or after this date are left out (today's close not settled yet)
        self.sources = {}

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

    def __call__(self, sid, start):
        c = self._daily(sid)
        rows = [tuple(r) for r in c["rows"] if r[0] >= start and (not self.cutoff or r[0] < self.cutoff)]
        if rows:
            self.sources[sid] = c["source"]
        return rows or None
