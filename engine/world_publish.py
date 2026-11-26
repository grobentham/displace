"""Build every Displace World view from the ledger: data files, static pages, RSS feeds and sitemap entries.

All of these are derived. The ledger (site/data/world/ledger) is the only source of truth, so this module can be
re-run at any time and will produce the same pages from the same ledger.
"""
import datetime as dt
import html
import json
import statistics
from collections import Counter, defaultdict, deque
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import world_nlp as N
from world_ledger import LABELS, iso, load_json, parse, write_json

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA = SITE / "data/world"
LEDGER = DATA / "ledger"
PAGES = SITE / "world"
BASE = "https://grobentham.github.io/displace/"
SGT = ZoneInfo("Asia/Singapore")
CSS_V = "20261127a"
KIND_NAMES = {"market": "Market move", "attention": "Coverage spike", "filing": "Company filing", "rule": "US rule",
              "quake": "Earthquake", "haze": "Singapore haze", "release": "Economic release", "trend": "Long-term base rate"}
LABEL_NAMES = {"hit": "Came true", "miss": "Did not happen", "unresolved": "Open", "not_assessable": "Not assessable"}
PRINCIPLES = [
    ("A claim is only useful if a stranger could grade it from public data.", "Every Displace World claim stores the exact rule that grades it."),
    ("Freeze the claim before the outcome is known, and never edit it.", "Each claim carries a SHA-256 hash; the engine refuses to save a changed one."),
    ("Date the event, the report and the check separately.", "Signals show when something happened, when Displace published it, and when it was graded."),
    ("Coverage measures attention, not truth.", "A coverage spike says many outlets wrote about a topic, not that the story is right."),
    ("Many articles can be one source.", "Repeated wire copies are grouped before Displace counts outlets."),
    ("A probability needs comparable past cases.", "Displace only prints a probability when at least 20 earlier cases exist, and shows the count."),
    ("Count misses as loudly as hits.", "Misses are listed on the Trust page next to the hits."),
    ("A listed source is not a verified outcome.", "Grades come from data (prices, counts, official records), never from a headline."),
    ("Big moves come in clusters.", "After a large daily move, the next week's moves are usually larger than normal; Displace measures how often."),
    ("A filing's item code says what kind of news it is, not whether it is good.", "Displace reads SEC item numbers, not the filing's text."),
    ("Effective dates move.", "Rule checkpoints are graded on whether the stated date held."),
    ("Keyword matches can be wrong.", "Every keyword-based link is labelled as such."),
]


