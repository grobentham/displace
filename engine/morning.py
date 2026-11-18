"""Prepare the 7 a.m. Singapore daily brief and refresh confirmed releases."""
import datetime as dt
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from calendar_rules import nyse_holidays
from engine import DATA, NY, NOW, clean, fomc_label, kind_of, load, market_line, save, when
from earnings import WATCH, TIMES
from earnings_news import FEEDS, get_reports
from news import CONTEXT

SGT = ZoneInfo("Asia/Singapore")
DAY = dt.timedelta(days=1)
LEAD = dt.timedelta(minutes=20)
RATE_THRESHOLD = 3
WATCH_FOR = {
    "cpi": "Compare monthly core and headline inflation. Broad price pressure matters for Fed expectations and Treasury yields.",
    "nfp": "Read job growth alongside unemployment and hourly pay. Strong hiring and slower wages can point in different directions.",
    "pce": "Watch monthly core inflation and whether consumer spending is strengthening or slowing.",
    "ppi": "Watch the components that feed into PCE inflation, especially when headline and core prices diverge.",
    "retail": "Compare headline sales with the control group, which feeds into estimates of consumer spending in GDP.",
    "fomc": "Watch the policy decision, changes in the statement, and the chair’s explanation of what could move rates next.",
    "minutes": "Look for disagreement over inflation and jobs, and what officials said would justify a change in rates.",
}


def edition_time(now):
    today = now.astimezone(SGT).replace(hour=7, minute=0, second=0, microsecond=0)
    return today if now >= today - LEAD else today - DAY


def recent_updates(news, opens, cutoff):
    items = {}
    for item in news.get("items", []):
        published = dt.datetime.fromisoformat(item["published"])
        if opens - DAY <= published <= cutoff and item.get("title") and item.get("url", "").startswith("https://"):
            row = {key: item[key] for key in ("id", "title", "url", "source", "analysis", "context") if item.get(key)}
            row["published"] = published.astimezone(SGT).isoformat(timespec="seconds")
            items[row.get("id") or (row["url"], row["title"], row["published"])] = row
    updates = sorted(items.values(), key=lambda item: item["published"], reverse=True)
    boundary = opens.astimezone(SGT).isoformat(timespec="seconds")
    return ([item for item in updates if item["published"] >= boundary][:2]
            + [item for item in updates if item["published"] < boundary][:3])


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


def rates_summary(short, long):
    if short <= -RATE_THRESHOLD and long <= -RATE_THRESHOLD:
        return "Bullish tilt", f"Both yields fell by at least {RATE_THRESHOLD} bp, easing pressure on tech valuations."
    if short >= RATE_THRESHOLD and long >= RATE_THRESHOLD:
        return "Bearish tilt", f"Both yields rose by at least {RATE_THRESHOLD} bp, adding pressure on tech valuations."
    if abs(short) < RATE_THRESHOLD and abs(long) < RATE_THRESHOLD:
        return "Neutral", f"Neither yield moved by the {RATE_THRESHOLD} bp needed for a rates tilt."
    if short * long < 0:
        return "Neutral", "The 2-year and 10-year moved in opposite directions."
    lagging = "2-year" if abs(short) < RATE_THRESHOLD else "10-year"
    return "Neutral", f"The {lagging} yield moved by less than {RATE_THRESHOLD} bp. A tilt requires both yields to reach that threshold."


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
    label, reason = rates_summary(short, long)
    return {"label": label, "reason": reason, "rates": rates}


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
        if item.get("src"):
            row["source"] = item["src"]
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
    lead = next(((at, event) for at, event in scheduled if at > cutoff), None)
    focus = {"title": clean(lead[1]["title"]), "at": lead[0].isoformat(timespec="minutes")} if lead else None
    rows = []
    for at, event in scheduled:
        row = {"at": at.isoformat(timespec="minutes"), "title": event["title"]}
        kind = kind_of(event)
        watch = WATCH_FOR.get(kind) or CONTEXT.get(kind)
        if watch:
            row["watch"] = watch
        if event.get("src"):
            row["source"] = event["src"]
        confirmed = at <= cutoff and event.get("actual")
        source_url = (event.get("provenance") or {}).get("url") if confirmed else None
        url = source_url or event.get("url") or ""
        if url.startswith("https://"):
            row["url"] = url
        for key in ("metric", "forecast", "previous"):
            if event.get(key):
                row[key] = event[key]
        if row.get("forecast") and event.get("fsrc"):
            row["forecastSource"] = event["fsrc"]
        if confirmed:
            row["actual"] = event["actual"]
            if event.get("revised") and event["revised"] != event.get("previous"):
                row["revised"] = event["revised"]
            components = [{key: component[key] for key in ("label", "actual", "previous") if component.get(key)}
                          for component in event.get("components", [])[1:] if component.get("label") and component.get("actual")]
            if components:
                row["components"] = components[:3]
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
        "updates": recent_updates(news, opens, cutoff), "upcoming": upcoming, "moreReleases": more,
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


def refresh_edition(edition, now, calendar, news, earnings=None):
    opens = dt.datetime.fromisoformat(edition["opensAt"])
    if not opens <= now < opens + DAY:
        return
    before = (edition["upcoming"], edition["moreReleases"], edition["focus"], edition["updates"])
    upcoming, more, focus, _ = before
    if "events" in calendar:
        upcoming, more, focus = release_schedule(opens, now, calendar)
    refreshed_news = {"items": [*edition["updates"], *news.get("items", [])]}
    updates = recent_updates(refreshed_news, opens, now)
    if (upcoming, more, focus, updates) != before:
        edition.update(upcoming=upcoming, moreReleases=more, focus=focus, updates=updates,
                       refreshedAt=now.astimezone(SGT).isoformat(timespec="seconds"))
    if earnings is not None and "events" in earnings and "earnings" in edition:
        edition["earnings"]["upcoming"] = scheduled_earnings(opens, opens + DAY, earnings)
    outlook = edition.get("outlook", {})
    if rates := outlook.get("rates"):
        short, long = rates.get("twoYearBp"), rates.get("tenYearBp")
        if all(isinstance(move, (int, float)) and isfinite(move) for move in (short, long)):
            _, outlook["reason"] = rates_summary(short, long)


def publish(now, data, read_reports=get_reports):
    target = data / "brief" / "morning.json"
    editions = load(target, {}).get("editions", [])
    opens = edition_time(now)
    date = opens.date().isoformat()
    calendar = load(data / "calendar" / "events.json", {})
    news = load(data / "news" / "latest.json", {})
    earnings = load(data / "calendar" / "earnings.json", {})
    if not any(edition["date"] == date and "moreReleases" in edition for edition in editions):
        reports, sources_read = read_reports(opens - DAY, min(opens, now))
        edition = build_edition(opens, now, calendar, news,
                                load(data / "markets" / "latest.json", {}),
                                earnings, reports, sources_read)
        editions = [item for item in editions if item["date"] != date] + [edition]
        print(f"Prepared daily brief for {opens.isoformat(timespec='minutes')}.")
    editions = sorted(editions, key=lambda item: item["date"], reverse=True)[:2]
    for edition in editions:
        if "moreReleases" in edition:
            refresh_edition(edition, now, calendar, news, earnings)
    save(target, {"version": 2, "editions": editions})


if __name__ == "__main__":
    publish(NOW, Path(DATA))
