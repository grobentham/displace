"""ES / NQ divergence (SMT): when one index makes a new high or low and the other does not.

Two definitions, both mechanical so every case can be checked on a chart:

  swing  At a confirmed swing high (the bar's high is the highest of K bars either side), compare each market's
         high around this swing with its high around the previous swing high. Bearish divergence: one market made
         a higher high and the other did not. Swing lows the same way, bullish.
  level  Each trading day has reference levels for both markets: the previous day's high and low, the Asia range
         (20:00-00:00 New York) and the London range (02:00-05:00). When one market trades through its level and
         the other has still not traded through its own K bars later, that is a divergence at that level.

For every past divergence the outcome is measured: did NQ (and ES) move in the divergence's direction over the
next 60 minutes and 2 hours (5-minute bars) or 3 and 6 hours (hourly bars)? Each type is compared with the base
rate of all bars, with a 95% Wilson interval. The page says "no edge shown" unless the whole interval clears the
base rate. This is a research measurement, not a trade signal.

    python engine/smt.py      reads engine/cache/bars (ES and NQ), writes site/data/smt/current.json
"""
import datetime as dt
import json
import math
import os
import sys
from collections import defaultdict

import bars
import exchange as X

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "site", "data", "smt", "current.json")
NY = X.NY
SETTINGS = {  # timeframe: pivot half-width K, look-back for the previous swing (bars), outcome horizons (bars)
    "5m": {"k": 3, "lookback": 48, "horizons": (12, 24), "labels": ("60 min", "2 hours")},
    "1h": {"k": 2, "lookback": 24, "horizons": (3, 6), "labels": ("3 hours", "6 hours")},
}
LEVELS = (("pdh", "pdl", "previous day"), ("asia_h", "asia_l", "Asia range"), ("london_h", "london_l", "London range"))


def wilson(hits, n, z=1.96):
    if n == 0:
        return None, None
    p = hits / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def aligned(nq, es):
    """Bars both markets have, oldest first: [(time NY, nq bar, es bar)] with bar = (o, h, l, c)."""
    e = {t: b for t, *b in es}
    return [(t, tuple(b), tuple(e[t])) for t, *b in nq if t in e]


_DAY = {}


def trade_date(t):
    key = (t.date(), t.hour >= 18)
    if key not in _DAY:
        d = X.session_for("nq", t)
        _DAY[key] = d.isoformat() if d else None
    return _DAY[key]


def session_name(t):
    h = t.hour + t.minute / 60
    if 9.5 <= h < 16:
        return "New York"
    if 2 <= h < 5:
        return "London"
    if h >= 20 or h < 0.01:
        return "Asia"
    return "Other"


def pivots(rows, side, k):
    """Indices of confirmed swing highs (side 'high', column 1) or lows (side 'low', column 2) for one market."""
    col = 1 if side == "high" else 2
    out = []
    for i in range(k, len(rows) - k):
        v = rows[i][col]
        left = [rows[j][col] for j in range(i - k, i)]
        right = [rows[j][col] for j in range(i + 1, i + k + 1)]
        if side == "high" and v > max(left) and v >= max(right):
            out.append(i)
        if side == "low" and v < min(left) and v <= min(right):
            out.append(i)
    return out


def window(rows, i, k, col, fn):
    return fn(rows[j][col] for j in range(max(0, i - k), min(len(rows), i + k + 1)))


def swing_divergences(joint, k, lookback):
    nq = [b for _, b, _ in joint]
    es = [b for _, _, b in joint]
    found = {}
    for side, col, fn in (("high", 1, max), ("low", 2, min)):
        for mkt, rows in (("NQ", nq), ("ES", es)):
            piv = pivots(rows, side, k)
            for a, b in zip(piv, piv[1:]):
                if b - a > lookback or b - a <= k:
                    continue
                n_now, n_prev = window(nq, b, k, col, fn), window(nq, a, k, col, fn)
                e_now, e_prev = window(es, b, k, col, fn), window(es, a, k, col, fn)
                if side == "high":
                    nq_new, es_new = n_now > n_prev, e_now > e_prev
                else:
                    nq_new, es_new = n_now < n_prev, e_now < e_prev
                if nq_new == es_new:
                    continue
                if any(f["direction"] == ("bearish" if side == "high" else "bullish") and abs(f["pivot_index"] - b) <= k
                       for f in found.values()):
                    continue                                    # one record per swing, whichever market found it
                found[(side, b)] = {"index": b + k, "pivot_index": b, "type": "swing",
                              "direction": "bearish" if side == "high" else "bullish",
                              "leader": "NQ" if nq_new else "ES", "laggard": "ES" if nq_new else "NQ",
                              "level": f"swing {side}", "nq_prev": n_prev, "nq_now": n_now, "es_prev": e_prev, "es_now": e_now}
    return sorted(found.values(), key=lambda d: d["index"])


