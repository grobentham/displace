"""Signal generators for Displace World. Fixed templates, no language model.

Each generator turns one kind of public event into a signal (what happened, why it might matter, what could
change the picture, what to check next, sources) plus claims that can be graded later by a stored rule.
A probability is attached only when at least 20 comparable past cases exist; it is the historical frequency,
nothing more.
"""
import datetime as dt
import hashlib
import urllib.parse

import world_markets as M
import world_nlp as N
from world_ledger import iso, parse

MAJOR_OUTLETS = ("reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com", "apnews.com", "bbc.co.uk",
                 "bbc.com", "nytimes.com", "theguardian.com", "straitstimes.com", "channelnewsasia.com",
                 "nikkei.com", "scmp.com", "economist.com", "marketwatch.com", "barrons.com", "axios.com")

ITEMS_8K = {
    "1.01": ("signed a material agreement", ["agreement", "deal", "partnership", "contract"]),
    "1.02": ("ended a material agreement", ["terminat", "ends", "ended", "agreement"]),
    "1.05": ("reported a material cybersecurity incident", ["cyber", "breach", "hack", "attack"]),
    "2.01": ("completed an acquisition or sale of assets", ["acqui", "completes", "sale", "buy"]),
    "2.02": ("reported quarterly results", ["earnings", "results", "revenue", "quarter", "profit"]),
    "2.05": ("disclosed restructuring or exit costs", ["layoff", "job cuts", "restructur", "cuts"]),
    "2.06": ("recorded a material impairment", ["impairment", "write-down", "writedown", "charge"]),
    "3.01": ("received a delisting or listing-rule notice", ["delist", "nasdaq notice", "listing"]),
    "4.02": ("said earlier financial statements can no longer be relied on", ["restate", "restatement"]),
    "5.02": ("announced a change of directors or officers", ["ceo", "cfo", "steps down", "resign", "appoint", "executive", "chief"]),
}
CLAIM_ITEMS = ("1.01", "1.05", "2.02", "2.05", "2.06", "3.01", "4.02", "5.02")


def poss(name):
    return name + ("'" if name.endswith("s") else "'s")


def F(text, cls="fact"):
    return {"text": text, "class": cls}


def short_hash(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8]


def day_label(d):
    d = dt.date.fromisoformat(d[:10]) if isinstance(d, str) else d
    return f"{d.day} {d.strftime('%b %Y')}"


def prob(base):
    if not base or base["n"] < 20:
        return None, None
    p = base["hits"] / base["n"]
    return round(min(max(p, 0.02), 0.98), 3), dict(base)


def source(title, url, publisher, published=None, retrieved=None, access="public", limit=""):
    return {"title": title, "url": url, "publisher": publisher, "published_at": published, "retrieved_at": retrieved,
            "access": access, "limit": limit}


def markets_for(categories):
    out = []
    for c in categories:
        for m in N.CATEGORIES.get(c, {}).get("markets", []):
            if m not in out:
                out.append(m)
    return out


