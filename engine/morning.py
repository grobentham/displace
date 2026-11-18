"""Prepare the daily Singapore morning brief from the published engine data."""
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import DATA, NY, NOW, WHY, clean, kind_of, load, save, when

SGT = ZoneInfo("Asia/Singapore")
DAY = dt.timedelta(days=1)
LEAD = dt.timedelta(minutes=20)


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


def build_edition(opens, now, calendar, news, markets):
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
        "calendarCovered": calendar.get("through", "") >= end.astimezone(NY).date().isoformat(),
        "feedsChecked": checked is not None and now - dt.timedelta(hours=2) <= checked <= now,
        "feedIssues": any(ok is False for ok in news.get("sources", {}).values()),
    }


def publish(now, data):
    target = data / "brief" / "morning.json"
    editions = load(target, {}).get("editions", [])
    opens = edition_time(now)
    date = opens.date().isoformat()
    if any(edition["date"] == date for edition in editions):
        print(f"Morning brief for {date} SGT already prepared.")
        return

    edition = build_edition(opens, now,
                            load(data / "calendar" / "events.json", {}),
                            load(data / "news" / "latest.json", {}),
                            load(data / "markets" / "latest.json", {}))
    editions = sorted([*editions, edition], key=lambda item: item["date"], reverse=True)[:2]
    save(target, {"version": 1, "editions": editions})
    print(f"Prepared morning brief for {opens.isoformat(timespec='minutes')}.")


if __name__ == "__main__":
    publish(NOW, Path(DATA))
