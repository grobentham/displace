"""Market data for Displace World: settled closes, unusual moves and historical base rates.

Reads the caches the existing engine already keeps (engine/cache/daily, engine/cache/series) and the watch-list
share closes World keeps (engine/cache/world/stocks). Nothing here downloads.
"""
import datetime as dt
import json
import statistics
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NY = ZoneInfo("America/New_York")
DAILY = ROOT / "engine/cache/daily"
SERIES = ROOT / "engine/cache/series"
STOCKS = ROOT / "engine/cache/world/stocks"

MARKETS = {  # id: (name, unit, how a move is measured, decimals)
    "nq": ("Nasdaq-100 futures", "points", "pct", 2), "es": ("S&P 500 futures", "points", "pct", 2),
    "ym": ("Dow futures", "points", "pct", 0), "rty": ("Russell 2000 futures", "points", "pct", 1),
    "gold": ("Gold futures", "USD/oz", "pct", 1), "cl": ("WTI crude futures", "USD/bbl", "pct", 2),
    "btc": ("Bitcoin futures", "USD", "pct", 0), "6e": ("Euro futures (EUR/USD)", "USD", "pct", 4),
}
SERIES_IDS = {  # FRED id: (name, unit, move, decimals)
    "VIXCLS": ("VIX volatility index", "points", "pct", 2), "DGS2": ("US 2-year Treasury yield", "%", "diff", 2),
    "DGS10": ("US 10-year Treasury yield", "%", "diff", 2), "DTWEXBGS": ("Broad US dollar index", "index", "pct", 2),
    "BAMLH0A0HYM2": ("US high-yield credit spread", "%", "diff", 2),
}
MOVE_Z = 2.5
LOOKBACK = 60


def ny_today(now):
    return now.astimezone(NY).date()


def settled_cutoff(now):
    """Sessions up to and including this date have a final close."""
    local = now.astimezone(NY)
    return local.date() if local.hour >= 18 else local.date() - dt.timedelta(days=1)


def load_market(mid, now=None):
    try:
        days = json.loads((DAILY / f"{mid}.json").read_text())["days"]
    except (OSError, ValueError, KeyError):
        return {}
    cut = settled_cutoff(now).isoformat() if now else "9999"
    return {d: float(v[3]) for d, v in sorted(days.items()) if d <= cut and v and v[3]}


def load_series(sid):
    try:
        rows = json.loads((SERIES / f"{sid}.json").read_text())["rows"]
    except (OSError, ValueError, KeyError):
        return {}
    out = {}
    for r in rows:
        try:
            out[r[0]] = float(r[1])
        except (ValueError, TypeError, IndexError):
            continue
    return dict(sorted(out.items()))


def load_stock(ticker):
    try:
        return dict(sorted(json.loads((STOCKS / f"{ticker}.json").read_text())["closes"].items()))
    except (OSError, ValueError, KeyError):
        return {}


def moves(closes, how):
    keys = list(closes)
    out = []
    for i in range(1, len(keys)):
        a, b = closes[keys[i - 1]], closes[keys[i]]
        out.append((keys[i], (b / a - 1) * 100 if how == "pct" else (b - a)))
    return out


def unusual(closes, how, day=None):
    """The last settled move (or `day`'s) and its z-score against the 60 moves before it."""
    mv = moves(closes, how)
    if len(mv) < LOOKBACK + 1:
        return None
    idx = len(mv) - 1 if day is None else next((i for i, (d, _) in enumerate(mv) if d == day), None)
    if idx is None or idx < LOOKBACK:
        return None
    hist = [m for _, m in mv[idx - LOOKBACK:idx]]
    sd = statistics.pstdev(hist)
    if sd == 0:
        return None
    d, m = mv[idx]
    return {"day": d, "move": m, "z": m / sd, "sd": sd, "prev_day": mv[idx - 1][0] if idx else None,
            "close": closes[d], "median_abs": statistics.median(abs(h) for h in hist)}


def _all_z(mv):
    for i in range(LOOKBACK, len(mv)):
        hist = [m for _, m in mv[i - LOOKBACK:i]]
        sd = statistics.pstdev(hist)
        if sd:
            yield i, mv[i][1] / sd, statistics.mean(abs(h) for h in hist)


def after_big_move(closes, how, sign, horizon=5, before=None):
    """After past moves of at least MOVE_Z sd in this direction: how often was the close `horizon` sessions
    later above the big-move day's close, and how often were the next `horizon` sessions' moves larger than
    the 60-session average? Excludes the event being forecast (everything on or after `before`)."""
    keys = list(closes)
    mv = moves(closes, how)
    up = {"n": 0, "hits": 0}
    wide = {"n": 0, "hits": 0}
    last_i = -99
    for i, z, avg_abs in _all_z(mv):
        if sign * z < MOVE_Z or i - last_i <= horizon:
            continue
        day = mv[i][0]
        if before and day >= before:
            break
        k = keys.index(day)
        if k + horizon >= len(keys):
            break
        last_i = i
        later = closes[keys[k + horizon]]
        up["n"] += 1
        up["hits"] += later > closes[day]
        nxt = [abs(m) for _, m in mv[i + 1:i + 1 + horizon]]
        wide["n"] += 1
        wide["hits"] += statistics.mean(nxt) > avg_abs
    return up, wide


def trend_persistence(closes, horizon, lookback=252, step=21, before=None):
    """Sampled monthly: when the close was above (or below) its level `lookback` sessions earlier, how often was
    that still true `horizon` sessions later? Returns {"above": {...}, "below": {...}}."""
    keys = [k for k in closes if not before or k < before]
    out = {"above": {"n": 0, "hits": 0}, "below": {"n": 0, "hits": 0}}
    for i in range(lookback, len(keys) - horizon, step):
        state = closes[keys[i]] > closes[keys[i - lookback]]
        j = i + horizon
        later = closes[keys[j]] > closes[keys[j - lookback]]
        bucket = out["above" if state else "below"]
        bucket["n"] += 1
        bucket["hits"] += later == state
    return out


def session_after(closes, day, n):
    """The nth session after `day` in this series, or None if it has not happened yet."""
    keys = [k for k in closes if k > day]
    return keys[n - 1] if len(keys) >= n else None


def reaction_session(closes, accepted_utc):
    """The first session whose close comes after a filing was accepted (16:00 New York close)."""
    local = accepted_utc.astimezone(NY)
    day = local.date().isoformat()
    for k in closes:
        if k > day or (k == day and local.hour < 16):
            return k
    return None


def prev_session(closes, day):
    keys = [k for k in closes if k < day]
    return keys[-1] if keys else None


def fmt(v, decimals):
    return f"{v:,.{decimals}f}"
