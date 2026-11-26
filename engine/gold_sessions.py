"""Clean Gold futures session candles built from one-minute bars."""
import datetime as dt

from exchange import NY
from es_outlook import day_key, despike, load_json

URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?range=5d&interval=1m"


def minutes(raw):
    """[(New York time, o, h, l, c, volume)] for each 1-minute bar with a full price."""
    res = raw["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(res["timestamp"]):
        o, h, l, c = (q[k][i] for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c):
            continue
        out.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(NY), o, h, l, c, float(q["volume"][i] or 0)))
    return out


def sessions(rows, now=None):
    """{session date: {"o","h","l","c","rawH","rawL","bars","complete","full","spikes"}} from 1-minute rows, despiked one
    session at a time. rawH/rawL are the extremes before the filter: a consumer can tell a clipped bad print (its
    daily high equals rawH, above h) from a candle that simply covers a different window."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(NY)
    by = {}
    for r in rows:
        by.setdefault(day_key(r[0]), []).append(r)
    out = {}
    for day, b in sorted(by.items()):
        b.sort(key=lambda r: r[0])
        clean = despike(b)
        spikes = sum(1 for x, y in zip(b, clean) if x[2] != y[2] or x[3] != y[3])
        end = dt.datetime.combine(day, dt.time(17, 0), NY)
        start = dt.datetime.combine(day - dt.timedelta(days=1), dt.time(18, 0), NY)   # Monday opens Sunday 18:00
        out[day.isoformat()] = {"o": round(clean[0][1], 4), "h": round(max(r[2] for r in clean), 4),
                                "l": round(min(r[3] for r in clean), 4), "c": round(clean[-1][4], 4),
                                "rawH": round(max(r[2] for r in b), 4), "rawL": round(min(r[3] for r in b), 4),
                                "bars": len(clean), "complete": now >= end,
                                "full": b[0][0] <= start + dt.timedelta(minutes=20),   # the 5-day window can start mid-session
                                "spikes": spikes}
    return out



def fetch_sessions():
    return sessions(minutes(load_json(URL)))
