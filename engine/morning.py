"""Prepare the daily Singapore morning brief from the published engine data."""
import datetime as dt
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from calendar_rules import nyse_holidays
from engine import DATA, NY, NOW, WHY, clean, kind_of, load, save, when
from earnings import WATCH, TIMES
from earnings_news import FEEDS, get_reports

SGT = ZoneInfo("Asia/Singapore")
DAY = dt.timedelta(days=1)
LEAD = dt.timedelta(minutes=20)
RATE_THRESHOLD = 3


def edition_time(now):
    today = now.astimezone(SGT).replace(hour=7, minute=0, second=0, microsecond=0)
    return today if now >= today - LEAD else today - DAY


def recent_updates(news, start, cutoff):
    items = []
    for item in news.get("items", []):
        published = dt.datetime.fromisoformat(item["published"])
        if start <= published <= cutoff and item.get("title") and item.get("url", "").startswith("https://"):
            items.append((published, {key: item[key] for key in ("title", "url", "analysis") if key in item}))
    items.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in items[:2]]


def treasury_context(markets, cutoff):
    tile = markets.get("tiles", {}).get("y2")
    if not tile:
        return None
    date = dt.date.fromisoformat(tile["date"])
    day = cutoff.astimezone(NY).date()
    if not day - dt.timedelta(days=4) <= date <= day:
        return None
    return {"date": tile["date"], "yield": tile["value"], "changeBp": tile.get("d1")}


def cash_session(day):
    return day.weekday() < 5 and day not in nyse_holidays(day.year)


def market_outlook(opens, markets):
    last_close = opens.astimezone(NY).date()
    session = last_close + DAY
    if not cash_session(session):
        return {"label": "No U.S. session", "reason": "U.S. cash equities are closed during this edition’s window."}
    while not cash_session(last_close):
        last_close -= DAY
    tiles = markets.get("tiles", {})
    two, ten = tiles.get("y2", {}), tiles.get("y10", {})
    if any(tile.get("date") != last_close.isoformat() or not isinstance(tile.get("d1"), (int, float))
           or not isfinite(tile["d1"]) for tile in (two, ten)):
        return {"label": "Data pending", "reason": "The latest U.S. session’s 2-year and 10-year yields are needed for a rates-based tilt."}
    short, long = two["d1"], ten["d1"]
    moves = f"2-year {short:+g} bp and 10-year {long:+g} bp on {last_close.isoformat()}."
    if short <= -RATE_THRESHOLD and long <= -RATE_THRESHOLD:
        return {"label": "Bullish tilt", "reason": f"Yields fell across both maturities, easing pressure on tech valuations. {moves}"}
    if short >= RATE_THRESHOLD and long >= RATE_THRESHOLD:
        return {"label": "Bearish tilt", "reason": f"Yields rose across both maturities, adding pressure on tech valuations. {moves}"}
    return {"label": "Neutral", "reason": f"Treasury moves gave no clear rates signal. {moves}"}


def scheduled_earnings(opens, end, earnings):
    selected = []
    for item in earnings.get("events", []):
        symbol = item["id"].rsplit("-earn-", 1)[-1].upper()
        if symbol not in WATCH:
            continue
        session = item.get("session", "")
        clock = item.get("time")
        if not clock:
            if item["date"] != end.astimezone(NY).date().isoformat():
                continue
            sort_at = when(item)
        else:
            sort_at = when(item)
            if not opens <= sort_at < end:
                continue
        row = {"symbol": symbol, "title": WATCH[symbol][0], "session": session,
               "date": item["date"], "confirmed": item.get("status") == "confirmed"}
        if clock:
            row["at"] = sort_at.astimezone(SGT).isoformat(timespec="minutes")
            row["timeConfirmed"] = clock != TIMES.get(session)
        if item.get("url", "").startswith("https://"):
            row["url"] = item["url"]
        selected.append((WATCH[symbol][1] != "mega", sort_at, row))
    selected.sort(key=lambda entry: entry[:2])
    return [row for _, _, row in selected[:2]]


def build_edition(opens, now, calendar, news, markets, earnings=None, reports=(), sources_read=0):
    end, cutoff = opens + DAY, min(opens, now)
    scheduled = []
    for event in calendar.get("events", []):
        if event.get("cur") != "USD" or event.get("impact") not in ("high", "medium") or not event.get("time"):
            continue
        at = when(event).astimezone(SGT)
        if opens <= at < end:
            scheduled.append((at, event))
    scheduled.sort(key=lambda pair: (pair[1]["impact"] != "high", pair[0]))
    lead = scheduled[0][1] if scheduled else {}
    why = WHY.get(kind_of(lead))
    next_releases = []
    for at, event in sorted(scheduled[:3], key=lambda pair: pair[0]):
        row = {"at": at.isoformat(timespec="minutes"), "title": event["title"]}
        if event.get("forecast"):
            row["forecast"] = event["forecast"]
        next_releases.append(row)

    checked = dt.datetime.fromisoformat(news["checkedAt"]) if news.get("checkedAt") else None
    return {
        "date": opens.date().isoformat(), "opensAt": opens.isoformat(timespec="minutes"),
        "generatedAt": now.astimezone(SGT).isoformat(timespec="seconds"),
        "updates": recent_updates(news, opens - DAY, cutoff), "upcoming": next_releases,
        "focus": {"title": clean(lead["title"]), "text": why} if why else None,
        "treasury": treasury_context(markets, cutoff),
        "outlook": {**market_outlook(opens, markets), "thresholdBp": RATE_THRESHOLD},
        "earnings": {"reports": list(reports), "upcoming": scheduled_earnings(opens, end, earnings or {}),
                     "sourcesRead": sources_read, "sourcesTotal": len(FEEDS)},
        "calendarCovered": calendar.get("through", "") >= end.astimezone(NY).date().isoformat(),
        "feedsChecked": checked is not None and now - dt.timedelta(hours=2) <= checked <= now,
        "feedIssues": any(ok is False for ok in news.get("sources", {}).values()),
    }


def publish(now, data, read_reports=get_reports):
    target = data / "brief" / "morning.json"
    editions = load(target, {}).get("editions", [])
    opens = edition_time(now)
    date = opens.date().isoformat()
    if any(edition["date"] == date and "outlook" in edition and "earnings" in edition for edition in editions):
        print(f"Morning brief for {date} SGT already prepared.")
        return

    reports, sources_read = read_reports(opens - DAY, min(opens, now))
    edition = build_edition(opens, now,
                            load(data / "calendar" / "events.json", {}),
                            load(data / "news" / "latest.json", {}),
                            load(data / "markets" / "latest.json", {}),
                            load(data / "calendar" / "earnings.json", {}), reports, sources_read)
    editions = [item for item in editions if item["date"] != date]
    editions = sorted([*editions, edition], key=lambda item: item["date"], reverse=True)[:2]
    save(target, {"version": 2, "editions": editions})
    print(f"Prepared morning brief for {opens.isoformat(timespec='minutes')}.")


if __name__ == "__main__":
    publish(NOW, Path(DATA))
