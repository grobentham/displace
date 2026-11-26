"""Collect Displace World's inputs from public sources into engine/cache/world. Network only happens here.

Each source is independent: a failure is recorded in the health report and the others carry on.
"""
import datetime as dt
import json
import time

import world_markets as M
import world_nlp as N
import world_sources as S
from world_ledger import iso, parse

FR_TERMS = ("tariff", "export controls", "sanctions", "semiconductor", "artificial intelligence", "critical minerals",
            "digital assets", "Section 232", "Section 301")
MAX_TIMING_CHECKS = 8


def _safe(health, name, fn, *a, **k):
    t0 = time.time()
    try:
        out = fn(*a, **k)
        health[name] = {"ok": True, "seconds": round(time.time() - t0, 1)}
        return out
    except Exception as e:                       # one broken source must not stop the run
        health[name] = {"ok": False, "seconds": round(time.time() - t0, 1), "error": repr(e)[:200]}
        return None


# GDELT --------------------------------------------------------------------------------------------------------
def coverage(now, health):
    histories = S.cache_load("coverage.json", {})
    articles = {}
    for cid, cat in N.CATEGORIES.items():
        days = histories.get(cid, {})
        span = "90d" if len(days) < 60 else "30d"
        tl = _safe(health, "gdelt-volume:" + cid, lambda: S.parse_gdelt_timeline(S.gdelt(cat["query"], "timelinevolraw", span)))
        if tl:
            days.update(tl)
            histories[cid] = dict(sorted(days.items())[-400:])
        arts = _safe(health, "gdelt-articles:" + cid, lambda: S.parse_gdelt_articles(S.gdelt(cat["query"], "artlist", "24h")))
        if arts is not None:
            articles[cid] = arts
    S.cache_save("coverage.json", histories)
    S.cache_save("articles.json", {"fetched": iso(now), "categories": articles})
    return histories, articles


def timing_checks(now, ledger, timing, health):
    """For recent signals: find the first major outlet to report the same thing after Displace published it."""
    done = {t["signal_id"] for t in timing}
    checked = 0
    domains = " OR ".join("domainis:" + d for d in __import__("world_signals").MAJOR_OUTLETS)
    for s in sorted(ledger.signals.values(), key=lambda s: s["published_at"], reverse=True):
        if checked >= MAX_TIMING_CHECKS:
            break
        pub = parse(s["published_at"])
        if s["id"] in done or (now - pub).days > 3 or s["kind"] not in ("filing", "rule", "attention"):
            continue
        if s["kind"] == "filing":
            words = s.get("match_words") or []
            if not words:
                continue
            q = f'"{s["match_name"]}" ({domains})'
        elif s["kind"] == "rule":
            words = s.get("match_words") or []
            if len(words) < 3:
                continue
            q = " ".join(w for w in words[:5] if len(w) > 2) + f" ({domains})"
        else:
            words = s.get("lead_tokens") or []
            if len(words) < 3:
                continue
            q = " ".join(w for w in words[:6] if len(w) > 2) + f" ({domains})"
        checked += 1
        arts = _safe(health, "gdelt-timing", lambda: S.parse_gdelt_articles(S.gdelt(q, "artlist", "3d")))
        if not arts:
            continue
        hits = []
        for a in arts:
            seen = parse(a["seen"])
            if seen <= pub:
                continue
            title = a["title"].lower()
            if s["kind"] == "filing":
                ok = s["match_name"].lower() in title and any(w in title for w in words)
            else:
                ok = N.jaccard(N.tokens(a["title"]), set(words)) >= 0.3
            if ok:
                hits.append((seen, a))
        if hits:
            seen, a = min(hits, key=lambda x: x[0])
            minutes = round((seen - pub).total_seconds() / 60)
            timing.append({"signal_id": s["id"], "signal_title": s["title"], "signal_published": s["published_at"],
                           "later_title": a["title"], "later_url": a["url"], "later_publisher": a["domain"],
                           "later_seen": a["seen"], "delay_minutes": minutes, "recorded_at": iso(now),
                           "basis": "Displace's publication time against the time GDELT first saw the later article.",
                           "qualification": "Matched by keywords in the headline; Displace did not read the article.",
                           "status": "matched"})
    return timing


