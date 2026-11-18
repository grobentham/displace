"""Public St. Louis Fed calendar and CSV downloads. No account or key required."""
import csv
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from functools import lru_cache
from html.parser import HTMLParser
from io import StringIO
import math
import re
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source_health import record

FRED = "https://fred.stlouisfed.org"
ALFRED = "https://alfred.stlouisfed.org"
BEA_CALENDAR = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
STATS = {"calls": 0, "errors": 0, "failed": []}
MAX_DOWNLOAD = 3 * 1024 * 1024
FRED_AVAILABLE = True
ALFRED_AVAILABLE = True


def download(url, *, timeout=25, payload=None, tries=3):
    """GET (or POST JSON) with retries. GitHub's runners sometimes take ~5 s to resolve a host name or fail a
    lookup outright, so a short timeout or a single try makes healthy sources look down."""
    # St. Louis Fed servers stall requests whose User-Agent does not look like a browser; this one is answered.
    headers = {"User-Agent": "Mozilla/5.0 (Displace data engine; +https://github.com/grobentham/displace)"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(tries):
        try:
            with urlopen(Request(url, data=payload, headers=headers), timeout=timeout) as response:
                body = response.read(MAX_DOWNLOAD + 1)
            break
        except HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        except (URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
        time.sleep(2 * (attempt + 1))
    if len(body) > MAX_DOWNLOAD:
        raise ValueError("Download exceeded the size limit")
    return body


def check_fred_access(today):
    """Skip repeated requests to a host that timed out on this runner."""
    global FRED_AVAILABLE, ALFRED_AVAILABLE
    start = (today - dt.timedelta(days=90)).isoformat()
    vintage = (today - dt.timedelta(days=1)).isoformat()
    urls = (FRED + f"/graph/fredgraph.csv?id=DGS2&cosd={start}",
            ALFRED + f"/graph/alfredgraph.csv?id=CPIAUCSL&cosd={start}&coed={vintage}&vintage_date={vintage}")

    def reachable(url):
        try:
            return b"observation_date," in download(url, timeout=25)[:96].lower()
        except (OSError, ValueError):
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        FRED_AVAILABLE, ALFRED_AVAILABLE = pool.map(reachable, urls)
    record("fred", FRED_AVAILABLE)
    record("alfred", ALFRED_AVAILABLE)


def read_csv(body, column, start, vintage=""):
    reader = csv.DictReader(StringIO(body.decode("utf-8-sig")))
    if not reader.fieldnames or column not in reader.fieldnames:
        raise ValueError("The expected series is missing")
    date_key = reader.fieldnames[0]
    if date_key.lower() not in {"date", "observation_date"}:
        raise ValueError("The observation date column is missing")
    rows = {}
    for row in reader:
        raw = row.get(column)
        if raw in (None, "", "."):
            continue
        date = dt.date.fromisoformat(row[date_key]).isoformat()
        value = float(raw)
        if date >= start and math.isfinite(value):
            rows[date] = (date, value, vintage)
    return [rows[date] for date in sorted(rows)]


def failed(label):
    STATS["errors"] += 1
    STATS["failed"].append(label)


@lru_cache(maxsize=256)
def observations(series, start, vintage=""):
    """A current FRED series, or the series exactly as available on an ALFRED vintage date."""
    if not (ALFRED_AVAILABLE if vintage else FRED_AVAILABLE):
        return None
    params = {"id": series, "cosd": start}
    if vintage:
        params.update(vintage_date=vintage, coed=vintage)
        url = ALFRED + "/graph/alfredgraph.csv"
        column = f"{series}_{vintage.replace('-', '')}"
    else:
        url = FRED + "/graph/fredgraph.csv"
        column = series
    STATS["calls"] += 1
    provider = "alfred" if vintage else "fred"
    try:
        rows = read_csv(download(url + "?" + urlencode(params)), column, start, vintage)
        record(provider, True)
        return rows
    except (OSError, ValueError):
        record(provider, False)
        failed(series)
        return None


def prefetch_observations(requests):
    with ThreadPoolExecutor(max_workers=4) as pool:
        for _ in pool.map(lambda args: observations(*args), requests):
            pass


class ReleaseCalendar(HTMLParser):
    """Collect dated rows for one release ID in the public release calendar."""

    def __init__(self, release_id):
        super().__init__()
        self.link = f"/release?rid={release_id}"
        self.dates = set()
        self.day = None
        self.cells = None
        self.matched = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells = []
            self.matched = False
        elif tag == "td" and self.cells is not None:
            self.cells.append("")
        elif tag == "a" and self.cells and dict(attrs).get("href") == self.link:
            self.matched = True

    def handle_data(self, data):
        if self.cells:
            self.cells[-1] += " " + data

    def handle_endtag(self, tag):
        if tag != "tr" or not self.cells:
            return
        first = " ".join(self.cells[0].split())
        date = re.match(r"^[A-Za-z]+ ([A-Za-z]+ \d{1,2}, \d{4})\b", first)
        if date:
            self.day = dt.datetime.strptime(date[1], "%B %d, %Y").date().isoformat()
        elif self.day and self.matched and re.fullmatch(r"\d{1,2}:\d{2} (?:am|pm)", first, re.I):
            self.dates.add(self.day)
        self.cells = None


@lru_cache(maxsize=64)
def release_dates(release_id, start, end):
    if not FRED_AVAILABLE:
        return None
    query = urlencode({"rid": release_id, "vs": start, "ve": end, "view": "month"})
    STATS["calls"] += 1
    try:
        source = download(FRED + "/releases/calendar?" + query).decode("utf-8")
        calendar = ReleaseCalendar(release_id)
        calendar.feed(source)
        dates = sorted(date for date in calendar.dates if start <= date <= end)
        # Empty or changed HTML must leave the existing schedule in place.
        if dates:
            record("fred", True)
            return dates
    except (OSError, ValueError):
        pass
    record("fred", False)
    failed(f"release {release_id}")
    return None


def parse_bea_calendar(body, tz):
    source = re.sub(r"\r?\n[ \t]", "", body.decode("utf-8-sig"))
    if not source.startswith("BEGIN:VCALENDAR"):
        raise ValueError("Invalid BEA calendar")
    for event in source.split("BEGIN:VEVENT")[1:]:
        title = re.search(r"^SUMMARY:(.+)$", event, re.M)
        start = re.search(r"^DTSTART(?:;VALUE=DATE-TIME)?:(\d{8}T\d{6}Z)", event, re.M)
        if not title or not start:
            continue
        published = dt.datetime.strptime(start[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).astimezone(tz)
        pce = re.match(r"Personal Income and Outlays\\?, ([A-Za-z]+) \d{4}\b", title[1])
        gdp = re.match(r"GDP \((Advance|Second|Third) Estimate\).*?([1-4])(?:st|nd|rd|th) Quarter", title[1])
        if pce:
            yield "pce", published, pce[1][:3], None
        elif gdp:
            yield "gdp", published, f"Q{gdp[2]}", gdp[1].lower()


def bea_releases(tz):
    STATS["calls"] += 1
    try:
        releases = list(parse_bea_calendar(download(BEA_CALENDAR), tz))
        if releases:
            record("bea", True)
            return releases
    except (OSError, ValueError):
        pass
    record("bea", False)
    failed("BEA calendar")
    return []
