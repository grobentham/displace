"""Public St. Louis Fed calendar and CSV downloads. No account or key required."""
import csv
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from functools import lru_cache
from html.parser import HTMLParser
from io import StringIO
import math
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FRED = "https://fred.stlouisfed.org"
ALFRED = "https://alfred.stlouisfed.org"
BEA_CALENDAR = "https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics"
STATS = {"calls": 0, "errors": 0, "failed": []}
MAX_DOWNLOAD = 3 * 1024 * 1024


def download(url):
    request = Request(url, headers={"User-Agent": "Displace/1.0 (public economic data reader)"})
    with urlopen(request, timeout=12) as response:
        body = response.read(MAX_DOWNLOAD + 1)
    if len(body) > MAX_DOWNLOAD:
        raise ValueError("Download exceeded the size limit")
    return body


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
    params = {"id": series, "cosd": start}
    if vintage:
        params.update(vintage_date=vintage, coed=vintage)
        url = ALFRED + "/graph/alfredgraph.csv"
        column = f"{series}_{vintage.replace('-', '')}"
    else:
        url = FRED + "/graph/fredgraph.csv"
        column = series
    STATS["calls"] += 1
    try:
        return read_csv(download(url + "?" + urlencode(params)), column, start, vintage)
    except (OSError, ValueError):
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
    query = urlencode({"rid": release_id, "vs": start, "ve": end, "view": "month"})
    STATS["calls"] += 1
    try:
        source = download(FRED + "/releases/calendar?" + query).decode("utf-8")
        calendar = ReleaseCalendar(release_id)
        calendar.feed(source)
        dates = sorted(date for date in calendar.dates if start <= date <= end)
        # Empty or changed HTML must leave the existing schedule in place.
        if dates:
            return dates
    except (OSError, ValueError):
        pass
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
            return releases
    except (OSError, ValueError):
        pass
    failed("BEA calendar")
    return []