# SEC EDGAR ----------------------------------------------------------------------------------------------------
def sec(now, health):
    tickers = S.cache_load("sec_tickers.json", {})
    if not tickers.get("map") or tickers.get("fetched", "")[:10] < (now - dt.timedelta(days=7)).date().isoformat():
        m = _safe(health, "sec-tickers", lambda: S.parse_sec_tickers(S.get("https://www.sec.gov/files/company_tickers.json", "sec")))
        if m:
            tickers = {"fetched": iso(now), "map": m}
            S.cache_save("sec_tickers.json", tickers)
    cik = tickers.get("map", {})
    seen = set(S.cache_load("sec_seen.json", []))
    history = S.cache_load("sec_history.json", {})
    new = []
    for co in N.ENTITIES["companies"]:
        c = cik.get(co["ticker"])
        if not c:
            continue
        time.sleep(0.25)                              # SEC asks for under 10 requests a second
        rows = _safe(health, "sec:" + co["ticker"],
                     lambda: S.parse_sec_filings(S.get(f"https://data.sec.gov/submissions/CIK{c:010d}.json", "sec")))
        if rows is None:
            continue
        history[co["ticker"]] = [{"form": r["form"], "accepted": r["acceptanceDateTime"], "items": r.get("items") or ""}
                                 for r in rows if r["form"] == "8-K"][:300]
        for r in rows:
            key = co["ticker"] + ":" + r["accessionNumber"]
            if key in seen:
                continue
            seen.add(key)
            try:
                accepted = dt.datetime.fromisoformat(r["acceptanceDateTime"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if accepted.tzinfo is None:
                accepted = accepted.replace(tzinfo=dt.timezone.utc)
            if (now - accepted).days > 3:
                continue                              # only new filings become signals
            new.append({"company": co, "form": r["form"], "items": r.get("items") or "",
                        "accepted": iso(accepted), "accession": r["accessionNumber"],
                        "url": S.sec_url(c, r["accessionNumber"], r["primaryDocument"])})
    S.cache_save("sec_seen.json", sorted(seen))
    S.cache_save("sec_history.json", history)
    return new


def stocks(now, tickers, health, rng="2y"):
    for t in sorted(tickers):
        path = M.STOCKS / f"{t}.json"
        try:
            old = json.loads(path.read_text())
            if old.get("fetched", "")[:13] >= iso(now - dt.timedelta(hours=12))[:13]:
                continue
        except (OSError, ValueError):
            old = {"closes": {}}
        closes = _safe(health, "yahoo:" + t, lambda: S.parse_yahoo_closes(S.get(S.yahoo_url(t, rng), "yahoo")))
        if closes:
            old["closes"].update(closes)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"fetched": iso(now), "closes": dict(sorted(old["closes"].items()))}, separators=(",", ":")))


def filing_base_rates(history):
    """Pooled across the watch list: after an 8-K with item X, how often did the first close move more than
    the stock's median absolute move of the previous 60 sessions?"""
    import world_signals as W
    rates = {}
    for ticker, rows in history.items():
        closes = M.load_stock(ticker)
        keys = list(closes)
        if len(keys) < 80:
            continue
        for r in rows:
            try:
                accepted = dt.datetime.fromisoformat(r["accepted"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if accepted.tzinfo is None:
                accepted = accepted.replace(tzinfo=dt.timezone.utc)
            sess = M.reaction_session(closes, accepted)
            if not sess:
                continue
            i = keys.index(sess)
            if i < M.LOOKBACK + 1:
                continue
            rets = [abs(closes[keys[j]] / closes[keys[j - 1]] - 1) for j in range(i - M.LOOKBACK, i)]
            wide = abs(closes[sess] / closes[keys[i - 1]] - 1) > sorted(rets)[len(rets) // 2]
            for item in {x.strip() for x in r["items"].split(",")}:
                if item in W.CLAIM_ITEMS:
                    b = rates.setdefault(item, {"n": 0, "hits": 0})
                    b["n"] += 1
                    b["hits"] += wide
    return rates


# Federal Register ---------------------------------------------------------------------------------------------
def federal_register(now, health, open_numbers):
    seen = set(S.cache_load("fr_seen.json", []))
    new = []
    for term in FR_TERMS:
        docs = _safe(health, "federal-register:" + term, lambda: S.parse_fr(S.get(S.fr_url(term), "federal-register")))
        for d in docs or []:
            if d["number"] in seen:
                continue
            seen.add(d["number"])
            if not d["published"] or d["published"] < (now.date() - dt.timedelta(days=3)).isoformat():
                continue
            new.append(d)
    docs_cache = S.cache_load("fr_docs.json", {})
    for number in sorted(open_numbers):
        try:
            rows = S.parse_fr(S.get(S.fr_doc_url(number), "federal-register"))
            docs_cache[number] = rows[0] if rows else "missing"
        except OSError as e:
            docs_cache[number] = "missing" if "404" in str(e) else docs_cache.get(number)
    S.cache_save("fr_docs.json", docs_cache)
    S.cache_save("fr_seen.json", sorted(seen))
    return new


# USGS and PSI -------------------------------------------------------------------------------------------------
def earthquakes(now, health, open_rules):
    seen = set(S.cache_load("usgs_seen.json", []))
    events = _safe(health, "usgs", lambda: S.parse_usgs(S.get(S.USGS_SIGNIFICANT, "usgs"))) or []
    fresh = [e for e in events if e["id"] not in seen]
    seen |= {e["id"] for e in events}
    S.cache_save("usgs_seen.json", sorted(seen)[-2000:])
    after = S.cache_load("aftershocks.json", {})
    for rule in open_rules:
        end = min(parse(rule["end"]), now)
        rows = _safe(health, "usgs-aftershocks", lambda: S.parse_usgs(S.get(
            S.usgs_query_url(rule["lat"], rule["lon"], rule["radius_km"], rule["min_mag"], rule["start"], iso(end)), "usgs")))
        if rows is not None:
            after[rule["exclude"]] = {"checked": iso(now), "complete": now >= parse(rule["end"]),
                                      "events": [r for r in rows if r["id"] != rule["exclude"] and r["time"] > rule["start"]]}
    S.cache_save("aftershocks.json", after)
    return [e for e in fresh if (now - parse(e["time"])).days <= 3]


def psi(now, health):
    hist = S.cache_load("psi.json", [])
    rows = _safe(health, "data.gov.sg-psi", lambda: S.parse_psi(S.get(S.PSI_URL, "data.gov.sg"))) or []
    have = {r[0] for r in hist}
    hist += [list(r) for r in rows if r[0] not in have]
    hist = sorted(hist)[-24 * 45:]
    S.cache_save("psi.json", hist)
    return [tuple(r) for r in hist]
