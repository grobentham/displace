"""Free, keyless public sources for Displace World.

  GDELT DOC 2.0     worldwide news articles and coverage volume (100+ languages, nearly every country)
  SEC EDGAR         company filings (8-K, 10-Q, 10-K) for the watch list
  Federal Register  US rules, proposed rules and presidential documents
  USGS              significant earthquakes and aftershock counts
  data.gov.sg       Singapore's 24-hour PSI (haze)
  Yahoo chart       daily closes for watch-list shares (for grading claims)

Every parser is a pure function so it can be tested on saved responses. Every fetch goes through `get`, which
retries and records failures in STATS; a failed source never stops the run, it only means fewer signals.
Nothing here needs an account, a key or a secret.
"""
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "engine/cache/world"
UA = "Mozilla/5.0 (Displace World research engine; +https://github.com/grobentham/displace; grobentham@users.noreply.github.com)"
STATS = {}            # source -> {"calls": n, "errors": n, "last_error": str}
GDELT_GAP = 5.5       # GDELT asks for no more than one request every 5 seconds
_last_gdelt = [0.0]


def get(url, source, timeout=30, tries=3, max_bytes=8 * 1024 * 1024, sleep=time.sleep):
    stat = STATS.setdefault(source, {"calls": 0, "errors": 0, "last_error": ""})
    stat["calls"] += 1
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("response too large")
            return body.decode("utf-8", "replace")
        except Exception as e:          # network errors, HTTP errors, timeouts
            last = e
            if getattr(e, "code", None) in (400, 401, 403, 404):
                break
            sleep(3 * (attempt + 1))
    stat["errors"] += 1
    stat["last_error"] = repr(last)[:200]
    raise OSError(f"{source} unavailable: {last!r}")


def gdelt_url(query, mode, timespan, maxrecords=75):
    params = {"query": query, "mode": mode, "format": "json", "timespan": timespan}
    if mode == "artlist":
        params.update(maxrecords=str(maxrecords), sort="datedesc")
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)


def gdelt(query, mode, timespan, sleep=time.sleep, clock=time.monotonic, fetch=None):
    wait = GDELT_GAP - (clock() - _last_gdelt[0])
    if wait > 0:
        sleep(wait)
    try:
        return (fetch or get)(gdelt_url(query, mode, timespan), "gdelt")
    finally:
        _last_gdelt[0] = clock()


def gdelt_time(s):
    """'20261126T153000Z' -> aware datetime."""
    return dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)


