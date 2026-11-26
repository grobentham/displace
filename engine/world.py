"""Displace World engine.

    python engine/world.py run     collect from public sources, publish new signals, grade claims, build pages
    python engine/world.py build   no network: grade claims from the caches and rebuild pages

Templates only, no language model, no API keys. See engine/world_*.py for each part and README.md for the design.
"""
import datetime as dt
import json
import sys

import world_fetch as FE
import world_markets as M
import world_publish as P
import world_resolve as R
import world_signals as W
import world_sources as S
from world_ledger import Ledger, iso, load_json, parse, utcnow, write_json



def context(now):
    coverage = S.cache_load("coverage.json", {})
    fr = S.cache_load("fr_docs.json", {})
    after = S.cache_load("aftershocks.json", {})
    psi = [tuple(r) for r in S.cache_load("psi.json", [])]

    def aftershocks(rule):
        rec = after.get(rule["exclude"])
        if not rec:
            return None
        return rec["events"] if (rec["events"] or rec["complete"]) else None

    return {"market": lambda m: M.load_market(m, now), "series": M.load_series,
            "stock": lambda t: {d: v for d, v in M.load_stock(t).items() if d <= M.settled_cutoff(now).isoformat()},
            "coverage": lambda c: coverage.get(c, {}), "fr_doc": lambda n: fr.get(n), "aftershocks": aftershocks,
            "psi": lambda: psi}


def open_rules(ledger, kind):
    return [c["rule"] for cid, c in ledger.claims.items()
            if c["rule"]["type"] == kind and ledger.current(cid) == "unresolved"]


def publish_all(ledger, generated):
    added = 0
    for signal, claims in generated:
        try:
            added += ledger.add_signal(signal, claims)
        except ValueError as e:
            print("world: skipped", signal.get("id"), e)
    return added


def run(now, network=True):
    ledger = Ledger(P.LEDGER)
    health = {}
    TIMING, HEALTH = P.LEDGER / "timing.json", P.DATA / "health.json"
    timing = load_json(TIMING, {"timing": []})["timing"]
    generated = []
    if network:
        histories, articles = FE.coverage(now, health)
        base = W.N.spike_base_rate(list(histories.values()))
        generated += W.attention(now, histories, articles, base)
        new_filings = FE.sec(now, health) or []
        tickers = {c["ticker"] for c in W.N.ENTITIES["companies"]}
        FE.stocks(now, tickers, health)
        rates = FE.filing_base_rates(S.cache_load("sec_history.json", {}))
        S.cache_save("filing_rates.json", rates)
        generated += W.filings(now, new_filings, rates)
        numbers = {r["number"] for r in open_rules(ledger, "fr_date_unchanged") if r["value"] <= now.date().isoformat()}
        generated += W.rules(now, FE.federal_register(now, health, numbers) or [])
        generated += W.quakes(now, FE.earthquakes(now, health, open_rules(ledger, "aftershock")) or [])
        readings = FE.psi(now, health)
        recent = any(s["kind"] == "haze" and (now - parse(s["published_at"])).days < 3 for s in ledger.signals.values())
        generated += W.haze(now, readings, recent)
    news = load_json(P.SITE / "data/news/latest.json", {}).get("items", [])
    generated += W.releases(now, news)
    generated += W.market_moves(now)
    if now.day <= 7 and not any(s["kind"] == "trend" and s["published_at"][:7] == iso(now)[:7] for s in ledger.signals.values()):
        generated += W.long_term(now)
    added = publish_all(ledger, generated)
    graded = R.grade_all(ledger, context(now), now)
    if network:
        timing = FE.timing_checks(now, ledger, timing, health)
    ledger.save()
    write_json(TIMING, {"timing": timing})
    prev = load_json(HEALTH, {})
    write_json(HEALTH, {"checked_at": iso(now), "network": network,
                        "sources": health if network else prev.get("sources", {}),
                        "calls": S.STATS if network else prev.get("calls", {}),
                        "signals_added": added, "claims_graded": graded})
    pages = P.build(ledger, timing, now)
    print(f"world: {added} new signals, {graded} grades, {len(ledger.signals)} signals in the ledger, {pages} pages")
    return added, graded


def main(argv):
    mode = argv[1] if len(argv) > 1 else "build"
    if mode not in ("run", "build"):
        raise SystemExit(__doc__)
    run(utcnow(), network=(mode == "run"))


if __name__ == "__main__":
    main(sys.argv)
