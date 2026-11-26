"""Indicative XAUUSD outlook from XAUS's five-minute spot observations."""
import datetime as dt
import json
import math
import urllib.request
from zoneinfo import ZoneInfo

URL = "https://xaus.com/api/v1/intraday?symbol=xau&hours=48"
NY = ZoneInfo("America/New_York")
MAX_AGE = dt.timedelta(minutes=15)
HOUR = dt.timedelta(hours=1)


def observations(data, now):
    if (data.get("symbol"), data.get("currency"), data.get("unit")) != ("xau", "USD", "troy_oz"):
        return []
    if data.get("data_state", {}).get("status") != "fresh":
        return []
    result = {}
    for item in data.get("points", []):
        stamp, price = item.get("t"), item.get("p")
        if (type(stamp) is int and 0 < stamp <= now.timestamp()
                and type(price) in (int, float) and math.isfinite(price) and price > 0):
            result[dt.datetime.fromtimestamp(stamp, dt.timezone.utc)] = price
    return sorted(result.items())


def session_date(stamp):
    local = stamp.astimezone(NY)
    return local.date() + dt.timedelta(days=local.hour >= 17)


def direction(move, threshold):
    return 1 if move > threshold else -1 if move < -threshold else 0


def xauusd_outlook(data=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if data is None:
        request = urllib.request.Request(URL, headers={
            "Accept": "application/json", "User-Agent": "Displace spot outlook"
        })
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)

    points = observations(data, now)
    if not points:
        return None
    last_stamp, last = points[-1]
    if now - last_stamp > MAX_AGE:
        return None

    day = session_date(last_stamp)
    current = [row for row in points if session_date(row[0]) == day]
    previous = [row for row in points if session_date(row[0]) < day]
    lines = [f"XAUUSD spot reference: {last:,.2f} USD per troy ounce."]
    checks = []
    levels = []

    if previous:
        prior_stamp, prior_price = previous[-1]
        close = dt.datetime.combine(session_date(prior_stamp), dt.time(17), NY)
        if dt.timedelta(0) <= close - prior_stamp <= dt.timedelta(minutes=30):
            change = (last / prior_price - 1) * 100
            lines.append(f"{change:+.2f}% versus the prior session’s last sampled price ({prior_price:,.2f}).")
            checks.append(("versus the prior session", direction(change, 0.10)))
            levels.append(("Prior sampled close", prior_price))

    if len(current) >= 7 and current[-1][0] - current[0][0] >= dt.timedelta(minutes=30):
        high = max(price for _, price in current)
        low = min(price for _, price in current)
        lines.append(f"Observed session range: {low:,.2f}–{high:,.2f} ({high - low:,.2f} USD), from five-minute samples.")
        if high - low >= last * 0.0005:
            position = (last - low) / (high - low)
            checks.append(("within the sampled session range", direction(position - 0.5, 1 / 6)))
        else:
            checks.append(("within the sampled session range", 0))
        levels.extend([("Observed session high", high), ("Observed session low", low)])

    target = last_stamp - HOUR
    prior_hour = next((row for row in reversed(current) if row[0] <= target), None)
    if prior_hour and target - prior_hour[0] <= dt.timedelta(minutes=8):
        move = last - prior_hour[1]
        lines.append(f"Last hour: {move:+,.2f} USD between sampled prices.")
        checks.append(("over the last hour", direction(move, last * 0.0005)))

    tally = sum(sign for _, sign in checks)
    if len(checks) < 2:
        lean, summary = "mixed", "Gathering session observations for a directional read."
    elif abs(tally) >= 2:
        sign = 1 if tally > 0 else -1
        lean = "bullish" if sign > 0 else "bearish"
        matching = ", ".join(name for name, value in checks if value == sign)
        summary = f"Sampled spot prices are {'up' if sign > 0 else 'down'} {matching}."
    elif all(sign == 0 for _, sign in checks):
        lean, summary = "consolidating", "Sampled prices show little directional movement across the available checks."
    else:
        lean, summary = "mixed", "The available spot-price checks give a mixed reading."

    def levels_on_side(sign):
        nearby = sorted((abs(price - last), name, price) for name, price in levels if (price - last) * sign > 0.01)
        return [{"name": name, "price": round(price, 2)} for _, name, price in nearby[:3]]

    return {
        "symbol": "XAUUSD",
        "source": "xaus",
        "time": now.isoformat(timespec="seconds"),
        "barTime": last_stamp.isoformat(timespec="seconds"),
        "last": round(last, 2),
        "phaseText": "Indicative XAU/USD spot prices sampled every five minutes.",
        "lean": lean,
        "leanText": summary,
        "lines": lines,
        "levels": {"above": levels_on_side(1), "below": levels_on_side(-1)},
        "checks": [{"name": name, "sign": sign} for name, sign in checks],
    }