def esc(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def sgt(ts):
    try:
        return parse(ts).astimezone(SGT).strftime("%d %b %Y, %H:%M SGT")
    except (ValueError, AttributeError):
        return str(ts)


# summaries ----------------------------------------------------------------------------------------------------
def claim_view(ledger, cid):
    c = ledger.claims[cid]
    hist = ledger.assessments.get(cid) or []
    last = hist[-1] if hist else {}
    return {"id": cid, "statement": c["statement"], "kind": c["kind"], "probability": c.get("probability"),
            "base": c.get("base"), "due": c["due"], "rule": c["rule"]["type"], "label": ledger.current(cid),
            "assessed_at": last.get("assessed_at"), "happened": last.get("happened", ""), "learned": last.get("learned", ""),
            "hash": c["hash"]}


def summary(ledger, s):
    return {"id": s["id"], "title": s["title"], "kind": s["kind"], "category": s["category"], "areas": s.get("areas", []),
            "published_at": s["published_at"], "event_at": s.get("event_at"), "rank": s.get("rank", 0),
            "horizon": s.get("horizon", "short"), "markets": s.get("markets", []), "entities": s.get("entities", {}),
            "lead": s["facts"][0]["text"] if s.get("facts") else "",
            "claims": [claim_view(ledger, c) for c in s.get("claims", [])],
            "url": f"world/s/{s['id']}.html"}


def ordered(ledger):
    return sorted(ledger.signals.values(), key=lambda s: (s["published_at"], s.get("rank", 0)), reverse=True)


# scorecard ----------------------------------------------------------------------------------------------------
def scorecard(ledger):
    labels = Counter(ledger.current(c) for c in ledger.claims)
    graded = [(c, ledger.current(cid)) for cid, c in ledger.claims.items() if ledger.current(cid) in ("hit", "miss")]
    probs = [(c["probability"], 1 if lab == "hit" else 0) for c, lab in graded if c.get("probability") is not None]
    brier = round(statistics.mean((p - y) ** 2 for p, y in probs), 4) if probs else None
    buckets = []
    for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
        rows = [(p, y) for p, y in probs if lo <= p < lo + 0.2 or (lo == 0.8 and p == 1.0)]
        buckets.append({"range": f"{lo:.0%}–{lo + 0.2:.0%}", "n": len(rows),
                        "average_probability": round(statistics.mean(p for p, _ in rows), 3) if rows else None,
                        "came_true": round(statistics.mean(y for _, y in rows), 3) if rows else None})
    by_rule = defaultdict(lambda: Counter())
    for cid, c in ledger.claims.items():
        by_rule[c["rule"]["type"]][ledger.current(cid)] += 1
    kinds = Counter(s["kind"] for s in ledger.signals.values())
    return {"signals": len(ledger.signals), "claims": len(ledger.claims), "labels": {k: labels.get(k, 0) for k in LABELS},
            "graded": len(graded), "hit_rate": round(sum(1 for _, l in graded if l == "hit") / len(graded), 3) if graded else None,
            "probabilistic": len(probs), "brier": brier, "brier_coin": 0.25 if probs else None,
            "brier_skill": round(1 - brier / 0.25, 3) if probs else None, "calibration": buckets,
            "by_rule": {k: dict(v) for k, v in sorted(by_rule.items())}, "rule_names": RULE_NAMES, "by_kind": dict(kinds),
            "corrections": len(ledger.corrections())}


RULE_NAMES = {"close_above_after": "Direction five sessions after a big market move",
             "moves_stay_wide": "Volatility staying high after a big move",
             "stock_reaction_wide": "Share price reaction to company filings",
             "coverage_persists": "Coverage spikes staying elevated for a week",
             "fr_date_unchanged": "US rule dates holding", "aftershock": "Large aftershocks after M7+ earthquakes",
             "psi_below": "Haze clearing within 72 hours", "trend_holds": "Year-on-year trends persisting"}


def lessons(ledger):
    out = []
    for rule, label in RULE_NAMES.items():
        rows = [(c, ledger.current(cid)) for cid, c in ledger.claims.items() if c["rule"]["type"] == rule]
        graded = [(c, l) for c, l in rows if l in ("hit", "miss")]
        if not rows:
            continue
        hits = sum(1 for _, l in graded if l == "hit")
        probs = [c["probability"] for c, _ in graded if c.get("probability") is not None]
        text = (f"{label}: {hits} of {len(graded)} graded claims came true ({hits / len(graded):.0%})." if graded
                else f"{label}: {len(rows)} claims published, none graded yet.")
        if probs:
            text += f" The average stated probability was {statistics.mean(probs):.0%}."
            gap = hits / len(graded) - statistics.mean(probs)
            if len(graded) >= 20:
                text += (" Outcomes ran ahead of the stated odds." if gap > 0.1 else
                         " Outcomes fell short of the stated odds." if gap < -0.1 else " Outcomes were close to the stated odds.")
            else:
                text += " Fewer than 20 graded claims: too few to judge the odds."
        out.append({"rule": rule, "title": label, "published": len(rows), "graded": len(graded), "hits": hits, "text": text})
    return out


def cases(ledger, limit=200):
    out = []
    for cid, hist in ledger.assessments.items():
        if cid not in ledger.claims or not hist:
            continue
        c = ledger.claims[cid]
        s = ledger.signals.get(c["signal_id"], {})
        last = hist[-1]
        out.append({"claim": cid, "signal": c["signal_id"], "signal_title": s.get("title", ""), "category": s.get("category"),
                    "predicted": c["statement"], "probability": c.get("probability"), "frozen_at": c["frozen_at"],
                    "due": c["due"], "label": ledger.current(cid), "assessed_at": last["assessed_at"],
                    "happened": last["happened"], "learned": last.get("learned", ""), "open": last.get("open", ""),
                    "next": "Nothing further: graded by its rule." if last["label"] in ("hit", "miss") else f"Check again after {c['due']}."})
    out.sort(key=lambda x: x["assessed_at"], reverse=True)
    return out[:limit]


# connections --------------------------------------------------------------------------------------------------
def relations():
    rel = defaultdict(list)
    for r in N.ENTITIES["relations"]:
        rel[r["a"]].append((r["b"], r["basis"]))
        rel[r["b"]].append((r["a"], r["basis"]))
    return rel


def nodes_of(s):
    out = {"category:" + c for c in [s["category"]] + s.get("categories", [])}
    if s.get("kind") in ("market", "trend"):                 # a market is the subject only of market signals
        out |= {"market:" + m for m in s.get("markets", [])}
    out |= {"company:" + c for c in (s.get("entities") or {}).get("companies", [])}
    return out


def link(a, b, rel):
    """How two signals are joined, strongest first.
    documented:  both signals name the same company (each source names it; that is checkable)
    topic:       their categories are joined by one of Displace's documented topic relations (not proven for these stories)
    co-mentioned: they name the same country
    """
    ea, eb = a.get("entities") or {}, b.get("entities") or {}
    same = sorted(set(ea.get("companies", [])) & set(eb.get("companies", [])))
    if same:
        return {"type": "documented", "via": same, "basis": "Both signals name " + ", ".join(same) + "."}
    for x in nodes_of(a):
        for y, basis in rel.get(x, []):
            if y in nodes_of(b) and not (x.startswith("company:") or y.startswith("company:")):
                return {"type": "topic", "via": [x, y], "basis": basis + " This does not show the two stories are connected."}
    shared = sorted(set(ea.get("countries", [])) & set(eb.get("countries", [])))
    if shared:
        return {"type": "co-mentioned", "via": shared, "basis": "Both name " + ", ".join(shared) + "; not evidence that one affects the other."}
    return None


def connections(signals, day):
    rel = relations()
    pool = [s for s in signals if s.get("kind") != "trend"][:60]
    edges = {}
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            l = link(a, b, rel)
            if l:
                edges[(a["id"], b["id"])] = l
                edges[(b["id"], a["id"])] = l
    adj = defaultdict(list)
    for (x, y) in edges:
        adj[x].append(y)
    by = {s["id"]: s for s in pool}
    routes = []
    tops = sorted(pool, key=lambda s: -s.get("rank", 0))[:8]
    for a in tops:
        prev = {a["id"]: None}
        q = deque([a["id"]])
        while q:
            x = q.popleft()
            for y in adj[x]:
                if y not in prev:
                    prev[y] = x
                    q.append(y)
        for b in pool:
            if b["id"] == a["id"] or b["category"] == a["category"] or b["id"] not in prev:
                continue
            path = [b["id"]]
            while prev[path[-1]]:
                path.append(prev[path[-1]])
            path.reverse()
            if len(path) > 4:
                continue
            links = [edges[(path[i], path[i + 1])] for i in range(len(path) - 1)]
            routes.append({"from": a["id"], "to": b["id"], "degrees": len(path) - 2, "path": path, "links": links,
                           "documented": sum(l["type"] == "documented" for l in links),
                           "score": a.get("rank", 0) + b.get("rank", 0) + 30 * sum(l["type"] == "documented" for l in links)
                                    + 10 * sum(l["type"] == "co-mentioned" for l in links) - 15 * len(path)})
    routes.sort(key=lambda r: -r["score"])
    seen, picked = set(), []
    for r in routes:
        key = frozenset((r["from"], r["to"]))
        if key in seen:
            continue
        seen.add(key)
        picked.append(r)
        if len(picked) == 6:
            break
    used = {x for r in picked for x in r["path"]}
    return {"date": day, "nodes": [{"id": i, "title": by[i]["title"], "kind": by[i]["kind"], "category": by[i]["category"],
                                     "published_at": by[i]["published_at"]} for i in sorted(used)],
            "routes": picked, "edges_considered": len(edges) // 2, "signals_considered": len(pool)}


# early edition ------------------------------------------------------------------------------------------------
def early(ledger, now, signals):
    local = now.astimezone(SGT)
    day = local.date().isoformat()
    since = now - dt.timedelta(hours=24)
    recent = [s for s in signals if parse(s["published_at"]) >= since]
    graded = []
    for cid, hist in ledger.assessments.items():
        if hist and parse(hist[-1]["assessed_at"]) >= since and cid in ledger.claims:
            graded.append({"claim": cid, "statement": ledger.claims[cid]["statement"], "label": hist[-1]["label"],
                           "happened": hist[-1]["happened"], "signal": ledger.claims[cid]["signal_id"]})
    due = sorted(({"claim": cid, "statement": c["statement"], "due": c["due"], "signal": c["signal_id"],
                   "probability": c.get("probability")}
                  for cid, c in ledger.claims.items()
                  if ledger.current(cid) == "unresolved" and day <= c["due"] <= (local.date() + dt.timedelta(days=3)).isoformat()),
                 key=lambda x: x["due"])[:15]
    cal = load_json(SITE / "data/calendar/events.json", {}).get("events", [])
    window = {(local.date() + dt.timedelta(days=k)).isoformat() for k in (0, 1)}
    events = [e for e in cal if e.get("date") in window and e.get("impact") == "high"][:10]
    sections = []
    top = sorted(recent, key=lambda s: -s.get("rank", 0))[:5]
    shown = {s["id"] for s in top}

    def sec(sid, title, kinds, n):
        rows = [summary(ledger, s) for s in recent if s["kind"] in kinds and s["id"] not in shown][:n]
        if rows:
            sections.append({"id": sid, "title": title, "signals": rows})
    if top:
        sections.append({"id": "top", "title": "The strongest signals", "signals": [summary(ledger, s) for s in top]})
    sec("markets", "More unusual market moves", ("market",), 8)
    sec("coverage", "Where coverage jumped", ("attention",), 8)
    sec("rules", "New US rules and company filings", ("rule", "filing"), 10)
    sec("world", "Earthquakes, haze and releases", ("quake", "haze", "release"), 8)
    srcs, seen = [], set()
    for s in recent:
        for src in s.get("sources", []):
            if src["url"] not in seen:
                seen.add(src["url"])
                srcs.append({**src, "signal": s["id"]})
    headline = (top[0]["title"] if top else "A quiet day: no new signals in the last 24 hours")
    return {"date": day, "title": headline, "published_at": iso(now), "coverage_from": iso(since), "coverage_to": iso(now),
            "time_zone": "Asia/Singapore", "signal_count": len(recent), "sections": sections, "graded": graded[:20],
            "due": due, "calendar": events, "sources": srcs[:60],
            "reading_notes": ["Signals are produced by fixed rules from public data; none is written by a person or an AI model.",
                              "Probabilities are historical frequencies of comparable cases, shown with their counts.",
                              "Headlines from other outlets are linked, not checked; read the originals."]}


# HTML ---------------------------------------------------------------------------------------------------------
WORLD_NAV = [("index.html", "Signals"), ("early.html", "Early"), ("connections.html", "Connections"),
             ("long-term.html", "Long Term"), ("before-the-headlines.html", "Before the Headlines"),
             ("came-true.html", "Came True"), ("learns.html", "Learns"), ("trust.html", "Trust"),
             ("topics.html", "Topics"), ("radar.html", "My Displace"), ("business.html", "Business")]


def nav(prefix, current=""):
    """prefix: path from the page to site/ ('../' for site/world/*, '../../' one folder further down)."""
    w = prefix + "world/"
    links = "".join(f'<a href="{w}{href}"' + (' aria-current="page"' if href == current else "") + f">{esc(name)}</a>"
                    for href, name in WORLD_NAV)
    return (f'<nav class="gnav" aria-label="Site"><div class="wide"><a class="brand" href="{prefix}index.html#top">'
            '<svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><rect width="26" height="26" rx="7" fill="#0071e3"/>'
            '<rect x="5" y="13" width="4" height="7" rx="1" fill="#fff" opacity=".75"/><rect x="11" y="6" width="4" height="14" rx="1" fill="#fff"/>'
            '<rect x="17" y="4" width="4" height="6" rx="1" fill="#fff" opacity=".75"/></svg>Displace</a><ul>'
            f'<li><a href="{prefix}index.html#bias">Today</a></li><li><a href="{prefix}index.html#calendar">News</a></li>'
            f'<li><a href="{prefix}index.html#tools">Tools</a></li><li><a href="{prefix}research-hub.html">Research</a></li>'
            f'<li><a href="{w}index.html" aria-current="page">World</a></li><li><a href="/iron-brain/">Intraday ›</a></li></ul>'
            f'<div class="navr"><a class="navsrch" href="{prefix}search.html" aria-label="Search Displace">'
            '<svg width="17" height="17" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
            '<line x1="11" y1="11" x2="15" y2="15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></a>'
            f'<a class="pillbtn" href="{w}radar.html">My Displace</a></div></div></nav>'
            f'<nav class="rnav" aria-label="Displace World"><div class="wide">{links}</div></nav>')


def head(title, desc, canonical, prefix, extra=""):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} | Displace World</title><meta name="description" content="{esc(desc[:160])}">'
            f'<link rel="canonical" href="{esc(canonical)}"><link rel="stylesheet" href="{prefix}assets/intelligence.css?v={CSS_V}">'
            f'<link rel="stylesheet" href="{prefix}assets/world.css?v={CSS_V}"><meta name="theme-color" content="#ffffff">'
            f'<link rel="alternate" type="application/rss+xml" title="Displace World" href="{prefix}world/feed.xml">'
            f'<meta property="og:type" content="article"><meta property="og:title" content="{esc(title)}">'
            f'<meta property="og:url" content="{esc(canonical)}">{extra}</head><body>'
            '<a class="dp-skip" href="#content">Skip to content</a>')


