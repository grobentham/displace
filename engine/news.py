"""Publish a source-linked digest of confirmed economic releases and policy news."""
import datetime as dt
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from catalog import RELEASES
from engine import DATA, NOW, kind_of, load, recap, save, when
from publicdata import ALFRED, FRED, download

FEEDS = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "European Central Bank": "https://www.ecb.europa.eu/rss/press.html",
    "Bank of England": "https://www.bankofengland.co.uk/rss/news",
}

CONTEXT = {
    "cpi": "Core CPI excludes food and energy. Comparing it with headline CPI helps identify where prices changed.",
    "ppi": "PPI tracks prices received by producers. Some components feed into the PCE inflation calculation.",
    "nfp": "Payrolls count jobs, while the unemployment rate comes from a separate household survey. The two measures can diverge.",
    "pce": "The Fed measures its inflation target using headline PCE. Core PCE helps identify the underlying trend.",
    "gdp": "Headline U.S. GDP growth is annualized. Subsequent estimates add data and may revise the same quarter.",
    "retail": "Retail sales are reported in dollars. Changes can reflect prices as well as the volume of goods sold.",
    "claims": "Initial claims count new unemployment insurance applications. The four-week average smooths weekly swings.",
    "jolts": "Job openings and the quits rate capture different aspects of labor demand and workers' willingness to change jobs.",
    "fomc": "The Fed sets a target range for overnight interest rates. The statement explains the committee's reasoning and any dissent.",
    "minutes": "Meeting minutes show which risks officials weighed when they made the decision.",
    "schedule": "The published meeting calendar gives the timing of policy decisions and minutes.",
    "ecb": "The deposit facility rate is a key benchmark for overnight euro-area rates. The statement explains the Governing Council's decision.",
    "wages": "The ECB wage tracker follows negotiated pay, which can move differently from average earnings across the economy.",
    "boe": "Bank Rate is the UK policy rate. The vote split shows how much agreement there was on the decision.",
}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text(value):
    parser = PlainText()
    parser.feed(unescape(value or ""))
    return " ".join(" ".join(parser.parts).replace("\ufffd", "'").split())


def topic_for(source, title):
    title = title.lower()
    if source == "Federal Reserve":
        if "fomc statement" in title:
            return "fomc"
        if "minutes" in title and "federal open market committee" in title:
            return "minutes"
        if "schedule" in title and "federal open market committee" in title:
            return "schedule"
    elif source == "European Central Bank":
        if "monetary policy decisions" in title:
            return "ecb"
        if "monetary policy meeting" in title and ("account" in title or "minutes" in title):
            return "minutes"
        if "ecb wage tracker" in title:
            return "wages"
    elif "monetary policy summary" in title or title.startswith("bank rate"):
        return "boe"
    return None


def policy_summary(topic, title, url, fetch):
    if topic == "boe":
        match = re.search(r"Bank Rate (increased to|reduced to|maintained at|held at) (\d+(?:\.\d+)?)%", title, re.I)
        return f"Bank Rate was {match[1].lower()} {match[2]}%." if match else ""
    if topic not in ("fomc", "ecb"):
        return ""
    try:
        body = text(fetch(url).decode("utf-8-sig", "replace"))
    except (OSError, ValueError):
        return ""
    if topic == "fomc":
        rate = r"\d+(?:[- ]\d+/\d+|\.\d+)?"
        match = re.search(rf"decided to (raise|lower|maintain|keep) the target range for the federal funds rate (?:by [^.]{{0,50}}? )?(?:at|to) ({rate}) (?:to|–|−) ({rate}) percent", body, re.I)
        if match:
            prep = "at" if match[1].lower() in ("keep", "maintain") else "to"
            return f"The Fed decided to {match[1].lower()} its target range {prep} {match[2]}% to {match[3]}%."
        return ""
    match = re.search(r"deposit facility, the main refinancing operations and the marginal lending facility.{0,100}?\b(?:at|to) (\d+(?:\.\d+)?)\s*%", body, re.I)
    return f"The ECB reported a deposit facility rate of {match[1]}%." if match else ""


def feed_items(body, source, feed_url, now):
    content = body.upper()
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise ValueError("Unsupported XML declarations")
    root = ET.fromstring(body)
    entries = root.findall("./channel/item")
    if not entries:
        raise ValueError("No RSS entries")
    host = urlsplit(feed_url).hostname
    for entry in entries:
        title = text(entry.findtext("title"))[:200]
        topic = topic_for(source, title)
        url = (entry.findtext("link") or "").strip()
        link = urlsplit(url)
        if not topic or link.scheme != "https" or link.netloc.lower() != host:
            continue
        try:
            date = parsedate_to_datetime(entry.findtext("pubDate") or "")
        except ValueError:
            continue
        if date.tzinfo is None or not now - dt.timedelta(days=45) <= date <= now:
            continue
        yield {"title": title, "source": source, "url": url, "published": timestamp(date),
               "context": CONTEXT[topic]}, topic


def timestamp(time):
    return time.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def release_items(events, now):
    for event in events:
        kind = kind_of(event)
        if kind not in CONTEXT or kind not in RELEASES or not event.get("actual") or not event.get("time"):
            continue
        published = when(event)
        if not now - dt.timedelta(days=21) <= published <= now:
            continue
        source = event.get("provenance") or {}
        series = source.get("series") or RELEASES[kind]["comps"][0][1]
        archive = source.get("via") == "ALFRED"
        url = source.get("url") or (f"{ALFRED}/series?seid={series}&vintage_date={source['asof']}"
                                    if archive else f"{FRED}/series/{series}")
        yield {"id": event["id"], "title": event["title"], "source": event["src"], "url": url,
               "published": timestamp(published), "analysis": event.get("recap") or recap(event, kind),
               "context": CONTEXT[kind]}


def build(events, previous, now, fetch=download, log=print):
    cutoff = timestamp(now - dt.timedelta(days=45))
    cached = {item["url"]: item for item in previous.get("items", [])
              if item.get("source") in FEEDS and item.get("published", "") >= cutoff}
    sources = {}
    for source, url in FEEDS.items():
        try:
            items = list(feed_items(fetch(url), source, url, now))
        except (OSError, ValueError, ET.ParseError) as error:
            sources[source] = False
            log(f"{source} feed unavailable: {error}")
            continue
        sources[source] = True
        for item, topic in items[:8]:
            old = cached.get(item["url"], {})
            if old.get("title") == item["title"] and old.get("analysis"):
                item["analysis"] = old["analysis"]
            else:
                item["analysis"] = policy_summary(topic, item["title"], item["url"], fetch)
            cached[item["url"]] = item
    items = [*release_items(events, now), *cached.values()]
    items.sort(key=lambda item: item["published"], reverse=True)
    checked_at = timestamp(now)
    prior_health = previous.get("sourceHealth", {})
    health = {source: {"state": "available" if ok else "unavailable", "checkedAt": checked_at,
                       "lastSuccessAt": checked_at if ok else prior_health.get(source, {}).get("lastSuccessAt")
                       or (previous.get("checkedAt") if previous.get("sources", {}).get(source) else None)}
              for source, ok in sources.items()}
    return {"checkedAt": checked_at, "sources": sources, "sourceHealth": health, "items": items[:20]}


if __name__ == "__main__":
    from pathlib import Path

    target = Path(DATA, "news", "latest.json")
    calendar = load(Path(DATA, "calendar", "events.json"), {"events": []})
    digest = build(calendar["events"], load(target, {}), NOW)
    save(target, digest)
    print(f"Published {len(digest['items'])} news items. Feed checks: {json.dumps(digest['sources'])}")
