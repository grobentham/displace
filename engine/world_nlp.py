"""Rule-based text handling for Displace World: classification, entities, de-duplication and spikes.

No language model. Everything is keyword and arithmetic, so the same input always gives the same output and
every decision can be traced to a rule in engine/world/taxonomy.json or engine/world/entities.json.
"""
import json
import math
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = json.loads((ROOT / "engine/world/taxonomy.json").read_text())
ENTITIES = json.loads((ROOT / "engine/world/entities.json").read_text())
CATEGORIES = {c["id"]: c for c in TAXONOMY["categories"]}
STOP = set("""a an the and or but of to in on for with at by from as is are was were be been it its this that these those
into over after before about than more most new says say said will would could may might can has have had not no
amid also up down out off how why what who when where which while just now year years week amid via per""".split())


def norm(text):
    return " " + re.sub(r"[^a-z0-9&.+-]+", " ", text.lower()) + " "


def _has(padded, phrase):
    p = phrase.lower().strip()
    if not p:
        return False
    if p.endswith(" "):                              # "ev " style keywords: match whole word only
        p = p.strip()
    return (" " + p + " ") in padded or (" " + p + "s ") in padded or (" " + p + ". ") in padded


def classify(text):
    """[(category id, [area ids])] for every category whose keywords appear, strongest first."""
    padded = norm(text)
    out = []
    for c in TAXONOMY["categories"]:
        areas = [a["id"] for a in c["areas"] if any(_has(padded, k) for k in a["keywords"])]
        if areas:
            out.append((c["id"], areas))
    out.sort(key=lambda x: -len(x[1]))
    return out


def entities(text):
    padded = norm(text)
    found = {"companies": [], "countries": [], "markets": []}
    for co in ENTITIES["companies"]:
        if any(_has(padded, a) for a in co["aliases"]) or (" " + co["ticker"].lower() + " ") in padded and len(co["ticker"]) > 2:
            found["companies"].append(co["ticker"])
    for c in ENTITIES["countries"]:
        if any(_has(padded, a) for a in c["aliases"]):
            found["countries"].append(c["code"])
    return found


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2 and w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def cluster(articles, threshold=0.35):
    """Group repeated reports of one event (wire copies, rewrites). Greedy and order-stable."""
    groups = []
    for art in sorted(articles, key=lambda a: (a["seen"], a["url"])):
        t = tokens(art["title"])
        best, score = None, 0.0
        for g in groups:
            s = jaccard(t, g["tokens"])
            if s > score:
                best, score = g, s
        if best is not None and score >= threshold:
            best["articles"].append(art)
            best["tokens"] |= t
        else:
            groups.append({"tokens": set(t), "articles": [art]})
    out = []
    for g in groups:
        arts = g["articles"]
        lead = arts[0]
        out.append({"title": lead["title"], "first_seen": lead["seen"], "articles": arts,
                    "outlets": len({a["domain"] for a in arts}), "countries": sorted({a["country"] for a in arts if a["country"]}),
                    "languages": sorted({a["language"] for a in arts if a["language"]})})
    out.sort(key=lambda g: (-g["outlets"], g["first_seen"]))
    return out


def robust_z(x, history):
    """(x - median) / (1.4826 * MAD), with the scale floored at sqrt(median); None if history is too short."""
    if len(history) < 14:
        return None
    med = statistics.median(history)
    mad = statistics.median([abs(h - med) for h in history])
    scale = max(1.4826 * mad, math.sqrt(med) if med > 0 else 0)   # counts are at least Poisson-noisy
    if scale == 0:
        return None
    return (x - med) / scale


SPIKE = {"ratio": 1.8, "z": 3.0, "min_articles": 40, "baseline_days": 28}
PERSIST = {"ratio": 1.3, "days": 7}


def spike(days, day):
    """Is `day` an unusual coverage day? Compares it with the 28 days before it (median and MAD)."""
    keys = sorted(k for k in days if k < day)[-SPIKE["baseline_days"]:]
    if day not in days or len(keys) < 21:
        return None
    hist = [days[k] for k in keys]
    x = days[day]
    base = statistics.median(hist)
    z = robust_z(x, hist)
    if base <= 0 or z is None:
        return None
    ratio = x / base
    hit = ratio >= SPIKE["ratio"] and z >= SPIKE["z"] and x >= SPIKE["min_articles"]
    return {"day": day, "count": x, "baseline": base, "ratio": round(ratio, 2), "z": round(z, 1), "spike": hit}


def persists(days, start_day, baseline):
    """Average daily coverage over the PERSIST window from start_day (exclusive); None until complete."""
    keys = sorted(k for k in days if k > start_day)[:PERSIST["days"]]
    if len(keys) < PERSIST["days"]:
        return None
    avg = sum(days[k] for k in keys) / len(keys)
    return {"average": round(avg, 1), "ratio": round(avg / baseline, 2), "held": avg >= PERSIST["ratio"] * baseline}


def spike_base_rate(histories):
    """How often past spikes (same rule, every category pooled) stayed elevated for the next week."""
    n = held = 0
    for days in histories:
        prev = False
        for day in sorted(days):
            s = spike(days, day)
            now_spike = bool(s and s["spike"])
            first = now_spike and not prev          # count an episode once, on its first day
            prev = now_spike
            if first:
                p = persists(days, day, s["baseline"])
                if p is not None:
                    n += 1
                    held += p["held"]
    return {"n": n, "hits": held}