def statements(lines):
    tag = {"fact": "Reported fact", "interpretation": "Interpretation", "estimate": "Estimate", "open_question": "Open question"}
    return "<ul class=\"wd-lines\">" + "".join(
        f'<li><span class="wd-class wd-{esc(l["class"])}">{tag[l["class"]]}</span> {esc(l["text"])}</li>' for l in lines) + "</ul>"


def claim_rows(claims):
    rows = []
    for c in claims:
        p = f'{c["probability"]:.0%}<small> of {c["base"]["n"]} past cases</small>' if c.get("probability") is not None else '<small>No base rate</small>'
        status = f'<span class="wd-label wd-{esc(c["label"])}">{LABEL_NAMES[c["label"]]}</span>'
        if c.get("happened"):
            status += f'<br><small>{esc(c["happened"])}</small>'
        rows.append(f'<tr><td>{esc(c["statement"])}<br><small class="wd-hash">{esc(c["id"])} · SHA-256 {esc(c["hash"][:16])}…</small></td>'
                    f'<td>{p}</td><td>{esc(c["due"])}</td><td>{status}</td></tr>')
    return ('<div class="scroll"><table class="wd-claims"><thead><tr><th>Claim (frozen at publication)</th><th>Historical probability</th>'
            '<th>Due</th><th>Status</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def signal_page(ledger, s, related):
    sm = summary(ledger, s)
    p = "../../"
    cat = N.CATEGORIES.get(s["category"], {"name": s["category"]})
    url = BASE + f"world/s/{s['id']}.html"
    src = "".join(
        f'<li><a href="{esc(x["url"])}" rel="noopener">{esc(x["title"])}</a><br><small>{esc(x["publisher"])}'
        + (f' · published {esc(sgt(x["published_at"]) if "T" in str(x["published_at"]) else x["published_at"])}' if x.get("published_at") else " · publication time not established")
        + (f' · retrieved {esc(sgt(x["retrieved_at"]))}' if x.get("retrieved_at") else "")
        + f' · {"Primary source" if x.get("access") == "primary" else "Public access"}'
        + (f' · Limit: {esc(x["limit"])}' if x.get("limit") else "") + "</small></li>" for x in s.get("sources", []))
    rel = "".join(f'<li><a href="{esc(r["id"])}.html">{esc(r["title"])}</a> <small>{esc(r["basis"])}</small></li>' for r in related)
    body = (f'{head(s["title"], sm["lead"], url, p)}{nav(p)}<main id="content" class="wd-main wd-signal" data-signal="{esc(s["id"])}">'
            f'<p class="wd-crumbs"><a href="../index.html">World Signals</a> / <a href="../topics.html?c={esc(s["category"])}">{esc(cat["name"])}</a> / {esc(KIND_NAMES.get(s["kind"], s["kind"]))}</p>'
            f'<h1>{esc(s["title"])}</h1>'
            f'<p class="muted">Published {esc(sgt(s["published_at"]))} · Event {esc(sgt(s["event_at"]) if "T" in str(s.get("event_at")) else s.get("event_at"))} · '
            f'{esc(s["id"])} · {"Long term" if s.get("horizon") == "long" else "Short term"} · Written by fixed rules, not by a person or an AI model</p>'
            f'<p><button class="wd-save" type="button" data-save="{esc(s["id"])}">Save to My Displace</button></p>'
            f'<section class="panel wd-move"><h2>Your next move</h2><p><strong>Use this if:</strong> {esc(s.get("use_if"))}</p>'
            f'<p><strong>No action if:</strong> {esc(s.get("no_action_if"))}</p></section>'
            f'<section class="panel"><h2>What happened</h2>{statements(s["facts"])}</section>'
            f'<section class="panel"><h2>Why it might matter</h2>{statements(s.get("why", []))}</section>'
            + (f'<section class="panel"><h2>Claims Displace will grade</h2><p class="muted">Each claim was frozen when this signal was published and is graded automatically by the rule stored with it. <a href="../trust.html">How grading works</a></p>{claim_rows(sm["claims"])}</section>' if sm["claims"] else "")
            + f'<section class="panel"><h2>What could change the picture</h2>{statements(s.get("counter", []))}</section>'
            f'<section class="panel"><h2>What to check next</h2>{statements(s.get("next", []))}</section>'
            + (f'<section class="panel"><h2>Connected signals</h2><ul>{rel}</ul><p class="muted">Links come from Displace\'s list of documented relations or from shared names; neither proves cause.</p></section>' if rel else "")
            + f'<section class="panel"><h2>Sources</h2><ol class="wd-sources">{src}</ol></section>'
            f'<p class="muted wd-foot">Displace World publishes research and statistics, not personal financial advice. '
            f'<a href="../trust.html">Trust and corrections</a> · <a href="../../data/world/ledger/claims.json">Raw claim ledger</a></p></main>'
            f'<script src="{p}assets/world.js?v={CSS_V}"></script></body></html>\n')
    return body


def early_page(ed):
    p = "../../"
    url = BASE + f"world/early/{ed['date']}.html"
    secs = ""
    for sec in ed["sections"]:
        items = "".join(f'<li><a href="../s/{esc(s["id"])}.html">{esc(s["title"])}</a><br><small>{esc(s["lead"])}</small></li>' for s in sec["signals"])
        secs += f'<section class="panel"><h2>{esc(sec["title"])}</h2><ul class="wd-list">{items}</ul></section>'
    cal = "".join(f'<li>{esc(e["date"])} {esc(e.get("time", ""))} New York · {esc(e["title"])}</li>' for e in ed["calendar"])
    due = "".join(f'<li>{esc(d["due"])} · <a href="../s/{esc(d["signal"])}.html">{esc(d["statement"])}</a>'
                  + (f' <small>({d["probability"]:.0%} historically)</small>' if d.get("probability") is not None else "") + "</li>" for d in ed["due"])
    graded = "".join(f'<li><span class="wd-label wd-{esc(g["label"])}">{LABEL_NAMES[g["label"]]}</span> <a href="../s/{esc(g["signal"])}.html">{esc(g["statement"])}</a><br><small>{esc(g["happened"])}</small></li>' for g in ed["graded"])
    srcs = "".join(f'<li><a href="{esc(s["url"])}" rel="noopener">{esc(s["title"])}</a> <small>{esc(s["publisher"])}</small></li>' for s in ed["sources"])
    return (f'{head("Early, " + ed["date"] + ": " + ed["title"], ed["title"], url, p)}{nav(p, "early.html")}<main id="content" class="wd-main">'
            f'<p class="wd-crumbs"><a href="../early.html">Early</a> / {esc(ed["date"])}</p><h1>{esc(ed["title"])}</h1>'
            f'<p class="muted">Early edition for {esc(ed["date"])} · published {esc(sgt(ed["published_at"]))} · covers {esc(sgt(ed["coverage_from"]))} to {esc(sgt(ed["coverage_to"]))} · {ed["signal_count"]} new signals</p>'
            + secs
            + (f'<section class="panel"><h2>High-impact releases today and tomorrow</h2><ul>{cal}</ul></section>' if cal else "")
            + (f'<section class="panel"><h2>Graded in the last 24 hours</h2><ul class="wd-list">{graded}</ul></section>' if graded else "")
            + (f'<section class="panel"><h2>What to check next</h2><ul class="wd-list">{due}</ul></section>' if due else "")
            + f'<section class="panel"><h2>Sources and reading notes</h2><ol class="wd-sources">{srcs}</ol><ul>'
            + "".join(f"<li>{esc(n)}</li>" for n in ed["reading_notes"]) + "</ul></section>"
            f'<p class="muted">This edition is never edited after publication. Corrections appear on the <a href="../trust.html">Trust page</a>.</p></main>'
            f'<script src="{p}assets/world.js?v={CSS_V}"></script></body></html>\n')


def rss(items, title, link, path):
    ch_root = ET.Element("rss", version="2.0")
    ch = ET.SubElement(ch_root, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = link
    ET.SubElement(ch, "description").text = "Displace World signals: rule-based, source-linked, graded in public."
    for s in items[:50]:
        it = ET.SubElement(ch, "item")
        ET.SubElement(it, "title").text = s["title"]
        ET.SubElement(it, "link").text = BASE + s["url"]
        ET.SubElement(it, "guid").text = BASE + s["url"]
        ET.SubElement(it, "description").text = s["lead"]
        ET.SubElement(it, "category").text = s["category"]
        ET.SubElement(it, "pubDate").text = format_datetime(parse(s["published_at"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ET.tostring(ch_root, encoding="unicode", xml_declaration=True) + "\n")


def related_for(s, pool, rel, n=6):
    out = []
    for o in pool:
        if o["id"] == s["id"]:
            continue
        l = link(s, o, rel)
        if l:
            out.append({"id": o["id"], "title": o["title"], "basis": l["basis"]})
        if len(out) >= n:
            break
    return out


# build --------------------------------------------------------------------------------------------------------
def build(ledger, timing, now):
    signals = ordered(ledger)
    feed = [summary(ledger, s) for s in signals]
    write_json(DATA / "feed.json", {"generated": iso(now), "count": len(feed), "signals": feed[:600]}, compact=True)
    score = scorecard(ledger)
    corrections = ledger.corrections()
    changes = []
    for cid, hist in ledger.assessments.items():
        for h in hist:
            changes.append({"at": h["assessed_at"], "claim": cid, "label": h["label"], "note": h["happened"]})
    changes.sort(key=lambda x: x["at"], reverse=True)
    misses = [x for x in cases(ledger, 1000) if x["label"] == "miss"][:60]
    health = load_json(DATA / "health.json", {})
    write_json(DATA / "trust.json", {"generated": iso(now), "scorecard": score, "misses": misses,
                                     "corrections": corrections, "changes": changes[:200], "health": health,
                                     "integrity": {"claims_hashed": len(ledger.claims),
                                                   "history": "https://github.com/grobentham/displace/commits/main/site/data/world/ledger"}})
    write_json(DATA / "learns.json", {"generated": iso(now), "principles": [{"principle": a, "practice": b} for a, b in PRINCIPLES],
                                      "lessons": lessons(ledger), "cases": cases(ledger)})
    hits = [x for x in cases(ledger, 2000) if x["label"] == "hit"]
    write_json(DATA / "came-true.json", {"generated": iso(now), "count": len(hits), "cases": hits[:300]})
    write_json(DATA / "before-the-headlines.json", {"generated": iso(now),
                                                     "entries": sorted(timing, key=lambda t: t["signal_published"], reverse=True)})
    longs = [summary(ledger, s) for s in signals if s.get("horizon") == "long"]
    write_json(DATA / "long-term.json", {"generated": iso(now), "signals": longs[:200]})
    cats = Counter(s["category"] for s in signals)
    areas = Counter(a for s in signals for a in s.get("areas", []))
    topics = [{"id": c["id"], "name": c["name"], "description": c["description"], "count": cats.get(c["id"], 0),
               "markets": c["markets"], "areas": [{**{k: a[k] for k in ("id", "name")}, "count": areas.get(a["id"], 0)} for a in c["areas"]],
               "latest": [summary(ledger, s)["id"] for s in signals if s["category"] == c["id"]][:5]} for c in N.TAXONOMY["categories"]]
    write_json(DATA / "topics.json", {"generated": iso(now), "categories": topics})
    # connections: one map a day, from the last 72 hours of signals
    recent = [s for s in signals if parse(s["published_at"]) >= now - dt.timedelta(hours=72)]
    day = now.astimezone(SGT).date().isoformat()
    conn = connections(recent, day)
    write_json(DATA / f"connections/{day}.json", conn)
    days = sorted((p.stem for p in (DATA / "connections").glob("*.json") if p.stem != "index"), reverse=True)
    write_json(DATA / "connections/index.json", {"days": days})
    # early: one edition a day, written once after 06:00 Singapore time, never rewritten
    local = now.astimezone(SGT)
    path = DATA / f"early/{local.date().isoformat()}.json"
    if local.hour >= 6 and not path.exists():
        write_json(path, early(ledger, now, signals))
    editions = sorted((p.stem for p in (DATA / "early").glob("20*.json")), reverse=True)
    write_json(DATA / "early/index.json", {"editions": [{"date": d, "title": load_json(DATA / f"early/{d}.json", {}).get("title", "")} for d in editions]})
    # static pages
    PAGES.mkdir(parents=True, exist_ok=True)
    shells()
    rel = relations()
    pages = 0
    (PAGES / "s").mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(signals):
        window = signals[max(0, i - 40): i + 40]
        (PAGES / "s" / f"{s['id']}.html").write_text(signal_page(ledger, s, related_for(s, window, rel)), encoding="utf-8")
        pages += 1
    (PAGES / "early").mkdir(parents=True, exist_ok=True)
    for d in editions:
        ed = load_json(DATA / f"early/{d}.json", None)
        if ed:
            (PAGES / "early" / f"{d}.html").write_text(early_page(ed), encoding="utf-8")
            pages += 1
    rss(feed, "Displace World", BASE + "world/", PAGES / "feed.xml")
    for c in N.TAXONOMY["categories"]:
        rss([f for f in feed if f["category"] == c["id"]], f"Displace World: {c['name']}", BASE + f"world/topics.html?c={c['id']}",
            PAGES / "feeds" / f"{c['id']}.xml")
    urls = ["world/" + h for h, _ in WORLD_NAV] + [f"world/s/{s['id']}.html" for s in signals] + [f"world/early/{d}.html" for d in editions]
    write_json(DATA / "urls.json", {"urls": urls}, compact=True)
    return pages


def check(data=DATA):
    """Gate check for site/data/world/trust.json and the ledger it summarises."""
    problems = []
    trust = load_json(data / "trust.json", None)
    if not isinstance(trust, dict) or "scorecard" not in trust:
        return ["missing World trust scorecard"]
    sc = trust["scorecard"]
    if sum(sc["labels"].values()) != sc["claims"]:
        problems.append("claim labels do not add up")
    try:
        from world_ledger import Ledger
        Ledger(data / "ledger")
    except ValueError as e:
        problems.append("ledger integrity: " + str(e))
    return problems


# page shells (the scripts fill them from the data files) ----------------------------------------------------
SHELLS = {
    "index.html": ("signals", "World Signals", "World Signals",
                   "Early, source-linked signals about what is changing worldwide: coverage spikes, unusual market moves, new US rules, company filings, earthquakes and haze. Every claim is frozen when published and graded later by a stated rule."),
    "early.html": ("early", "Early", "Early: the daily briefing",
                   "One edition a day after 06:00 Singapore time: the strongest new signals, what was graded, and what to check next. Editions are never edited after publication."),
    "connections.html": ("connections", "Connections", "Connections",
                         "How the last three days' signals link to each other. Each route counts the stories in between. Solid links: both signals name the same company. Dashed links: a documented relation between their topics, or a shared country. No link proves cause."),
    "long-term.html": ("long-term", "Long Term", "Long Term",
                       "Signals with horizons from six months to five years, each with dated checkpoints and the historical base rate behind them."),
    "before-the-headlines.html": ("before-the-headlines", "Before the Headlines", "Before the Headlines",
                                  "When Displace published a signal before a major outlet reported the same thing. Publication order only: this is not an accuracy score."),
    "came-true.html": ("came-true", "Came True", "Came True",
                       "What Displace said, and what happened. Only claims graded as true appear here; misses are on the Trust page."),
    "learns.html": ("learns", "Learns", "What Displace World learns",
                    "Track records by rule, the research principles behind them, and every graded claim with what was predicted, what happened and what remains open."),
    "trust.html": ("trust", "Trust", "Trust and corrections",
                   "The full scorecard: every claim, hit, miss and open question, calibration of stated probabilities, misses, corrections, change history and source health."),
    "topics.html": ("topics", "Topics", "Topics",
                    "Thirty research categories and their research areas. Follow the ones you care about; your choices stay in this browser."),
    "radar.html": ("radar", "My Displace", "My Displace",
                   "Your followed topics and saved signals, kept only in this browser. No account, no sign-in, no tracking. Copy your settings to use them on another device."),
}

BUSINESS = """
<section class="panel"><h2>What a brief contains</h2><ul>
<li>The decision you are making, in one sentence.</li>
<li>Dated public evidence from World's sources: rules, filings, coverage, prices and official data.</li>
<li>How the evidence connects to your business, with documented and unproven links labelled.</li>
<li>What could change the conclusion, and dated checkpoints Displace will grade in public.</li></ul></section>
<section class="panel"><h2>Examples of questions</h2><ul>
<li>Will a proposed US tariff rule take effect on its stated date, and which of my import categories does it name?</li>
<li>Is coverage of a supplier's country rising unusually, and from which outlets?</li>
<li>How did watch-list shares move after earlier filings of this kind?</li></ul></section>
<section class="panel"><h2>Request research</h2>
<p class="muted">Requests open a GitHub issue on the public Displace repository, so other people can read them. Use only public or non-sensitive information.</p>
<form id="brief" class="wd-form">
<p><label>Sector<br><input name="sector" required maxlength="120"></label></p>
<p><label>Market or country<br><input name="market" required maxlength="120"></label></p>
<p><label>Decision you need to make<br><textarea name="decision" required maxlength="600" rows="3"></textarea></label></p>
<p><label>Time horizon<br><select name="horizon"><option>Weeks</option><option>Months</option><option>Years</option></select></label></p>
<p><button class="pillbtn" type="submit">Open the request</button></p></form></section>"""


def shells():
    p = "../"
    for name, (page, nav_title, h1, intro) in SHELLS.items():
        url = BASE + "world/" + name
        (PAGES / name).write_text(
            f'{head(nav_title, intro, url, p)}{nav(p, name)}<main id="content" class="wd-main" data-page="{page}">'
            f'<p class="wd-kicker">Displace World</p><h1>{esc(h1)}</h1><p>{esc(intro)}</p>'
            f'<p id="status" class="muted" aria-live="polite">Loading…</p></main>'
            f'<script src="{p}assets/world.js?v={CSS_V}"></script></body></html>\n', encoding="utf-8")
    url = BASE + "world/business.html"
    intro = "Custom research built on the same ledger: source-linked evidence, stated limits and checkpoints graded in public."
    (PAGES / "business.html").write_text(
        f'{head("Displace Business", intro, url, p)}{nav(p, "business.html")}<main id="content" class="wd-main" data-page="business">'
        f'<p class="wd-kicker">Displace World</p><h1>Displace Business</h1><p>{esc(intro)}</p>'
        f'<p id="status" class="muted" aria-live="polite"></p>{BUSINESS}</main>'
        f'<script src="{p}assets/world.js?v={CSS_V}"></script></body></html>\n', encoding="utf-8")
