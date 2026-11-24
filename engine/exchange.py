"""CME exchange sessions: trading dates, holidays, session times and settlement, per market.

One source of truth for "which session is this, when does it open, close and settle, and is there one today",
used by Displace (bias forecasts and scoring) and Iron Brain (no-trade days, early closes). The same file lives in
both repos (EXCHANGE_VERSION); keep them identical.

Rules, all in New York time, which handles daylight saving automatically (CME publishes Chicago time, one hour
earlier):
- A trading date D runs from the Globex reopen at 18:00 (17:00 Chicago) after the previous trading date's close,
  to 17:00 on D. A Monday session opens Sunday 18:00. On US holidays CME halts early (equity 13:00, metals and
  energy 14:30) and has no settlement: that trading belongs to the next trading date, whose session therefore starts
  before the holiday (Friday 27 Nov 2026's session opens Wednesday 25 Nov at 18:00).
- Fully closed, no reopen the evening before: New Year's Day, Good Friday, Christmas (observed dates).
- Holiday halts, no trading date: Martin Luther King Jr. Day, Presidents Day, Memorial Day, Juneteenth (from 2022),
  Independence Day, Labor Day, Thanksgiving.
- Early closes (a trading date that ends early): the day after Thanksgiving, 24 December and 3 July when the next day
  is the holiday. Equity index futures close 13:15 and settle 13:00 (12:15 / 12:00 Chicago); FX and crypto settle
  13:00; metals and energy keep their normal settlement and close early at a time CME announces each year (left as
  None here: check CME's advisory).
- Daily settlement (normal days): equity index and bitcoin 16:00 (15:00 Chicago), euro FX 15:00, crude 14:30, gold
  13:30.
- One-off closures: 11-14 Sep 2001.
Source: CME Group holiday calendars and settlement advisories (cmegroup.com/trading-hours.html); rules checked
24 Nov 2026. CME can change any of this in an advisory; unscheduled closures need adding to SPECIAL_CLOSED.
"""
import datetime as dt
from zoneinfo import ZoneInfo

EXCHANGE_VERSION = "2026-11-24.1"
NY = ZoneInfo("America/New_York")

GROUP = {"nq": "equity", "es": "equity", "ym": "equity", "rty": "equity", "gold": "metals", "cl": "energy",
         "6e": "fx", "btc": "crypto"}
SETTLE = {"equity": (16, 0), "crypto": (16, 0), "fx": (15, 0), "energy": (14, 30), "metals": (13, 30)}
HALT = {"equity": (13, 0), "crypto": (13, 0), "fx": (13, 0), "energy": (14, 30), "metals": (14, 30)}
EARLY = {"equity": {"close": (13, 15), "settle": (13, 0)}, "crypto": {"close": (13, 15), "settle": (13, 0)},
         "fx": {"close": (13, 15), "settle": (13, 0)},
         "metals": {"close": None, "settle": (13, 30)}, "energy": {"close": None, "settle": (14, 30)}}
SPECIAL_CLOSED = {dt.date(2001, 9, 11), dt.date(2001, 9, 12), dt.date(2001, 9, 13), dt.date(2001, 9, 14)}


