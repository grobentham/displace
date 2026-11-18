"""Prepare the 7 a.m. Singapore daily brief and refresh confirmed releases."""
import datetime as dt
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from calendar_rules import nyse_holidays
from engine import DATA, NY, NOW, WHY, clean, fomc_label, kind_of, load, market_line, save, when
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
    items = {}
    for item in news.get("items", []):
        published = dt.datetime.fromisoformat(item["published"])
        if start <= published <= cutoff and item.get("title") and item.get("url", "").startswith("https://"):
            row = {key: item[key] for key in ("id", "title", "url", "analysis") if key in item}
            row["published"] = published.astimezone(SGT).isoformat(timespec="seconds")
            items[row.get("id") or (row["url"], row["title"], row["published"])] = row
    return sorted(items.values(), key=lambda item: item["published"], reverse=True)[:2]


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
        return {"label": "No U.S. session", "reason": "U.S. cash equities are closed during this edition’s window.", "rates": None}
    while not cash_session(last_close):
        last_close -= DAY
    tiles = markets.get("tiles", {})
    two, ten = tiles.get("y2", {}), tiles.get("y10", {})
    if any(tile.get("date") != last_close.isoformat() or not isinstance(tile.get("d1"), (int, float))
           or not isfinite(tile["d1"]) for tile in (two, ten)):
        return {"label": "Data pending", "reason": "Waiting for both Treasury yields from the latest U.S. session.", "rates": None}
    short, long = two["d1"], ten["d1"]
    rates = {"date": last_close.isoformat(), "twoYearBp": short, "tenYearBp": long,
             "twoYearYield": two.get("value"), "tenYearYield": ten.get("value")}
    if short <= -RATE_THRESHOLD and long <= -RATE_THRESHOLD:
        return {"label": "Bullish tilt", "reason": "Yields fell across both maturities, easing pressure on tech valuations.", "rates": rates}
    if short >= RATE_THRESHOLD and long >= RATE_THRESHOLD:
        return {"label": "Bearish tilt", "reason": "Yields rose across both maturities, adding pressure on tech valuations.", "rates": rates}
    return {"label": "Neutral", "reason": "Treasury moves gave no clear directional signal for tech stocks.", "rates": rates}


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


def release_schedule(opens, cutoff, calendar):
    end = opens + DAY
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
    focus = {"title": clean(lead["title"]), "text": why} if why else None
    rows = []
    for at, event in scheduled:
        row = {"at": at.isoformat(timespec="minutes"), "title": event["title"]}
        for key in ("forecast", "previous"):
            if event.get(key):
                row[key] = event[key]
        if at <= cutoff and event.get("actual"):
            row["actual"] = event["actual"]
        rows.append(row)
    return sorted(rows[:3], key=lambda row: row["at"]), sorted(rows[3:], key=lambda row: row["at"]), focus


def build_edition(opens, now, calendar, news, markets, earnings=None, reports=(), sources_read=0):
    end, cutoff = opens + DAY, min(opens, now)
    upcoming, more, focus = release_schedule(opens, cutoff, calendar)
    fed = next((e for e in sorted(calendar.get("events", []), key=when)
                if kind_of(e) == "fomc" and when(e) >= opens), None)
    day = cutoff.astimezone(NY).date()
    close = [market_line({key: tile}) for key, tile in markets.get("tiles", {}).items()
             if key in ("usd", "oil") and day - dt.timedelta(days=4) <= dt.date.fromisoformat(tile["date"]) <= day]

    checked = dt.datetime.fromisoformat(news["checkedAt"]) if news.get("checkedAt") else None
    return {
        "date": opens.date().isoformat(), "opensAt": opens.isoformat(timespec="minutes"),
        "generatedAt": now.astimezone(SGT).isoformat(timespec="seconds"),
        "updates": recent_updates(news, opens - DAY, cutoff), "upcoming": upcoming, "moreReleases": more,
        "focus": focus,
        "nextFed": fomc_label(fed) if fed and when(fed) >= end else None, "otherCloses": close,
        "treasury": treasury_context(markets, cutoff),
        "outlook": {**market_outlook(opens, markets), "thresholdBp": RATE_THRESHOLD},
        "earnings": {"reports": list(reports), "upcoming": scheduled_earnings(opens, end, earnings or {}),
                     "sourcesRead": sources_read, "sourcesTotal": len(FEEDS)},
        "calendarCovered": calendar.get("through", "") >= end.astimezone(NY).date().isoformat(),
        "feedsChecked": checked is not None and now - dt.timedelta(hours=2) <= checked <= now,
        "feedIssues": any(ok is False for ok in news.get("sources", {}).values()),
    }


def refresh_edition(edition, now, calendar, news):
    opens = dt.datetime.fromisoformat(edition["opensAt"])
    if not opens <= now < opens + DAY:
        return
    before = (edition["upcoming"], edition["moreReleases"], edition["focus"], edition["updates"])
    upcoming, more, focus, _ = before
    if "events" in calendar:
        upcoming, more, focus = release_schedule(opens, now, calendar)
    refreshed_news = {"items": [*edition["updates"], *news.get("items", [])]}
    updates = recent_updates(refreshed_news, opens - DAY, now)
    if (upcoming, more, focus, updates) != before:
        edition.update(upcoming=upcoming, moreReleases=more, focus=focus, updates=updates,
                       refreshedAt=now.astimezone(SGT).isoformat(timespec="seconds"))


def publish(now, data, read_reports=get_reports):
    target = data / "brief" / "morning.json"
    editions = load(target, {}).get("editions", [])
    opens = edition_time(now)
    date = opens.date().isoformat()
    calendar = load(data / "calendar" / "events.json", {})
    news = load(data / "news" / "latest.json", {})
    if not any(edition["date"] == date and "moreReleases" in edition for edition in editions):
        reports, sources_read = read_reports(opens - DAY, min(opens, now))
        edition = build_edition(opens, now, calendar, news,
                                load(data / "markets" / "latest.json", {}),
                                load(data / "calendar" / "earnings.json", {}), reports, sources_read)
        editions = [item for item in editions if item["date"] != date] + [edition]
        print(f"Prepared daily brief for {opens.isoformat(timespec='minutes')}.")
    editions = sorted(editions, key=lambda item: item["date"], reverse=True)[:2]
    for edition in editions:
        if "moreReleases" in edition:
            refresh_edition(edition, now, calendar, news)
    save(target, {"version": 2, "editions": editions})


if __name__ == "__main__":
    publish(NOW, Path(DATA))
