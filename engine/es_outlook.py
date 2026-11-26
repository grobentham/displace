"""Indicative ES futures outlook from delayed five-minute bars."""
import datetime as dt
import json
import math
import urllib.request
from statistics import median

from exchange import NY

URL = "https://query1.finance.yahoo.com/v8/finance/chart/ES%3DF?range=30d&interval=5m"
SPAN = 20


def load_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Displace outlook)"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def day_key(stamp):
    return (stamp + dt.timedelta(hours=6)).date()


def bars(raw=None):
    """[(utc datetime, o, h, l, c, volume)] of 5-minute futures bars."""
    res = (raw or load_json(URL))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((dt.datetime.fromtimestamp(t, dt.timezone.utc), o, h, l, c, (q.get("volume") or [0] * len(res["timestamp"]))[i] or 0))
    return out


def despike(b):
    """Clip one-bar spikes (a wick that is most of its bar, over twice the median bar range and four times any wick
    within three bars either side), as engine/orb930.py does for minute bars: on 23 Nov 2026 a 09:30 print at 27,137
    would otherwise stand as 'yesterday's high'."""
    if len(b) < 10:
        return b
    rng = sorted(x[2] - x[3] for x in b)
    med = rng[len(rng) // 2]
    out = list(b)

    def wick(k):
        t_, o, h, l, c, v = b[k]
        return h - max(o, c), min(o, c) - l
    for j, (t_, o, h, l, c, v) in enumerate(b):
        up, dn = wick(j)
        nb = [wick(k) for k in range(max(0, j - 3), min(len(b), j + 4)) if k != j]
        if med > 0 and up > 0.8 * (h - l) and up > 2 * med and up > 4 * max(x[0] for x in nb):
            h = max(o, c) + med
        if med > 0 and dn > 0.8 * (b[j][2] - l) and dn > 2 * med and dn > 4 * max(x[1] for x in nb):
            l = min(o, c) - med
        out[j] = (t_, o, h, l, c, v)
    return out


def phase(ny):
    m = ny.hour * 60 + ny.minute
    if ny.weekday() == 5 or (ny.weekday() == 6 and ny.hour < 18) or (ny.weekday() == 4 and m >= 17 * 60):
        return "closed", "The market is closed for the weekend."
    if 17 * 60 <= m < 18 * 60:
        return "break", "Daily break (17:00-18:00 New York)."
    if m >= 18 * 60 or m < 3 * 60:
        return "asia", "Overnight: Asian session, usually the quietest hours."
    if m < 8 * 60:
        return "london", "Overnight: London session."
    if m < 9 * 60 + 30:
        return "premarket", "Pre-market: US data releases often land at 08:30 New York."
    if m < 10 * 60:
        return "open", "The cash open: the busiest half hour of the day."
    if m < 11 * 60 + 30:
        return "morning", "New York morning."
    if m < 14 * 60:
        return "midday", "Midday: usually slower."
    if m < 16 * 60:
        return "afternoon", "Afternoon into the 16:00 cash close."
    return "after", "After the cash close."


def outlook(b, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    ny = now.astimezone(NY)
    dp = 0
    rows = [(x[0].astimezone(NY),) + tuple(x[1:]) for x in despike(b)]
    by_day = {}
    for r in rows:
        by_day.setdefault(day_key(r[0]), []).append(r)
    keys = sorted(by_day)
    if len(keys) < 3:
        return None
    today, prev = keys[-1], keys[-2]
    T = by_day[today]
    P = by_day[prev]
    last = T[-1][4]
    hi, lo = max(r[2] for r in T), min(r[3] for r in T)
    # typical day range: EWMA of daily log ranges over the complete days held
    a = 2 / (SPAN + 1)
    s = None
    for k in keys[:-1]:
        d = by_day[k]
        r_ = math.log(max(x[2] for x in d) / min(x[3] for x in d))
        s = r_ if s is None else math.sqrt(a * r_ * r_ + (1 - a) * s * s)
    typical = last * (math.exp(s) - 1)
    if typical <= 0:
        return None
    used = (hi - lo) / typical
    # yesterday's levels (the 09:30-16:00 cash session) and today's overnight and opening range
    rth = [r for r in P if (9, 30) <= (r[0].hour, r[0].minute) < (16, 0)] or P
    p_hi, p_lo, p_close = max(r[2] for r in rth), min(r[3] for r in rth), rth[-1][4]
    on = [r for r in T if r[0].hour >= 18 or (r[0].hour, r[0].minute) < (9, 30)]
    orng = [r for r in T if (9, 30) <= (r[0].hour, r[0].minute) < (10, 0)]
    cash = [r for r in T if (r[0].hour, r[0].minute) >= (9, 30) and r[0].hour < 17]
    vw_src = cash if cash else T
    vol = sum(r[5] for r in vw_src)
    vwap = (sum((r[2] + r[3] + r[4]) / 3 * r[5] for r in vw_src) / vol) if vol else None
    # the last hour, against the same hour's usual range
    hr = [r for r in T if r[0] > T[-1][0] - dt.timedelta(minutes=60)]
    move = hr[-1][4] - hr[0][1]
    same = []
    for k in keys[:-1]:
        h_ = [r for r in by_day[k] if (r[0].hour, r[0].minute) <= (T[-1][0].hour, T[-1][0].minute)
              and r[0].time() > (T[-1][0] - dt.timedelta(minutes=60)).time()] if T[-1][0].hour >= 1 else []
        if len(h_) >= 6:
            same.append(max(x[2] for x in h_) - min(x[3] for x in h_))
    usual_hour = float(median(same)) if same else 0
    busy = (max(r[2] for r in hr) - min(r[3] for r in hr)) / usual_hour if usual_hour > 0 else None
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5
    levels = [("Yesterday's high", p_hi), ("Yesterday's low", p_lo), ("Yesterday's close", p_close),
              ("Today's high", hi), ("Today's low", lo)]
    if on and len(on) < len(T):
        levels += [("Overnight high", max(r[2] for r in on)), ("Overnight low", min(r[3] for r in on))]
    if len(orng) >= 6:
        levels += [("Opening-range high", max(r[2] for r in orng)), ("Opening-range low", min(r[3] for r in orng))]
    if vwap:
        levels.append(("VWAP", vwap))
    threshold = 0.5
    above = sorted([(v - last, n, v) for n, v in levels if v - last > threshold])[:2]
    below = sorted([(last - v, n, v) for n, v in levels if last - v > threshold])[:2]
    ph, ph_text = phase(ny)
    chg = (last / p_close - 1) * 100
    trend = ("up" if move > 0.15 * typical / math.sqrt(6.5) else "down" if move < -0.15 * typical / math.sqrt(6.5)
             else "sideways")
    lines = [f"ES {last:,.2f}, {chg:+.2f}% against yesterday's close ({p_close:,.2f}).",
             f"Today's range is {hi - lo:,.{dp}f} points, {used:.0%} of a normal day ({typical:,.{dp}f})"
             + (": most of a usual day's movement is done." if used >= 0.8 else
                ": well over half of a usual day's movement is done." if used >= 0.55 else
                ": there is usually plenty of movement still to come."),
             f"Price is in the {'top' if pos >= 0.67 else 'bottom' if pos <= 0.33 else 'middle'} third of today's range"
             + (f", {'above' if last > vwap else 'below'} the session VWAP ({vwap:,.2f})." if vwap else ".")]
    lines.append(f"Last hour: {move:+,.{dp}f} points ({trend})"
                 + (f", {'busier than' if busy > 1.3 else 'quieter than' if busy < 0.7 else 'about as busy as'} usual for this hour"
                    f" ({busy:.1f}x)." if busy else "."))
    near = ", ".join(f"{n} {v:,.2f} ({'+' if d_ > 0 else ''}{d_:,.{dp}f})" for d_, n, v in
                     [(x[0], x[1], x[2]) for x in above] + [(-x[0], x[1], x[2]) for x in below])
    if near:
        lines.append("Nearest levels: " + near + ".")
    # the lean: what price is doing now (bullish, bearish or consolidating), from five plain checks. A reading of
    # the tape, not a forecast: Iron Brain has tested no edge in it.
    five = keys[-6:-1]
    week = (last / by_day[five[0]][0][1] - 1) * 100 if five else 0.0
    unit = 0.15 * typical / math.sqrt(6.5)          # a modest hourly move for this market today
    checks = [("against yesterday's close", 1 if chg > 0.1 else -1 if chg < -0.1 else 0),
              ("against VWAP", (1 if last > vwap else -1) if vwap and abs(last - vwap) > 0.25 * unit else 0),
              ("in today's range", 1 if pos >= 0.67 else -1 if pos <= 0.33 else 0),
              ("over the last hour", 1 if move > unit else -1 if move < -unit else 0),
              ("over five days", 1 if week > 0.5 else -1 if week < -0.5 else 0)]
    score = sum(v for _, v in checks)
    quiet = busy is not None and busy < 0.7 and abs(move) < unit
    if abs(score) <= 1 and (quiet or abs(move) < unit):
        lean = "consolidating"                      # a quiet hour never overrides a clear majority of the checks
    elif score >= 2:
        lean = "bullish"
    elif score <= -2:
        lean = "bearish"
    else:
        lean = "mixed"
    strength = "clearly" if abs(score) >= 4 else "leaning" if abs(score) >= 2 else ""
    pro = [n for n, v in checks if v == (1 if score > 0 else -1) and v != 0]
    con = [n for n, v in checks if v == (-1 if score > 0 else 1) and v != 0]
    lean_text = {"bullish": f"{'Clearly' if strength == 'clearly' else 'Leaning'} bullish: price is up " + ", ".join(pro)
                            + (f"; against it: down {', '.join(con)}" if con else "") + ".",
                 "bearish": f"{'Clearly' if strength == 'clearly' else 'Leaning'} bearish: price is down " + ", ".join(pro)
                            + (f"; against it: up {', '.join(con)}" if con else "") + ".",
                 "consolidating": "Consolidating: " + ("a quiet, narrow last hour" if quiet else "no clear direction")
                                  + f" ({score:+d} of {len(checks)} checks).",
                 "mixed": f"Mixed: the checks disagree ({score:+d} of {len(checks)})."}[lean]
    lines.insert(0, lean_text)
    return {"symbol": "ES", "time": now.strftime("%Y-%m-%dT%H:%MZ"), "barTime": T[-1][0].astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
            "phase": ph, "phaseText": ph_text, "last": round(last, 2), "changePct": round(chg, 2),
            "rangeUsed": round(used, 3), "typicalRange": round(typical, dp), "position": round(pos, 2),
            "vwap": round(vwap, 2) if vwap else None, "hourMove": round(move, 2), "trend": trend,
            "busy": round(busy, 2) if busy else None,
            "levels": {"above": [{"name": n, "price": round(v, 2)} for _, n, v in above],
                       "below": [{"name": n, "price": round(v, 2)} for _, n, v in below]},
            "lines": lines, "lean": lean, "leanScore": score, "leanText": lean_text,
            "checks": [{"name": n, "sign": v} for n, v in checks], "weekPct": round(week, 2),
            "note": "Intraday market conditions from delayed ES futures."}