def parse_gdelt_articles(text):
    if not text.strip().startswith("{"):
        return []                       # GDELT answers plain text for a bad or empty query
    out = []
    for a in json.loads(text).get("articles", []):
        try:
            seen = gdelt_time(a["seendate"])
        except (KeyError, ValueError):
            continue
        url = a.get("url", "")
        if not url.startswith(("https://", "http://")) or not a.get("title"):
            continue
        out.append({"url": url, "title": " ".join(a["title"].split())[:300], "domain": a.get("domain", ""),
                    "language": a.get("language", ""), "country": a.get("sourcecountry", ""),
                    "seen": seen.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return out


def parse_gdelt_timeline(text):
    """Daily article counts {YYYY-MM-DD: count} from a timelinevolraw answer (any resolution)."""
    if not text.strip().startswith("{"):
        return {}
    days = {}
    for series in json.loads(text).get("timeline", []):
        for point in series.get("data", []):
            try:
                day = gdelt_time(point["date"]).date().isoformat()
                days[day] = days.get(day, 0) + int(point.get("value", 0))
            except (KeyError, ValueError, TypeError):
                continue
        break                           # the first series is the article count
    return days


# SEC EDGAR ----------------------------------------------------------------------------------------------------
def parse_sec_tickers(text):
    return {row["ticker"].upper(): int(row["cik_str"]) for row in json.loads(text).values()}


def parse_sec_filings(text, forms=("8-K", "10-Q", "10-K")):
    recent = json.loads(text).get("filings", {}).get("recent", {})
    keys = ("form", "filingDate", "acceptanceDateTime", "accessionNumber", "primaryDocument", "items")
    cols = [recent.get(k, []) for k in keys]
    out = []
    for row in zip(*cols):
        rec = dict(zip(keys, row))
        if rec["form"] in forms:
            out.append(rec)
    return out


def sec_url(cik, accession, document):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"


# Federal Register ---------------------------------------------------------------------------------------------
FR_FIELDS = ("document_number", "title", "type", "abstract", "html_url", "publication_date", "agencies",
             "effective_on", "comments_close_on", "action")


def fr_url(term, per_page=20):
    q = [("per_page", str(per_page)), ("order", "newest"), ("conditions[term]", term)]
    q += [("conditions[type][]", t) for t in ("RULE", "PRORULE", "PRESDOCU")]
    q += [("fields[]", f) for f in FR_FIELDS]
    return "https://www.federalregister.gov/api/v1/documents.json?" + urllib.parse.urlencode(q)


def fr_doc_url(number):
    q = [("fields[]", f) for f in FR_FIELDS]
    return f"https://www.federalregister.gov/api/v1/documents/{number}.json?" + urllib.parse.urlencode(q)


def parse_fr(text):
    doc = json.loads(text)
    rows = doc.get("results", [doc] if "document_number" in doc else [])
    out = []
    for r in rows:
        if not r.get("document_number") or not str(r.get("html_url", "")).startswith("https://"):
            continue
        out.append({"number": r["document_number"], "title": " ".join(str(r.get("title", "")).split())[:300],
                    "type": r.get("type", ""), "abstract": " ".join(str(r.get("abstract") or "").split())[:600],
                    "url": r["html_url"], "published": r.get("publication_date"),
                    "agencies": [a.get("name") or a.get("raw_name") for a in r.get("agencies") or [] if a],
                    "effective_on": r.get("effective_on"), "comments_close_on": r.get("comments_close_on"),
                    "action": r.get("action") or ""})
    return out


# USGS ---------------------------------------------------------------------------------------------------------
USGS_SIGNIFICANT = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"


def usgs_query_url(lat, lon, radius_km, min_mag, start, end):
    q = {"format": "geojson", "latitude": f"{lat:.3f}", "longitude": f"{lon:.3f}", "maxradiuskm": str(radius_km),
         "minmagnitude": str(min_mag), "starttime": start, "endtime": end}
    return "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(q)


def parse_usgs(text):
    out = []
    for f in json.loads(text).get("features", []):
        p, g = f.get("properties", {}), f.get("geometry", {}).get("coordinates", [None, None, None])
        if p.get("mag") is None or p.get("time") is None:
            continue
        t = dt.datetime.fromtimestamp(p["time"] / 1000, dt.timezone.utc)
        out.append({"id": f.get("id"), "mag": float(p["mag"]), "place": p.get("place") or "", "url": p.get("url") or "",
                    "time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "alert": p.get("alert"), "tsunami": p.get("tsunami", 0),
                    "lon": g[0], "lat": g[1], "depth": g[2] if len(g) > 2 else None})
    return out


# data.gov.sg PSI ----------------------------------------------------------------------------------------------
PSI_URL = "https://api-open.data.gov.sg/v2/real-time/api/psi"


def parse_psi(text):
    """National 24-hour PSI readings as [(timestamp, value)]."""
    doc = json.loads(text)
    items = (doc.get("data") or {}).get("items") or doc.get("items") or []
    out = []
    for it in items:
        readings = it.get("readings", {}).get("psi_twenty_four_hourly", {})
        value = readings.get("national")
        stamp = it.get("timestamp") or it.get("updatedTimestamp") or it.get("date")
        if isinstance(value, (int, float)) and stamp:
            out.append((str(stamp), float(value)))
    return out


# Yahoo daily closes -------------------------------------------------------------------------------------------
def yahoo_url(symbol, rng="6mo"):
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range={rng}&interval=1d"


def parse_yahoo_closes(text):
    r = json.loads(text)["chart"]["result"][0]
    off = r.get("meta", {}).get("gmtoffset", 0)
    out = {}
    for t, c in zip(r.get("timestamp") or [], r["indicators"]["quote"][0].get("close") or []):
        if c:
            out[dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date().isoformat()] = round(float(c), 4)
    return out


# small cache helpers ------------------------------------------------------------------------------------------
def cache_load(name, default):
    try:
        return json.loads((CACHE / name).read_text())
    except (OSError, ValueError):
        return default


def cache_save(name, obj):
    path = CACHE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=True))
    tmp.replace(path)


def slug(text, n=48):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-")