def day_levels(joint):
    """{trade date: {level: (nq value, es value)}} and the bar index each level becomes known."""
    days = defaultdict(list)
    for i, (t, n, e) in enumerate(joint):
        d = trade_date(t)
        if d:
            days[d].append(i)
    out = {}
    order = sorted(days)
    for di, d in enumerate(order):
        idx = days[d]
        lv = {}
        if di > 0:
            prev = days[order[di - 1]]
            lv["pdh"] = (max(joint[i][1][1] for i in prev), max(joint[i][2][1] for i in prev), idx[0])
            lv["pdl"] = (min(joint[i][1][2] for i in prev), min(joint[i][2][2] for i in prev), idx[0])
        for name, (h0, h1) in (("asia", (20, 24)), ("london", (2, 5))):
            part = [i for i in idx if h0 <= joint[i][0].hour < h1]
            if part:
                after = part[-1] + 1
                lv[name + "_h"] = (max(joint[i][1][1] for i in part), max(joint[i][2][1] for i in part), after)
                lv[name + "_l"] = (min(joint[i][1][2] for i in part), min(joint[i][2][2] for i in part), after)
        out[d] = {"bars": idx, "levels": lv}
    return out


def level_divergences(joint, k, days=None):
    days = days or day_levels(joint)
    found = []
    for d, info in days.items():
        idx = info["bars"]
        for hi, lo, label in LEVELS:
            for name, side in ((hi, "high"), (lo, "low")):
                if name not in info["levels"]:
                    continue
                nq_lv, es_lv, start = info["levels"][name]
                col = 1 if side == "high" else 2
                through = (lambda v, lv: v > lv) if side == "high" else (lambda v, lv: v < lv)
                live = [i for i in idx if i >= start]
                first_n = next((i for i in live if through(joint[i][1][col], nq_lv)), None)
                first_e = next((i for i in live if through(joint[i][2][col], es_lv)), None)
                firsts = [(i, m) for i, m in ((first_n, "NQ"), (first_e, "ES")) if i is not None]
                if not firsts:
                    continue
                i, leader = min(firsts)
                other = first_e if leader == "NQ" else first_n
                if other is not None and other <= i + k:
                    continue                                  # both took it: no divergence
                if i + k > idx[-1]:
                    continue                                  # not confirmed yet (near the session end or right now)
                found.append({"index": i + k, "pivot_index": i, "type": "level",
                              "direction": "bearish" if side == "high" else "bullish", "leader": leader,
                              "laggard": "ES" if leader == "NQ" else "NQ", "level": f"{label} {side}",
                              "nq_level": nq_lv, "es_level": es_lv,
                              "laggard_took_it_later": other is not None})
    return sorted(found, key=lambda d: d["index"])


def outcome(joint, i, h, direction):
    if i + h >= len(joint):
        return None
    sign = -1 if direction == "bearish" else 1
    n0, n1 = joint[i][1][3], joint[i + h][1][3]
    e0, e1 = joint[i][2][3], joint[i + h][2][3]
    return {"nq_points": round(n1 - n0, 2), "es_points": round(e1 - e0, 2),
            "nq_right": sign * (n1 - n0) > 0, "es_right": sign * (e1 - e0) > 0}


def base_rates(joint, h):
    up = n = 0
    for i in range(len(joint) - h):
        d = joint[i + h][1][3] - joint[i][1][3]
        if d != 0:
            n += 1
            up += d > 0
    return {"n": n, "up": round(up / n, 3) if n else None}


def stats(events, joint, horizons, labels):
    out = []
    groups = defaultdict(list)
    for e in events:
        groups[(e["type"], e["direction"])].append(e)
        groups[(e["type"], e["direction"], e["session"])].append(e)
    for key, rows in sorted(groups.items()):
        for h, lab in zip(horizons, labels):
            res = [r["outcomes"].get(str(h)) for r in rows]
            res = [r for r in res if r]
            n = len(res)
            hits = sum(r["nq_right"] for r in res)
            base = base_rates(joint, h)["up"]
            if base is not None and key[1] == "bearish":
                base = round(1 - base, 3)
            lo, hi = wilson(hits, n)
            if n < 30:
                verdict = "too few cases"
            elif lo is not None and base is not None and lo > base:
                verdict = "better than the base rate"
            elif hi is not None and base is not None and hi < base:
                verdict = "worse than the base rate"
            else:
                verdict = "no edge shown"
            out.append({"type": key[0], "direction": key[1], "session": key[2] if len(key) > 2 else "All",
                        "horizon": lab, "bars": h, "n": n, "hits": hits, "hit_rate": round(hits / n, 3) if n else None,
                        "ci95": [lo, hi], "base_rate": base, "verdict": verdict,
                        "avg_nq_points": round(sum(r["nq_points"] for r in res) / n, 2) if n else None})
    return out


