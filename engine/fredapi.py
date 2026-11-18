"""Small FRED client with retries and an in-run cache.

FRED is the St. Louis Fed's free data service: https://fred.stlouisfed.org/docs/api/fred/
Every function returns None (never raises) when the key is missing or FRED can't be reached,
so the engine always falls back to the data it already has.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from source_health import record

KEY = os.environ.get("FRED_API_KEY", "").strip()
BASE = "https://api.stlouisfed.org/fred/"
STATS = {"calls": 0, "errors": 0, "failed": []}
_cache = {}


def _get(path, **params):
    if not KEY:
        return None
    params.update(api_key=KEY, file_type="json")
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    if url in _cache:
        return _cache[url]
    for attempt in range(4):
        try:
            STATS["calls"] += 1
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
            record("fred", True)
            _cache[url] = data
            time.sleep(0.15)  # stay well under FRED's 120 requests a minute
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            break
        except Exception:
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            break
    STATS["errors"] += 1
    record("fred", False)
    STATS["failed"].append(params.get("series_id") or params.get("release_id") or path)
    _cache[url] = None
    return None


def observations(series, start, initial=False):
    """[(date, value, realtime_start)] for a series. initial=True gives values as first published."""
    p = {"series_id": series, "observation_start": start}
    if initial:
        p.update(output_type=4, realtime_start="1776-07-04", realtime_end="9999-12-31")
    d = _get("series/observations", **p)
    if not d:
        return None
    out = []
    for o in d.get("observations", []):
        v = o.get("value")
        if v in (".", "", None):
            continue
        try:
            out.append((o["date"], float(v), o.get("realtime_start", "")))
        except ValueError:
            continue
    return out


def releases():
    """{release name: id} for every FRED release."""
    d = _get("releases", limit=1000)
    if not d:
        return None
    return {r["name"]: r["id"] for r in d.get("releases", [])}


def release_dates(release_id, start, end="9999-12-31"):
    """Release dates (past and scheduled) between start and end, oldest first."""
    d = _get("release/dates", release_id=release_id, realtime_start=start, realtime_end=end,
             include_release_dates_with_no_data="true", sort_order="asc", limit=10000)
    if not d:
        return None
    return sorted({r["date"] for r in d.get("release_dates", []) if start <= r["date"] <= end})