# 1. unusual market moves --------------------------------------------------------------------------------------
def market_moves(now):
    out = []
    pool = [(mid, *spec, M.load_market(mid, now), "market") for mid, spec in M.MARKETS.items()]
    pool += [(sid, *spec, M.load_series(sid), "series") for sid, spec in M.SERIES_IDS.items()]
    for mid, name, unit, how, dec, closes, kind in pool:
        u = M.unusual(closes, how)
        if not u or abs(u["z"]) < M.MOVE_Z:
            continue
        if (now.date() - dt.date.fromisoformat(u["day"])).days > 5:
            continue
        sign = 1 if u["z"] > 0 else -1
        up, wide = M.after_big_move(closes, how, sign, before=u["day"])
        moved = (f"{'rose' if sign > 0 else 'fell'} {abs(u['move']):.2f}%" if how == "pct"
                 else f"{'rose' if sign > 0 else 'fell'} {abs(u['move']) * 100:.0f} basis points")
        sid = f"W{u['day'].replace('-', '')}-move-{mid.lower()}"
        title = f"{name} {moved} on {day_label(u['day'])}, a {abs(u['z']):.1f}-sigma day"
        p_up, b_up = prob(up)
        p_wide, b_wide = prob(wide)
        cat = {"nq": "equities", "es": "equities", "ym": "equities", "rty": "equities", "gold": "commodities",
               "cl": "energy", "btc": "crypto", "6e": "economics"}.get(mid, "economics")
        facts = [F(f"{name} closed at {M.fmt(u['close'], dec)} {unit} on {day_label(u['day'])}: it {moved}."),
                 F(f"That is {abs(u['z']):.1f} times its typical daily move over the previous {M.LOOKBACK} sessions "
                   f"(one standard deviation = {abs(u['sd']):.2f}{'%' if how == 'pct' else ' percentage points'}).")]
        why = [F("Large one-day moves tend to be followed by more large moves for a while (volatility clusters), "
                 "which changes position sizes and stop distances.", "interpretation")]
        if up["n"]:
            why.append(F(f"After {up['n']} earlier moves this size in the same direction, the close five sessions "
                         f"later was higher on {up['hits']} occasions ({up['hits'] / up['n']:.0%}).", "estimate"))
        counter = [F("A move can come from a single headline, a contract roll or thin holiday trading; the data "
                     "here does not say why the price moved.", "open_question"),
                   F("Past frequencies come from different market regimes and are not a forecast of this case.",
                     "interpretation")]
        sources = [source(f"{name} daily closes (Displace cache)", "https://grobentham.github.io/displace/research-hub.html",
                          "Displace from Yahoo Finance" if kind == "market" else "FRED, St. Louis Fed",
                          retrieved=iso(now), limit="Free data; closes can be revised.")]
        if kind == "series":
            sources[0]["url"] = f"https://fred.stlouisfed.org/series/{mid}"
        due5 = (dt.date.fromisoformat(u["day"]) + dt.timedelta(days=9)).isoformat()
        claims = []
        level = M.fmt(u["close"], dec)
        claims.append({"id": sid + "-C1", "kind": "forecast", "probability": p_up, "base": b_up, "due": due5,
                       "statement": f"{name} closes above {level} on the 5th session after {day_label(u['day'])}.",
                       "rule": {"type": "close_above_after", "source": kind, "id": mid, "day": u["day"],
                                "level": u["close"], "sessions": 5}})
        claims.append({"id": sid + "-C2", "kind": "forecast", "probability": p_wide, "base": b_wide, "due": due5,
                       "statement": f"{poss(name)} average daily move over the next 5 sessions is larger than its "
                                    f"previous 60-session average.",
                       "rule": {"type": "moves_stay_wide", "source": kind, "id": mid, "day": u["day"], "how": how,
                                "sessions": 5}})
        signal = {"id": sid, "kind": "market", "category": cat, "areas": [], "title": title,
                  "published_at": iso(now), "event_at": u["day"], "entities": {"markets": [mid] if kind == "market" else []},
                  "markets": [mid] if kind == "market" else [], "facts": facts, "why": why, "counter": counter,
                  "next": [F(f"Check the close on the 5th session after {day_label(u['day'])} against {level}.", "open_question")],
                  "use_if": "You hold or trade this market and size positions by recent volatility.",
                  "no_action_if": "You invest for years and do not trade around single days.",
                  "sources": sources, "rank": min(100, round(40 + 10 * abs(u["z"]))), "horizon": "short"}
        out.append((signal, claims))
    return out


