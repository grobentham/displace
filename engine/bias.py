"""Bias of the day for NQ and gold, from the previous day's candle (the ICT daily-bias read), with its record.

Each morning, before the New York futures session opens (18:00 New York), the last finished daily candle is
compared with the one before it:

  closed above the prior day's high      -> long,  draw on liquidity = the new day's high
  closed below the prior day's low       -> short, draw = the new day's low
  took the prior high, closed back inside -> short (a failed breakout), draw = the day's low
  took the prior low, closed back inside  -> long  (a failed breakdown), draw = the day's high
  inside day / took both sides            -> no bias, wait for one side to be taken

Every rule is checked against every day since 2000 (Yahoo daily futures candles, free): how often the next day
closed in the bias direction and how often it reached the draw, next to the same rates on all days, so a rule
that only matches what markets do anyway is labelled as such. Live calls are logged and scored the day after.

Writes site/data/bias/current.json and site/data/bias/log.json.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
OUT = os.path.join(DATA, "bias", "current.json")
LOG = os.path.join(DATA, "bias", "log.json")
CACHE_DIR = os.path.join(HERE, "cache", "daily")
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
MARKETS = {"nq": ("NQ%3DF", "NQ", "Nasdaq-100 futures"), "gold": ("GC%3DF", "Gold", "COMEX gold futures")}
SESSION_END = 17  # futures day ends 17:00 New York
RANGE_DAYS = 20
RECENT = 500      # "lately" = the last ~2 years of days
EDGE = 0.03       # beat the all-days rate by 3 points, with z >= 1.96, in the full history and lately


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- data

def _cache_path(m):
    return os.path.join(CACHE_DIR, f"{m}.json")


def load_cache(m):
    try:
        return json.load(open(_cache_path(m)))
    except (OSError, ValueError):
        return {"fetched": "", "days": {}}


def download(symbol, rng="max"):
    # an explicit span keeps daily candles; range=max quietly switches to monthly ones
    start = 946684800 if rng == "max" else int(time.time()) - 120 * 86400  # 2000-01-01, or the last ~4 months
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start}&period2={int(time.time()) + 86400}"
           f"&interval=1d")
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return parse(json.load(r))
        except Exception:
            if i == 2:
                raise
            time.sleep(3 * (i + 1))


def parse(doc):
    """Yahoo daily futures candles -> {trading date: [open, high, low, close]}."""
    r = doc["chart"]["result"][0]
    off = r.get("meta", {}).get("gmtoffset", 0) or 0
    q = r["indicators"]["quote"][0]
    out = {}
    for t, o, h, lo, c in zip(r["timestamp"], q["open"], q["high"], q["low"], q["close"]):
        if not (o and h and lo and c):
            continue
        d = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date()
        if d.weekday() >= 5:
            continue
        out[d.isoformat()] = [round(o, 2), round(max(h, o, c), 2), round(min(lo, o, c), 2), round(c, 2)]
    return out


def sync(m, now, fetch=download):
    c = load_cache(m)
    try:
        fresh = now - dt.datetime.fromisoformat(c["fetched"]) < dt.timedelta(minutes=50)
    except (KeyError, ValueError):
        fresh = False
    if not fresh:
        try:
            got = fetch(MARKETS[m][0], "max" if len(c["days"]) < 1000 else "3mo")
            if len(got) > 20:
                c["days"].update(got)  # the latest download wins, so a forming candle is replaced when it finishes
                c["fetched"] = now.isoformat(timespec="minutes")
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(_cache_path(m), "w") as fh:
                    json.dump({"fetched": c["fetched"], "days": dict(sorted(c["days"].items()))}, fh, separators=(",", ":"))
        except Exception as e:
            log(f"bias: {m} daily candles unavailable ({e!r}); using the archive")
    return c


def finished(days, now_ny):
    """Candles whose session has ended (a day's candle is final at 17:00 New York)."""
    today = now_ny.date()
    cut = today if now_ny.hour >= SESSION_END else today - dt.timedelta(days=1)
    return [(d, v) for d, v in sorted(days.items()) if dt.date.fromisoformat(d) <= cut]


# ---------------------------------------------------------------- the rules

CASES = {
    "close_above": ("long", "high", "Closed above the prior day's high"),
    "close_below": ("short", "low", "Closed below the prior day's low"),
    "failed_high": ("short", "low", "Took the prior day's high, then closed back inside"),
    "failed_low": ("long", "high", "Took the prior day's low, then closed back inside"),
    "inside": ("neutral", None, "Inside day: neither side of the prior day was taken"),
    "both": ("neutral", None, "Took both sides of the prior day and closed inside"),
}


def classify(prev, day):
    _, ph, pl, _ = prev
    _, h, l, c = day
    if c > ph:
        return "close_above"
    if c < pl:
        return "close_below"
    took_h, took_l = h > ph, l < pl
    if took_h and took_l:
        return "both"
    if took_h:
        return "failed_high"
    if took_l:
        return "failed_low"
    return "inside"


def zone(rows, i):
    """Premium or discount of the last 20 days' range, at day i's close."""
    win = rows[max(0, i - RANGE_DAYS + 1): i + 1]
    hi, lo = max(v[1] for _, v in win), min(v[2] for _, v in win)
    eq = (hi + lo) / 2
    return ("premium" if rows[i][1][3] > eq else "discount"), round(hi, 2), round(lo, 2), round(eq, 2)


def outcome(day, nxt, bias):
    """(closed in the bias direction, reached the draw) for the day after `day`.
    Direction is close-to-close: Yahoo's daily open for futures is unreliable (it often repeats the prior open)."""
    _, h, l, c = nxt
    if bias == "long":
        return c > day[3], h > day[1]
    return c < day[3], l < day[2]


def _rate(k, n):
    return round(k / n, 3) if n else None


def _z(k, n, p):
    if not n or p in (0, 1):
        return 0.0
    return (k / n - p) / math.sqrt(p * (1 - p) / n)


def study(rows):
    """Record of every rule on history, against the all-days base rates."""
    n_all = len(rows) - 2
    if n_all < 50:
        return {}
    base = {"up": 0, "high": 0, "low": 0}
    per = {k: [] for k in CASES}
    for i in range(1, len(rows) - 1):
        prev, day, nxt = rows[i - 1][1], rows[i][1], rows[i + 1][1]
        base["up"] += nxt[3] > day[3]
        base["high"] += nxt[1] > day[1]
        base["low"] += nxt[2] < day[2]
        k = classify(prev, day)
        bias = CASES[k][0]
        if bias == "neutral":
            per[k].append((i, None, None))
        else:
            d, w = outcome(day, nxt, bias)
            per[k].append((i, d, w))
    up, hi, lo = base["up"] / n_all, base["high"] / n_all, base["low"] / n_all
    out = {"days": n_all, "since": rows[0][0][:4], "base": {"up": round(up, 3), "high": round(hi, 3), "low": round(lo, 3)},
           "cases": {}}
    cut = len(rows) - 1 - RECENT
    for k, items in per.items():
        bias = CASES[k][0]
        rec = {"n": len(items)}
        if bias != "neutral" and items:
            pd = up if bias == "long" else 1 - up        # the direction rate on all days
            pw = hi if bias == "long" else lo            # the draw rate on all days
            dk = sum(1 for _, d, _ in items if d)
            wk = sum(1 for _, _, w in items if w)
            late = [x for x in items if x[0] >= cut]
            ldk = sum(1 for _, d, _ in late if d)
            rec.update({"dir": _rate(dk, len(items)), "draw": _rate(wk, len(items)),
                        "base_dir": round(pd, 3), "base_draw": round(pw, 3),
                        "late": {"n": len(late), "dir": _rate(ldk, len(late)),
                                 "draw": _rate(sum(1 for _, _, w in late if w), len(late))}})
            edge = (dk / len(items) - pd >= EDGE and _z(dk, len(items), pd) >= 1.96
                    and late and ldk / len(late) - pd >= EDGE / 2)
            rec["tested"] = bool(edge)
        out["cases"][k] = rec
    return out


# ---------------------------------------------------------------- today

def news_today(day_iso):
    try:
        ev = json.load(open(os.path.join(DATA, "calendar", "events.json")))["events"]
    except (OSError, ValueError, KeyError):
        return []
    return [{"time": e.get("time"), "title": e.get("title"), "impact": e.get("impact")}
            for e in ev if e.get("date") == day_iso and e.get("impact") == "high"]


def next_session(last_iso):
    d = dt.date.fromisoformat(last_iso) + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.isoformat()


WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def read(m, rows, st):
    """Today's bias for one market from its finished candles."""
    (pd_, prev), (yd, day) = rows[-2], rows[-1]
    k = classify(prev, day)
    bias, side, label = CASES[k]
    z, hi20, lo20, eq20 = zone(rows, len(rows) - 1)
    yname = WD[dt.date.fromisoformat(yd).weekday()]
    pname = WD[dt.date.fromisoformat(pd_).weekday()]
    named = label.replace("the prior day's", pname + "'s").replace("the prior day", pname)
    out = {"bias": bias, "case": k, "label": label, "named": f"{WD[dt.date.fromisoformat(yd).weekday()]} {named[0].lower() + named[1:]}",
           "candle": yd, "prior": pd_,
           "levels": {"pdh": day[1], "pdl": day[2], "pdc": day[3], "pdo": day[0], "prior_high": prev[1], "prior_low": prev[2],
                      "range_high": hi20, "range_low": lo20, "eq": eq20},
           "zone": z, "day_name": yname, "record": st.get("cases", {}).get(k, {})}
    if side:
        out["draw"] = {"level": day[1] if side == "high" else day[2], "name": f"{yname}'s {side}"}
        out["against"] = {"level": day[2] if side == "high" else day[1], "name": f"{yname}'s {'low' if side == 'high' else 'high'}"}
        out["fits_zone"] = (bias == "long" and z == "discount") or (bias == "short" and z == "premium")
    return out


def score_log(rows_by, entries):
    for e in entries:
        if "hit" in e or e["bias"] == "neutral":
            continue
        rows = rows_by.get(e["market"]) or []
        days = dict(rows)
        nxt = next((d for d, _ in rows if d > e["candle"]), None)
        if not nxt or e["candle"] not in days:
            continue
        d, w = outcome(days[e["candle"]], days[nxt], e["bias"])
        e.update({"day": nxt, "hit": int(d), "drawHit": int(w)})
    return entries


def summary(entries):
    done = [e for e in entries if "hit" in e]
    by = {}
    for e in done:
        b = by.setdefault(e["market"], {"calls": 0, "hits": 0, "draws": 0})
        b["calls"] += 1
        b["hits"] += e["hit"]
        b["draws"] += e["drawHit"]
    return {"calls": len(done), "hits": sum(e["hit"] for e in done), "draws": sum(e["drawHit"] for e in done),
            "byMarket": by, "recent": done[-10:][::-1]}


def run(now=None, fetch=download):
    now = now or dt.datetime.now(dt.timezone.utc)
    now_ny = now.astimezone(NY)
    try:
        entries = json.load(open(LOG)).get("entries", [])
    except (OSError, ValueError):
        entries = []
    markets, rows_by = {}, {}
    for m, (_, short, name) in MARKETS.items():
        c = sync(m, now, fetch)
        rows = finished(c["days"], now_ny)
        rows_by[m] = rows
        if len(rows) < 60:
            log(f"bias: not enough {m} history yet")
            continue
        st = study(rows)
        r = read(m, rows, st)
        r.update({"name": short, "full": name, "history": {k: st[k] for k in ("days", "since", "base")}})
        markets[m] = r
        if not any(e["market"] == m and e["candle"] == r["candle"] for e in entries):
            entries.append({"market": m, "candle": r["candle"], "for": next_session(r["candle"]), "bias": r["bias"],
                            "case": r["case"], "draw": (r.get("draw") or {}).get("level"),
                            "logged": now.isoformat(timespec="minutes")})
    if not markets:
        log("bias: nothing to publish; the last file stays live")
        return 1
    score_log(rows_by, entries)
    day = max(next_session(v["candle"]) for v in markets.values())
    doc = {"asof": now.isoformat(timespec="minutes"), "for": day, "markets": markets, "news": news_today(day),
           "live": summary(entries), "rules": {k: {"bias": v[0], "label": v[2]} for k, v in CASES.items()}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    with open(LOG, "w") as fh:
        json.dump({"entries": entries[-2000:]}, fh, separators=(",", ":"))
    for m, v in markets.items():
        rec = v["record"]
        log(f"bias: {m} {v['bias']} ({v['case']}) for {day}; history {rec.get('dir')} vs {rec.get('base_dir')} on {rec.get('n')} days")
    return 0


def main():
    try:
        return run()
    except Exception as e:  # never break the publish job
        log(f"bias: unexpected error ({e!r}); the last file stays live")
        return 0


if __name__ == "__main__":
    sys.exit(main())