def analyse(nq_rows, es_rows, interval, now):
    cfg = SETTINGS[interval]
    joint = aligned(nq_rows, es_rows)
    if len(joint) < 200:
        return None
    days = day_levels(joint)
    events = swing_divergences(joint, cfg["k"], cfg["lookback"]) + level_divergences(joint, cfg["k"], days)
    for e in events:
        t = joint[e["index"]][0]
        e["confirmed_at"] = t.isoformat(timespec="minutes")
        e["pivot_at"] = joint[e["pivot_index"]][0].isoformat(timespec="minutes")
        e["trade_date"] = trade_date(t)
        e["session"] = session_name(joint[e["pivot_index"]][0])
        e["nq_close"], e["es_close"] = joint[e["index"]][1][3], joint[e["index"]][2][3]
        e["outcomes"] = {str(h): o for h in cfg["horizons"] if (o := outcome(joint, e["index"], h, e["direction"]))}
        for k in ("index", "pivot_index"):
            e.pop(k)
    events.sort(key=lambda e: e["confirmed_at"])
    today = trade_date(joint[-1][0])
    info = days.get(today, {"levels": {}, "bars": []})
    board = []
    for hi, lo, label in LEVELS:
        for name, side in ((hi, "high"), (lo, "low")):
            if name not in info["levels"]:
                continue
            nq_lv, es_lv, start = info["levels"][name]
            live = [i for i in info["bars"] if i >= start]
            col = 1 if side == "high" else 2
            pick = max if side == "high" else min
            nq_x = pick((joint[i][1][col] for i in live), default=None)
            es_x = pick((joint[i][2][col] for i in live), default=None)
            took = (lambda v, lv: v is not None and (v > lv if side == "high" else v < lv))
            board.append({"level": f"{label} {side}", "nq_level": round(nq_lv, 2), "es_level": round(es_lv, 2),
                          "nq_taken": took(nq_x, nq_lv), "es_taken": took(es_x, es_lv),
                          "active": bool(live)})
    chart = [[int(t.timestamp()), n[3], e[3]] for t, n, e in joint if trade_date(t) == today]
    return {"interval": interval, "bars": len(joint), "from": joint[0][0].isoformat(timespec="minutes"),
            "to": joint[-1][0].isoformat(timespec="minutes"), "trade_date": today, "settings": cfg,
            "today": [e for e in events if e["trade_date"] == today],
            "recent": list(reversed(events[-60:])), "count": len(events),
            "stats": stats(events, joint, cfg["horizons"], cfg["labels"]), "levels": board, "chart": chart}


def build(now=None, loader=bars.load):
    now = now or dt.datetime.now(dt.timezone.utc)
    out = {"version": 1, "asof": now.isoformat(timespec="minutes"), "timeframes": {},
           "method": __doc__.split("For every past")[0].strip(),
           "source": "Yahoo Finance delayed futures bars (NQ=F, ES=F), archived by Displace's engine",
           "policy": "Research measurement of past divergences. Not a trade signal and not advice."}
    for interval in SETTINGS:
        res = analyse(loader("nq", interval), loader("es", interval), interval, now)
        if res:
            out["timeframes"][interval] = res
    return out


def check(doc):
    p = []
    if not isinstance(doc.get("timeframes"), dict):
        return ["no timeframes"]
    for k, tf in doc["timeframes"].items():
        for s in tf.get("stats", []):
            if s["n"] and not (0 <= s["hits"] <= s["n"]):
                p.append(f"{k}: impossible hit count")
        for e in tf.get("today", []) + tf.get("recent", []):
            if e["direction"] not in ("bearish", "bullish") or e["leader"] == e["laggard"]:
                p.append(f"{k}: malformed divergence")
                break
    return p


def main():
    doc = build()
    if not doc["timeframes"]:
        if os.path.exists(OUT):
            print("smt: not enough ES and NQ bars this run; keeping the last published file")
            return 1
        print("smt: not enough ES and NQ bars yet; publishing an empty record")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    for k, tf in doc["timeframes"].items():
        print(f"smt: {k} {tf['bars']} bars, {tf['count']} divergences, {len(tf['today'])} today")
    return 0


if __name__ == "__main__":
    sys.exit(main())