# 2. coverage spikes (GDELT) -----------------------------------------------------------------------------------
def attention(now, histories, articles, base):
    out = []
    p, b = prob(base)
    day = (now.date() - dt.timedelta(days=1)).isoformat()
    prev = (now.date() - dt.timedelta(days=2)).isoformat()
    for cid, days in histories.items():
        s = N.spike(days, day)
        if not s or not s["spike"]:
            continue
        before = N.spike(days, prev)
        if before and before["spike"]:
            continue                                     # a continuing episode, already published
        cat = N.CATEGORIES[cid]
        groups = N.cluster(articles.get(cid, []))
        lead = groups[0] if groups else None
        sid = f"W{day.replace('-', '')}-attention-{cid}"
        countries = sorted({a["country"] for a in articles.get(cid, []) if a["country"]})
        langs = sorted({a["language"] for a in articles.get(cid, []) if a["language"]})
        title = f"News coverage of {cat['name'].lower()} jumped {s['ratio']:.1f}x on {day_label(day)}"
        if lead:
            title += f": {lead['title'][:110]}"
        facts = [F(f"GDELT counted {s['count']:,} articles matching Displace's {cat['name'].lower()} query on "
                   f"{day_label(day)} (UTC), against a median of {s['baseline']:,.0f} a day over the previous 28 days "
                   f"({s['ratio']:.1f}x, robust z = {s['z']:.1f}).")]
        if lead:
            facts.append(F(f"The most repeated story in the latest sample was reported by {lead['outlets']} outlets, "
                           f"first seen {lead['first_seen'].replace('T', ' ')[:16]} UTC: \"{lead['title'][:160]}\"."))
        if articles.get(cid):
            facts.append(F(f"The latest {len(articles[cid])} sampled articles came from {len(countries)} countries in "
                           f"{len(langs)} languages."))
        areas = []
        for a in articles.get(cid, []):
            for c, ar in N.classify(a["title"]):
                if c == cid:
                    areas += [x for x in ar if x not in areas]
        ent = {"companies": [], "countries": []}
        for g in groups[:5]:
            e = N.entities(g["title"])
            ent["companies"] += [x for x in e["companies"] if x not in ent["companies"]]
            ent["countries"] += [x for x in e["countries"] if x not in ent["countries"]]
        why = [F(f"Displace links {cat['name'].lower()} to: " + (", ".join(M.MARKETS[m][0] for m in cat["markets"])
                 if cat["markets"] else "no traded market directly") + ".", "interpretation"),
               F("A sudden rise in coverage often means a development is spreading beyond specialist outlets; "
                 "it says nothing about whether the development is good or bad.", "interpretation")]
        counter = [F("Wire stories are syndicated: many articles can repeat one source.", "open_question"),
                   F("Keyword queries catch unrelated stories that share words.", "open_question")]
        if lead:
            counter.append(F("The sample shows the latest articles, which may not be the ones behind the spike.", "open_question"))
        sources = [source(f"GDELT coverage volume: {cat['name']}",
                          "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
                              {"query": cat["query"], "mode": "timelinevolraw", "timespan": "90d"}),
                          "GDELT Project", retrieved=iso(now), limit="Counts of machine-monitored articles, not readers.")]
        for g in groups[:6]:
            a = g["articles"][0]
            sources.append(source(a["title"][:160], a["url"], a["domain"], published=a["seen"], retrieved=iso(now),
                                  limit="Headline only; Displace did not verify the story."))
        end = (dt.date.fromisoformat(day) + dt.timedelta(days=N.PERSIST["days"] + 2)).isoformat()
        claims = [{"id": sid + "-C1", "kind": "forecast", "probability": p, "base": b, "due": end,
                   "statement": f"Over the 7 days after {day_label(day)}, coverage averages at least "
                                f"{N.PERSIST['ratio']}x the old baseline ({N.PERSIST['ratio'] * s['baseline']:,.0f} articles a day).",
                   "rule": {"type": "coverage_persists", "category": cid, "day": day, "baseline": s["baseline"],
                            "ratio": N.PERSIST["ratio"], "days": N.PERSIST["days"]}}]
        signal = {"id": sid, "kind": "attention", "category": cid, "areas": areas[:6], "title": title,
                  "published_at": iso(now), "event_at": day, "entities": ent, "markets": cat["markets"],
                  "facts": facts, "why": why, "counter": counter,
                  "next": [F(f"Check whether coverage is still elevated on {day_label(end)}.", "open_question"),
                           F("Open the linked articles and find the primary source they cite.", "open_question")],
                  "use_if": f"You follow {cat['name'].lower()} or hold the markets linked to it.",
                  "no_action_if": "You need confirmed facts; this is a measure of attention, not of truth.",
                  "sources": sources, "rank": min(100, round(35 + 8 * s["ratio"] + 2 * min(s["z"], 10))),
                  "horizon": "short", "lead_tokens": sorted(N.tokens(lead["title"])) if lead else []}
        out.append((signal, claims))
    return out


