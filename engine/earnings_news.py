"""Read company-published quarterly results and extract unambiguous headline figures."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from earnings import WATCH
from news import text
from publicdata import download

FEEDS = {
    "NVDA": "https://investor.nvidia.com/rss/PressRelease.aspx",
    "AMZN": "https://ir.aboutamazon.com/rss/PressRelease.aspx",
    "META": "https://investor.atmeta.com/rss/PressRelease.aspx",
    "ORCL": "https://investor.oracle.com/rss/PressRelease.aspx",
    "AMD": "https://ir.amd.com/rss/news-releases.xml",
    "AAPL": "https://www.apple.com/newsroom/rss-feed.rss",
}
ATOM = "{http://www.w3.org/2005/Atom}"
RESULTS = re.compile(r"\b(?:announces?|reports?)\b.*\bresults\b", re.I)
PERIOD = re.compile(r"\b(?:quarter|full.year|fiscal year|Q[1-4])\b", re.I)
SCHEDULE = re.compile(r"\b(?:to announce|to report|will report|sets? (?:the |a )?date|conference call|webcast)\b", re.I)
SALES = re.compile(r"(?:^|[.!?]\s+)\s*(?:total\s+)?(?:revenue|net sales)\s*"
                   r"(?:of|was|were|increased.{0,40}?\bto|decreased.{0,40}?\bto)\s*"
                   r"(?P<sales>\$[\d,.]+\s+(?:billion|million))"
                   r"(?P<tail>[^.]{0,115})", re.I)
REPORTED_SALES = re.compile(r"\b(?:reported|posted) (?:(?:quarterly|total) )?(?:revenue|net sales)\b[^.$]{0,110}"
                            r"(?P<sales>\$[\d,.]+\s+(?:billion|million))(?P<tail>[^.]{0,115})", re.I)
YOY = re.compile(r"\b(?P<direction>up|down)\s+(?P<percent>\d+(?:\.\d+)?)(?:%| percent)\s+"
                 r"(?:from a year ago|year.over.year|from the prior.year quarter)", re.I)
DILUTED = re.compile(r"\bGAAP and non-GAAP (?:earnings per diluted share|diluted earnings per share) were "
                     r"(?P<eps>\$\d+\.\d{2})\s+and\s+\$\d+\.\d{2}, respectively", re.I)
GUIDANCE = re.compile(r"\boutlook for the (?:first|second|third|fourth) quarter[^.]{0,185}?as follows:\s*"
                      r"revenue is expected to be (?P<sales>\$[\d,.]+\s+(?:billion|million))"
                      r"(?:, plus or minus (?P<range>\d+(?:\.\d+)?)%)?", re.I)


def report_items(body, feed, start, cutoff):
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unsupported XML declarations")
    root = ET.fromstring(body)
    for item in root.findall("./channel/item") + root.findall(f"./{ATOM}entry"):
        title = text(item.findtext("title") or item.findtext(f"{ATOM}title"))
        if not RESULTS.search(title) or not PERIOD.search(title) or SCHEDULE.search(title):
            continue
        pub = item.findtext("pubDate")
        if pub:
            at = parsedate_to_datetime(pub)
        else:
            at = dt.datetime.fromisoformat(item.findtext(f"{ATOM}published") or item.findtext(f"{ATOM}updated"))
        link = item.findtext("link") or next((node.get("href", "") for node in item.findall(f"{ATOM}link")
                                             if node.get("rel", "alternate") == "alternate"), "")
        url = urlsplit(link)
        if at.tzinfo and start <= at <= cutoff and url.scheme == "https" and url.netloc == urlsplit(feed).netloc:
            yield at, title, link


def report_metrics(body):
    article = text(body.decode("utf-8-sig", "replace"))
    # The issuer's narrative can include per-segment sales and future guidance. Use only explicit total figures.
    match = REPORTED_SALES.search(article) or SALES.search(article)
    metrics = []
    if match:
        growth = YOY.search(match["tail"])
        total = match["sales"]
        if growth:
            total += f" ({growth['direction'].lower()} {growth['percent']}% year over year)"
        metrics.append({"label": "Revenue", "value": total})
    if match := DILUTED.search(article):
        metrics.append({"label": "GAAP diluted EPS", "value": match["eps"]})
    if match := GUIDANCE.search(article):
        band = f" ±{match['range']}%" if match["range"] else ""
        metrics.append({"label": "Next-quarter revenue guidance", "value": match["sales"] + band})
    return metrics


def report_summary(metrics):
    return " ".join(f"{item['label']} {item['value']}." for item in metrics)


def release_page(ticker, url):
    # NVIDIA publishes the same release on both its investor site and its newsroom.
    if ticker == "NVDA":
        slug = urlsplit(url).path.split("/")[-2].lower()
        return "https://nvidianews.nvidia.com/news/" + slug
    return url


def get_reports(start, cutoff, fetch=download, log=print):
    def read(pair):
        ticker, feed = pair
        try:
            items = sorted(report_items(fetch(feed, timeout=20), feed, start, cutoff), reverse=True)
        except (OSError, ValueError, TypeError, ET.ParseError) as error:
            log(f"Earnings feed unavailable for {ticker}: {error}")
            return None
        if not items:
            return []
        at, title, url = items[0]
        page = release_page(ticker, url)
        metrics = []
        try:
            metrics = report_metrics(fetch(page, timeout=20))
        except (OSError, ValueError) as error:
            log(f"Earnings figures unavailable for {ticker}: {error}")
        return [(at, {"symbol": ticker, "title": title, "url": page if metrics else url,
                      "published": at.isoformat(timespec="seconds"), "metrics": metrics, "summary": report_summary(metrics)})]

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(read, FEEDS.items()))
    reports = sorted((row for batch in batches if batch for row in batch), key=lambda row: row[0], reverse=True)
    reports.sort(key=lambda row: WATCH[row[1]["symbol"]][1] != "mega")
    return [report for _, report in reports[:2]], sum(batch is not None for batch in batches)
