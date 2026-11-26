"""Grade Displace World claims by the rule frozen inside each claim. No judgement calls.

Each grader returns None while the answer is not yet knowable, or a tuple
(label, observed values, what happened). Labels: hit, miss, not_assessable.
A claim whose data never arrives is marked not_assessable 30 days after its due date, with the reason.
"""
import datetime as dt
import statistics

import world_markets as M
import world_nlp as N
from world_ledger import parse


def num(v):
    a = abs(v)
    return f"{v:,.0f}" if a >= 1000 else f"{v:,.2f}" if a >= 10 else f"{v:.4f}".rstrip("0").rstrip(".")


def _closes(rule, ctx):
    if rule.get("source") == "series":
        return ctx["series"](rule["id"])
    return ctx["market"](rule["id"])


def close_above_after(rule, ctx, now):
    closes = _closes(rule, ctx)
    target = M.session_after(closes, rule["day"], rule["sessions"])
    if not target:
        return None
    v = closes[target]
    hit = v > rule["level"]
    return ("hit" if hit else "miss", {"session": target, "close": v, "level": rule["level"]},
            f"The close on {target} was {num(v)}, {'above' if hit else 'not above'} {num(rule['level'])}.")


def moves_stay_wide(rule, ctx, now):
    closes = _closes(rule, ctx)
    mv = M.moves(closes, rule["how"])
    idx = next((i for i, (d, _) in enumerate(mv) if d == rule["day"]), None)
    if idx is None or idx < M.LOOKBACK or idx + rule["sessions"] >= len(mv):
        return None
    before = statistics.mean(abs(m) for _, m in mv[idx - M.LOOKBACK:idx])
    after = statistics.mean(abs(m) for _, m in mv[idx + 1:idx + 1 + rule["sessions"]])
    hit = after > before
    return ("hit" if hit else "miss", {"after": round(after, 4), "before": round(before, 4), "through": mv[idx + rule["sessions"]][0]},
            f"The next {rule['sessions']} sessions averaged {after:.3g} a day against {before:.3g} before.")


def stock_reaction_wide(rule, ctx, now):
    closes = ctx["stock"](rule["ticker"])
    r = M.reaction_session(closes, parse(rule["accepted"]))
    if not r:
        return None
    keys = list(closes)
    i = keys.index(r)
    if i < M.LOOKBACK + 1:
        return ("not_assessable", {"reason": "price history too short"}, "Not enough price history to compare.")
    rets = [abs(closes[keys[j]] / closes[keys[j - 1]] - 1) * 100 for j in range(i - M.LOOKBACK, i)]
    med = statistics.median(rets)
    move = (closes[r] / closes[keys[i - 1]] - 1) * 100
    hit = abs(move) > med
    return ("hit" if hit else "miss", {"session": r, "move_pct": round(move, 2), "median_abs_pct": round(med, 2)},
            f"{rule['ticker']} moved {move:+.2f}% on {r}, against a median absolute move of {med:.2f}%.")


def coverage_persists(rule, ctx, now):
    days = ctx["coverage"](rule["category"])
    p = N.persists(days, rule["day"], rule["baseline"])
    if p is None:
        return None
    return ("hit" if p["held"] else "miss", p,
            f"Coverage averaged {p['average']:,.0f} articles a day ({p['ratio']:.2f}x the old baseline).")


def fr_date_unchanged(rule, ctx, now):
    if now.date().isoformat() < rule["value"]:
        return None
    doc = ctx["fr_doc"](rule["number"])
    if doc is None:
        return None                                   # not refetched yet
    if doc == "missing":
        return ("miss", {"document": "not found"}, "The document could no longer be found on the Federal Register.")
    now_value = doc.get(rule["field"])
    hit = now_value == rule["value"]
    return ("hit" if hit else "miss", {rule["field"]: now_value},
            f"The Federal Register lists {rule['field'].replace('_', ' ')} as {now_value or 'not stated'}.")


def aftershock(rule, ctx, now):
    found = ctx["aftershocks"](rule)
    if found is None:
        return None
    if found:
        best = max(found, key=lambda q: q["mag"])
        return ("hit", {"count": len(found), "largest": best["mag"]},
                f"USGS recorded {len(found)} magnitude 5.0+ aftershock(s); the largest was M{best['mag']:.1f}.")
    if now < parse(rule["end"]):
        return None
    return ("miss", {"count": 0}, "USGS recorded no magnitude 5.0+ aftershock within 300 km in 7 days.")


def psi_below(rule, ctx, now):
    start, end = parse(rule["start"]), parse(rule["end"])
    for stamp, value in ctx["psi"]():
        try:
            t = parse(stamp)
        except ValueError:
            continue
        if start <= t <= end and value <= rule["threshold"]:
            return ("hit", {"time": stamp, "psi": value}, f"The 24-hour PSI was {value:.0f} at {stamp}.")
    if now <= end:
        return None
    return ("miss", {}, "The 24-hour PSI stayed above 100 for the whole 72 hours in Displace's readings.")


def trend_holds(rule, ctx, now):
    closes = ctx["market"](rule["id"])
    target = M.session_after(closes, rule["day"], rule["sessions"])
    if not target:
        return None
    keys = list(closes)
    i = keys.index(target)
    held = (closes[target] > closes[keys[i - 252]]) == (rule["state"] == "above")
    return ("hit" if held else "miss", {"session": target, "close": closes[target], "year_ago": closes[keys[i - 252]]},
            f"On {target} the close was {num(closes[target])} against {num(closes[keys[i - 252]])} a year earlier.")


GRADERS = {"close_above_after": close_above_after, "moves_stay_wide": moves_stay_wide,
           "stock_reaction_wide": stock_reaction_wide, "coverage_persists": coverage_persists,
           "fr_date_unchanged": fr_date_unchanged, "aftershock": aftershock, "psi_below": psi_below,
           "trend_holds": trend_holds}


def grade_all(ledger, ctx, now):
    """Grade every open claim. Returns the number of new assessments."""
    changed = 0
    for cid, c in sorted(ledger.claims.items()):
        if ledger.current(cid) != "unresolved":
            continue
        grader = GRADERS.get(c["rule"]["type"])
        result = grader(c["rule"], ctx, now) if grader else None
        if result is None:
            due = dt.date.fromisoformat(c["due"][:10])
            if now.date() > due + dt.timedelta(days=30):
                result = ("not_assessable", {"reason": "data unavailable 30 days after the due date"},
                          "The data needed to grade this claim did not arrive within 30 days of its due date.")
            else:
                continue
        label, observed, happened = result
        same = [x for x in ledger.claims.values() if x["rule"]["type"] == c["rule"]["type"] and x["id"] != cid]
        hits = sum(ledger.current(x["id"]) == "hit" for x in same) + (label == "hit")
        done = sum(ledger.current(x["id"]) in ("hit", "miss") for x in same) + (label in ("hit", "miss"))
        learned = f"Claims of this type have now come true {hits} of {done} times." if done else ""
        if c.get("probability") is not None and label in ("hit", "miss"):
            learned += f" This one carried a {c['probability']:.0%} historical probability."
        still_open = "" if label in ("hit", "miss") else "Waiting for the data to arrive."
        changed += ledger.assess(cid, label, observed, happened, now, learned.strip(), still_open)
    return changed