# 3. company filings (SEC EDGAR) -------------------------------------------------------------------------------
def filings(now, new_filings, base_rates):
    out = []
    for f in new_filings:
        items = [i.strip() for i in (f.get("items") or "").split(",") if i.strip()]
        meaningful = [i for i in items if i in ITEMS_8K]
        if f["form"] == "8-K" and not meaningful:
            continue
        co = f["company"]
        accepted = parse(f["accepted"])
        sid = f"W{accepted.strftime('%Y%m%d')}-filing-{co['ticker'].lower()}-{f['accession'][-6:]}"
        if f["form"] == "8-K":
            what = "; ".join(ITEMS_8K[i][0] for i in meaningful)
            title = f"{co['name']} ({co['ticker']}) {ITEMS_8K[meaningful[0]][0]}"
        else:
            what = "filed its " + ("annual report" if f["form"] == "10-K" else "quarterly report")
            title = f"{co['name']} ({co['ticker']}) {what}"
        facts = [F(f"{co['name']} filed a Form {f['form']} with the SEC, accepted {accepted.strftime('%d %b %Y %H:%M')} UTC."
                   + (f" Items: {', '.join(meaningful)} ({what})." if f["form"] == "8-K" else ""))]
        why = [F("Company filings are the primary source that news reports are written from.", "interpretation")]
        claims = []
        key = next((i for i in meaningful if i in CLAIM_ITEMS), None)
        if key and f["form"] == "8-K":
            p, b = prob(base_rates.get(key))
            due = (accepted.date() + dt.timedelta(days=5)).isoformat()
            claims.append({"id": sid + "-C1", "kind": "forecast", "probability": p, "base": b, "due": due,
                           "statement": f"{co['ticker']}'s first close after this filing moves more than its median "
                                        f"absolute daily move of the previous 60 sessions.",
                           "rule": {"type": "stock_reaction_wide", "ticker": co["ticker"], "accepted": f["accepted"]}})
            if b:
                why.append(F(f"Across {b['n']} earlier item {key} filings by watch-list companies, the first close "
                             f"after the filing moved more than usual {b['hits']} times ({b['hits'] / b['n']:.0%}).", "estimate"))
        counter = [F("A filing can repeat news the company already released in a press release.", "open_question"),
                   F("Displace reads the filing's item codes, not its text.", "interpretation")]
        sources = [source(f"{co['name']} Form {f['form']}", f["url"], "U.S. SEC EDGAR", published=f["accepted"],
                          retrieved=iso(now), access="primary", limit="Item codes as filed; the text was not analysed.")]
        signal = {"id": sid, "kind": "filing", "category": co["categories"][0], "areas": [], "title": title,
                  "published_at": iso(now), "event_at": f["accepted"],
                  "entities": {"companies": [co["ticker"]], "countries": []}, "markets": markets_for(co["categories"][:1]),
                  "facts": facts, "why": why, "counter": counter,
                  "next": [F("Read the filing's exhibits (press release, agreement) for the details.", "open_question")],
                  "use_if": f"You own {co['ticker']} or compete with or supply {co['name']}.",
                  "no_action_if": "The filing is routine for you (for example an expected earnings date).",
                  "sources": sources, "rank": 70 if key in ("1.05", "4.02", "2.05", "5.02") else 55 if key else 35,
                  "horizon": "short", "match_words": ITEMS_8K[key][1] if key else [], "match_name": co["aliases"][0]}
        out.append((signal, claims))
    return out