def _nth(y, m, wd, n):
    if n > 0:
        d = dt.date(y, m, 1)
        return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
    d = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return dt.date(y, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _observed(d):
    return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d


_cache = {}


def calendar(y):
    """{date: ("closed" | "halt" | "early", name)} for year y."""
    if y in _cache:
        return _cache[y]
    out = {}
    ny = dt.date(y, 1, 1)
    out[_observed(ny) if ny.weekday() == 6 else ny] = ("closed", "New Year's Day")
    out[_easter(y) - dt.timedelta(days=2)] = ("closed", "Good Friday")
    out[_observed(dt.date(y, 12, 25))] = ("closed", "Christmas")
    halts = [(_nth(y, 2, 0, 3), "Presidents Day"), (_nth(y, 5, 0, -1), "Memorial Day"),
             (_observed(dt.date(y, 7, 4)), "Independence Day"), (_nth(y, 9, 0, 1), "Labor Day"),
             (_nth(y, 11, 3, 4), "Thanksgiving")]
    if y >= 1998:
        halts.append((_nth(y, 1, 0, 3), "Martin Luther King Jr. Day"))
    if y >= 2022:
        halts.append((_observed(dt.date(y, 6, 19)), "Juneteenth"))
    for d, name in halts:
        out.setdefault(d, ("halt", name))
    early = [(_nth(y, 11, 3, 4) + dt.timedelta(days=1), "Day after Thanksgiving")]
    for d, name in ((dt.date(y, 12, 24), "Christmas Eve"), (dt.date(y, 7, 3), "Day before Independence Day")):
        nxt = d + dt.timedelta(days=1)
        if d.weekday() < 5 and d not in out and out.get(nxt, ("", ""))[0] in ("closed", "halt"):
            early.append((d, name))
    for d, name in early:
        out.setdefault(d, ("early", name))
    for d in SPECIAL_CLOSED:
        if d.year == y:
            out[d] = ("closed", "Unscheduled closure")
    _cache[y] = out
    return out


def _date(d):
    return d if isinstance(d, dt.date) and not isinstance(d, dt.datetime) else dt.date.fromisoformat(str(d)[:10])


def day_status(d):
    """('weekend' | 'closed' | 'halt' | 'early' | 'trade', name)."""
    d = _date(d)
    if d.weekday() >= 5:
        return "weekend", ""
    return calendar(d.year).get(d, ("trade", ""))


def is_trade_date(d):
    return day_status(d)[0] in ("trade", "early")


def next_trade_date(d):
    """The first trading date after calendar date d."""
    d = _date(d) + dt.timedelta(days=1)
    while not is_trade_date(d):
        d += dt.timedelta(days=1)
    return d


def prev_trade_date(d):
    d = _date(d) - dt.timedelta(days=1)
    while not is_trade_date(d):
        d -= dt.timedelta(days=1)
    return d


def _reopens(d):
    """Globex reopens at 18:00 on calendar day d when the next day has trading (a trading date or a holiday halt)."""
    s, _ = day_status(d + dt.timedelta(days=1))
    return s in ("trade", "early", "halt")


def _at(d, hm):
    return dt.datetime.combine(d, dt.time(*hm), NY) if hm else None


def session(market, d):
    """Trading date d for a market: open, close and settlement times (New York, aware datetimes), whether it
    closes early, the holiday-halt days it spans, or None if d is not a trading date."""
    d = _date(d)
    if not is_trade_date(d):
        return None
    group = GROUP[market]
    p = prev_trade_date(d)
    s = p
    while not _reopens(s):
        s += dt.timedelta(days=1)
    status, name = day_status(d)
    if status == "early":
        close, settle = _at(d, EARLY[group]["close"]), _at(d, EARLY[group]["settle"])
    else:
        close, settle = _at(d, (17, 0)), _at(d, SETTLE[group])
    halts = [x for x in (p + dt.timedelta(days=k) for k in range(1, (d - p).days)) if day_status(x)[0] == "halt"]
    return {"market": market, "trade_date": d.isoformat(), "open": _at(s, (18, 0)), "close": close, "settle": settle,
            "early_close": status == "early", "note": name,
            "includes_halt_days": [{"date": x.isoformat(), "halt_at": _at(x, HALT[group]).isoformat(),
                                    "holiday": day_status(x)[1]} for x in halts]}


def session_for(market, when):
    """The trading date that time `when` (aware datetime) belongs to, or None when the market is shut
    (daily break, weekend, closures, after a holiday halt)."""
    t = when.astimezone(NY)
    d = t.date()
    for cand in (d, next_trade_date(d)):             # today's session, or the one that opened this evening
        if is_trade_date(cand):
            s = session(market, cand)
            if s["open"] <= t < (s["close"] or _at(cand, (17, 0))):
                for h in s["includes_halt_days"]:
                    hd = dt.date.fromisoformat(h["date"])
                    if hd == d and _at(hd, HALT[GROUP[market]]) <= t < _at(hd, (18, 0)):
                        return None
                return cand
    return None


def target_for(market, when):
    """The trading date a forecast made at `when` should be for: the first trading date whose session has not
    opened yet. A forecast for an earlier date would already be inside its session."""
    d = when.astimezone(NY).date() - dt.timedelta(days=1)
    while True:
        d = next_trade_date(d)
        if session(market, d)["open"] > when:
            return d


def summary(market, start, end):
    """Trading dates and non-trading weekdays between two dates, for audits and the site."""
    d, out = _date(start), []
    while d <= _date(end):
        s, name = day_status(d)
        if s != "weekend":
            out.append({"date": d.isoformat(), "status": s, "name": name})
        d += dt.timedelta(days=1)
    return out
