"""Check the files actually served to visitors from outside the publishing job."""
import datetime as dt
import json
import sys
import time
import urllib.request

BASE = "https://grobentham.github.io/displace/"


def get(path):
    request = urllib.request.Request(BASE + path + "?health=" + str(int(time.time())),
                                     headers={"Cache-Control": "no-cache", "User-Agent": "Displace public health check"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def check(outlook, evidence, brief, calendar, now):
    errors = []
    updated = dt.datetime.fromisoformat(outlook["asof"])
    if now - updated > dt.timedelta(hours=18):
        errors.append(f"Outlook snapshot has not refreshed since {updated.isoformat()}")
    records = {row["id"]: row for row in evidence["forecasts"]}
    for market, view in outlook["markets"].items():
        row = records.get(view.get("forecast_id"))
        if (not row or row["logged"] != view["forecast_at"] or row["for"] != view["session"]["date"] or
                row["range_lo"] != view["range"]["lo"] or row["range_hi"] != view["range"]["hi"] or
                row["p_high"] != view["takes"]["high"]["p"] or row["p_low"] != view["takes"]["low"]["p"]):
            errors.append(f"Published {market} outlook and ledger disagree")
    nq = outlook["markets"]["nq"]
    if (brief["forecast_id"] != nq["forecast_id"] or brief["asof"] != nq["forecast_at"] or
            brief["date"] != nq["session"]["date"] or
            any(brief["range"][key] != nq["range"][key] for key in ("lo", "points", "hi")) or
            any(brief["levels"][side]["price"] != nq["levels"][side] for side in ("high", "low"))):
        errors.append("Published MNQ brief differs from the homepage outlook")
    if dt.date.fromisoformat(calendar["through"]) < now.date() + dt.timedelta(days=7):
        errors.append("Calendar has fewer than seven days of future coverage")
    return errors


def main():
    errors = check(get("data/bias/current.json"), get("data/open/current.json"),
                   get("data/briefs/mnq/latest.json"), get("data/calendar/events.json"), dt.datetime.now(dt.UTC))
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print("Published outlook, forecast ledger, shared brief and calendar passed")
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