# 4. US rules and executive actions (Federal Register) ---------------------------------------------------------
def rules(now, docs):
    out = []
    for d in docs:
        sid = f"W{d['published'].replace('-', '')}-rule-{d['number'].lower()}"
        cats = [c for c, _ in N.classify(d["title"] + " " + d["abstract"])] or ["policy"]
        if "policy" not in cats:
            cats.append("policy")
        kind = {"Rule": "final rule", "Proposed Rule": "proposed rule", "Presidential Document": "presidential document"}.get(d["type"], d["type"].lower())
        title = f"New US {kind}: {d['title'][:150]}"
        facts = [F(f"The Federal Register published a {kind} on {day_label(d['published'])}"
                   + (f" from {', '.join(d['agencies'][:3])}" if d["agencies"] else "") + ".")]
        if d["effective_on"]:
            facts.append(F(f"Stated effective date: {day_label(d['effective_on'])}."))
        if d["comments_close_on"]:
            facts.append(F(f"Public comments close on {day_label(d['comments_close_on'])}."))
        if d["abstract"]:
            facts.append(F("Summary as published: " + d["abstract"][:500]))
        claims = []
        today = now.date().isoformat()
        for n, field in enumerate(("effective_on", "comments_close_on"), 1):
            when = d.get(field)
            if when and when > today:
                label = "takes effect" if field == "effective_on" else "closes for comments"
                claims.append({"id": f"{sid}-C{n}", "kind": "checkpoint", "probability": None, "base": None,
                               "due": when, "statement": f"Document {d['number']} still {label} on {day_label(when)} "
                                                         "(the date is not moved or withdrawn).",
                               "rule": {"type": "fr_date_unchanged", "number": d["number"], "field": field, "value": when}})
        long_term = bool(d.get("effective_on") and d["effective_on"] > (now.date() + dt.timedelta(days=150)).isoformat())
        signal = {"id": sid, "kind": "rule", "category": cats[0], "categories": cats[1:], "areas": [], "title": title, "published_at": iso(now),
                  "event_at": d["published"], "entities": N.entities(d["title"] + " " + d["abstract"]),
                  "markets": markets_for(cats), "facts": facts,
                  "why": [F("Displace classifies this rule under: " + ", ".join(N.CATEGORIES[c]["name"] for c in cats if c in N.CATEGORIES) + ".", "interpretation"),
                          F("Federal rules change what businesses must do from a stated date; dates often move.", "interpretation")],
                  "counter": [F("A proposed rule can be changed or withdrawn before it is final.", "open_question"),
                              F("Displace matched this document by keywords; it may only touch the topic.", "open_question")],
                  "next": [F("Read the rule's 'Dates' and 'Summary' sections on the Federal Register page.", "open_question")]
                          + ([F(f"Check that the effective date is still {day_label(d['effective_on'])}.", "open_question")] if d["effective_on"] else []),
                  "use_if": "You import, export or operate in the affected industry.",
                  "no_action_if": "The rule does not name your products, sector or agency.",
                  "sources": [source(d["title"][:160], d["url"], "Federal Register (US)", published=d["published"],
                                     retrieved=iso(now), access="primary", limit="Official text; summaries can omit conditions.")],
                  "rank": 60 if d["type"] == "Presidential Document" else 50 if d["type"] == "Rule" else 40,
                  "horizon": "long" if long_term else "short", "match_words": sorted(N.tokens(d["title"]))[:8]}
        out.append((signal, claims))
    return out


# 5. earthquakes (USGS) ----------------------------------------------------------------------------------------
def quakes(now, events):
    out = []
    for q in events:
        if not (q["mag"] >= 6.0 or q["alert"] in ("orange", "red") or q["tsunami"]):
            continue
        t = parse(q["time"])
        sid = f"W{t.strftime('%Y%m%d')}-quake-{q['id']}"
        ent = N.entities(q["place"])
        facts = [F(f"USGS recorded a magnitude {q['mag']:.1f} earthquake {q['place']} at {t.strftime('%d %b %Y %H:%M')} UTC"
                   + (f", depth {q['depth']:.0f} km" if q["depth"] is not None else "") + ".")]
        if q["alert"]:
            facts.append(F(f"USGS PAGER alert level: {q['alert']} (estimated impact)."))
        if q["tsunami"]:
            facts.append(F("The USGS feed flags this event for a possible tsunami; check official warning centres."))
        claims = []
        if q["mag"] >= 7.0:
            end = t + dt.timedelta(days=7)
            claims.append({"id": sid + "-C1", "kind": "forecast", "probability": None, "base": None,
                           "due": end.date().isoformat(),
                           "statement": "At least one magnitude 5.0+ aftershock within 300 km in the 7 days after the main shock.",
                           "rule": {"type": "aftershock", "lat": q["lat"], "lon": q["lon"], "radius_km": 300,
                                    "min_mag": 5.0, "start": q["time"], "end": iso(end), "exclude": q["id"]}})
        why = [F("Large earthquakes can close factories, ports and chip plants in the affected area.", "interpretation")]
        if any(c in ent["countries"] for c in ("TW", "JP", "KR")):
            why.append(F("This region hosts semiconductor and electronics production.", "interpretation"))
        out.append(({"id": sid, "kind": "quake", "category": "weather", "areas": ["quakes"],
                     "title": f"Magnitude {q['mag']:.1f} earthquake {q['place']}", "published_at": iso(now),
                     "event_at": q["time"], "entities": ent,
                     "markets": ["nq"] if any(c in ent["countries"] for c in ("TW", "JP", "KR")) else [],
                     "facts": facts, "why": why,
                     "counter": [F("Early magnitude and location estimates are revised in the first hours.", "open_question"),
                                 F("Damage depends on depth and building standards, not magnitude alone.", "interpretation")],
                     "next": [F("Check local authorities and company statements for plant or port closures.", "open_question")],
                     "use_if": "You have staff, suppliers or travel plans in the region.",
                     "no_action_if": "You have no exposure to the region.",
                     "sources": [source(f"USGS event page: M{q['mag']:.1f} {q['place']}", q["url"] or "https://earthquake.usgs.gov/",
                                        "US Geological Survey", published=q["time"], retrieved=iso(now), access="primary",
                                        limit="Preliminary values that USGS revises.")],
                     "rank": min(100, round(30 + 10 * (q["mag"] - 5))), "horizon": "short"}, claims))
    return out


# 6. Singapore haze (data.gov.sg PSI) --------------------------------------------------------------------------
def haze(now, readings, recent_haze_signal):
    if not readings or recent_haze_signal:
        return []
    stamp, value = readings[-1]
    if value < 101:
        return []
    t = now
    sid = f"W{t.strftime('%Y%m%d')}-haze-sg"
    try:
        shown = parse(stamp).astimezone(dt.timezone(dt.timedelta(hours=8))).strftime("%d %b %Y, %H:%M SGT")
    except ValueError:
        shown = stamp
    band = "Unhealthy" if value <= 200 else "Very unhealthy" if value <= 300 else "Hazardous"
    end = t + dt.timedelta(hours=72)
    return [({"id": sid, "kind": "haze", "category": "singapore", "areas": ["sg-haze"],
              "title": f"Singapore's 24-hour PSI reached {value:.0f} ({band})", "published_at": iso(now), "event_at": stamp,
              "entities": {"companies": [], "countries": ["SG"]}, "markets": [],
              "facts": [F(f"The national 24-hour PSI was {value:.0f} at {shown}, in the {band.lower()} band (101 and above).")],
              "why": [F("NEA advises reducing prolonged or strenuous outdoor activity at these levels; schools and "
                        "outdoor events may change plans.", "interpretation")],
              "counter": [F("PSI can change quickly with wind direction.", "open_question")],
              "next": [F("Check the latest readings and NEA's health advisory before outdoor plans.", "open_question")],
              "use_if": "You live in or travel to Singapore or run outdoor work or events there.",
              "no_action_if": "You are not in Singapore.",
              "sources": [source("Pollutant Standards Index (PSI)", "https://data.gov.sg/datasets/d_fe37906a0182569b891506edc5e9f9dc/view",
                                 "National Environment Agency via data.gov.sg", published=stamp, retrieved=iso(now), access="primary")],
              "rank": 75, "horizon": "short"},
             [{"id": sid + "-C1", "kind": "forecast", "probability": None, "base": None, "due": end.date().isoformat(),
               "statement": "The national 24-hour PSI is back at 100 or below within 72 hours.",
               "rule": {"type": "psi_below", "threshold": 100, "start": iso(now), "end": iso(end)}}])]


# 7. central-bank decisions and economic releases (Displace's existing news engine) ----------------------------
def releases(now, items):
    out = []
    for it in items:
        if not it.get("analysis") or not it.get("url", "").startswith("https://"):
            continue
        published = it.get("published") or ""
        try:
            t = parse(published)
        except ValueError:
            continue
        if t > now or (now - t).days > 3:
            continue
        sid = "W" + t.strftime("%Y%m%d") + "-release-" + short_hash(it.get("id") or it["url"])
        cat = "economics"
        out.append(({"id": sid, "kind": "release", "category": cat, "areas": ["rates"] if "rate" in it["title"].lower() else [],
                     "title": f"{it['title']}: {it['analysis'].split('. ')[0][:140]}", "published_at": iso(now),
                     "event_at": iso(t), "entities": {"companies": [], "countries": ["US"] if it.get("source") not in ("ECB", "European Central Bank", "Bank of England") else []},
                     "markets": ["nq", "gold", "6e"],
                     "facts": [F(x.strip() + ("" if x.strip().endswith(".") else ".")) for x in it["analysis"].split(". ") if x.strip()][:5],
                     "why": [F(it.get("context") or "Official releases move rate expectations.", "interpretation")],
                     "counter": [F("First estimates are revised; the next release can change the picture.", "open_question")],
                     "next": [F("See the Displace calendar for the next release in this series.", "open_question")],
                     "use_if": "You trade rates, the dollar, gold or US index futures.",
                     "no_action_if": "You do not follow US macro data.",
                     "sources": [source(it["title"], it["url"], it.get("source") or "Official release", published=iso(t),
                                        retrieved=iso(now), access="primary")],
                     "rank": 55, "horizon": "short"}, []))
    return out


# 8. long-term trend checkpoints (monthly) ---------------------------------------------------------------------
HORIZONS = ((126, "6 months"), (252, "1 year"), (504, "2 years"), (756, "3 years"), (1260, "5 years"))


def long_term(now):
    out = []
    month = now.strftime("%Y%m")
    for mid, (name, unit, how, dec) in M.MARKETS.items():
        closes = M.load_market(mid, now)
        keys = list(closes)
        if len(keys) < 600:
            continue
        last = keys[-1]
        above = closes[last] > closes[keys[-253]]
        state = "above" if above else "below"
        sid = f"W{month}01-trend-{mid}"
        claims = []
        lines = []
        for n, (h, label) in enumerate(HORIZONS, 1):
            base = M.trend_persistence(closes, h, before=last)[state]
            p, b = prob(base)
            if b is None:
                continue
            due = (dt.date.fromisoformat(last) + dt.timedelta(days=round(h * 365 / 252) + 10)).isoformat()
            claims.append({"id": f"{sid}-C{n}", "kind": "forecast", "probability": p, "base": b, "due": due,
                           "statement": f"{h} sessions ({label}) after {day_label(last)}, {name} is still {state} its "
                                        f"level of 252 sessions before that date.",
                           "rule": {"type": "trend_holds", "id": mid, "day": last, "sessions": h, "state": state}})
            lines.append(f"{label}: {b['hits']} of {b['n']} ({b['hits'] / b['n']:.0%})")
        if not claims:
            continue
        ago = closes[keys[-253]]
        title = f"{name} is {state} its level of a year ago: how often that held for 6 months to 5 years"
        out.append(({"id": sid, "kind": "trend", "category": {"gold": "commodities", "cl": "energy", "btc": "crypto", "6e": "economics"}.get(mid, "equities"),
                     "areas": [], "title": title, "published_at": iso(now), "event_at": last,
                     "entities": {"markets": [mid]}, "markets": [mid],
                     "facts": [F(f"{name} closed at {M.fmt(closes[last], dec)} {unit} on {day_label(last)}, against "
                                 f"{M.fmt(ago, dec)} 252 sessions earlier ({(closes[last] / ago - 1) * 100:+.1f}%).")],
                     "why": [F("In Displace's history for this market, sampled monthly, the same 12-month state still "
                               "held after: " + "; ".join(lines) + ".", "estimate")],
                     "counter": [F("Monthly samples overlap, so the cases are not independent.", "interpretation"),
                                 F("Long horizons include very different regimes (rates, regulation, market structure).", "open_question")],
                     "next": [F("Each checkpoint is graded on the session nearest its date.", "open_question")],
                     "use_if": "You invest for months or years and want a base rate, not a call.",
                     "no_action_if": "You trade intraday.",
                     "sources": [source(f"{name} daily closes (Displace cache)", "https://grobentham.github.io/displace/research-hub.html",
                                        "Displace from Yahoo Finance", retrieved=iso(now), limit="Continuous futures; contract rolls add small jumps.")],
                     "rank": 45, "horizon": "long"}, claims))
    return out
