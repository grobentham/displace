"""Keyless figures from the U.S. agencies that publish them."""
import datetime as dt
from functools import lru_cache
from html.parser import HTMLParser
import json
import math
import re
import xml.etree.ElementTree as ET

from publicdata import download

BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SERIES = {
    "CPIAUCSL": "CUSR0000SA0", "CPILFESL": "CUSR0000SA0L1E",
    "PAYEMS": "CES0000000001", "UNRATE": "LNS14000000", "CES0500000003": "CES0500000003",
    "PPIFIS": "WPSFD4", "JTSJOL": "JTS000000000000000JOL", "JTSQUR": "JTS000000000000000QUR",
}
CENSUS_RETAIL = "https://www.census.gov/retail/sales.html"
BEA_NEWS = "https://www.bea.gov/news/current-releases"
TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
                "?data=daily_treasury_yield_curve&field_tdr_date_value=")
NYFED_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/25.json"
DATA_NS = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"


def parse_bls(body, asof):
    data = json.loads(body)
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError("BLS did not return the requested series")
    output = {}
    for series in data["Results"]["series"]:
        rows = {}
        for item in series["data"]:
            if not re.fullmatch(r"M(?:0[1-9]|1[0-2])", item["period"]):
                continue
            try:
                day = dt.date(int(item["year"]), int(item["period"][1:]), 1).isoformat()
                value = float(item["value"])
            except ValueError:
                continue
            if day <= asof and math.isfinite(value):
                rows[day] = (day, value, asof)
        output[series["seriesID"]] = [rows[day] for day in sorted(rows)]
    return output


@lru_cache(maxsize=1)
def bls(asof):
    year = dt.date.fromisoformat(asof).year
    payload = json.dumps({"seriesid": list(BLS_SERIES.values()), "startyear": str(year - 2),
                          "endyear": str(year)}).encode()
    try:
        return parse_bls(download(BLS_URL, payload=payload), asof)
    except (OSError, ValueError, KeyError, TypeError):
        return {}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def page_text(body):
    parser = PageText()
    parser.feed(body.decode("utf-8-sig", "replace"))
    return " ".join(" ".join(parser.parts).split())


def retail_from_page(body):
    text = page_text(body)
    date = re.search(r"FOR IMMEDIATE RELEASE:\s*[A-Za-z]+, ([A-Za-z]+ \d{1,2}, \d{4})", text, re.I)
    reading = re.search(
        r"Advance estimates of U\.S\. retail and food services sales for ([A-Za-z]+ \d{4}).{0,400}?"
        r"\b(up|down) (\d+(?:\.\d+)?) percent.{0,100}?from the previous month", text, re.I)
    if not date or not reading:
        return None
    day = dt.datetime.strptime(date[1], "%B %d, %Y").date()
    period = dt.datetime.strptime(reading[1], "%B %Y").date()
    change = float(reading[3]) * (-1 if reading[2].lower() == "down" else 1)
    return day, period, change


@lru_cache(maxsize=1)
def retail():
    try:
        return retail_from_page(download(CENSUS_RETAIL))
    except (OSError, ValueError):
        return None


def parse_bea_report(kind, body):
    text = page_text(body)
    released = re.search(r"EMBARGOED UNTIL RELEASE AT.{0,80}?[A-Za-z]+, ([A-Za-z]+ \d{1,2}, \d{4})", text, re.I)
    if not released:
        return None
    day = dt.datetime.strptime(released[1], "%B %d, %Y").date()
    text = text[released.end():]
    if kind == "gdp":
        heading = re.search(r"GDP \((Advance|Second|Third) Estimate\).*?([1-4])(?:st|nd|rd|th) Quarter(?: and Year)? (\d{4})", text, re.I)
        reading = re.search(r"Real gross domestic product \(GDP\) (increased|decreased) at an annual rate of (\d+(?:\.\d+)?) percent", text, re.I)
        if heading and reading:
            period = dt.date(int(heading[3]), (int(heading[2]) - 1) * 3 + 1, 1)
            value = float(reading[2]) * (-1 if reading[1].lower() == "decreased" else 1)
            return day, period, heading[1].lower(), {"A191RL1Q225SBEA": value}
    else:
        heading = re.search(r"Personal Income and Outlays, ([A-Za-z]+ \d{4})", text, re.I)
        month = re.search(r"From the preceding month, (.*?)(?=From the same month|Compared with the same month|$)", text[:6500], re.I)
        if not heading or not month:
            return None
        values = {}
        for series, pattern in (("PCEPI", r"^the PCE price index(?: for [A-Za-z]+)?"),
                                ("PCEPILFE", r"Excluding food and energy, the PCE price index")):
            value = re.search(pattern + r" (?:(increased|decreased) (\d+(?:\.\d+)?) percent|(was unchanged))", month[1], re.I)
            if value:
                values[series] = 0.0 if value[3] else float(value[2]) * (-1 if value[1].lower() == "decreased" else 1)
        if values:
            return day, dt.datetime.strptime(heading[1], "%B %Y").date(), None, values
    return None


@lru_cache(maxsize=1)
def bea_links():
    try:
        source = download(BEA_NEWS).decode("utf-8")
        return re.findall(r'href="(/news/\d{4}/(?:gdp-|personal-income-and-outlays-)[a-z0-9-]+)"', source)
    except (OSError, ValueError):
        return []


@lru_cache(maxsize=2)
def bea_report(kind):
    prefix = "/gdp-" if kind == "gdp" else "/personal-income-and-outlays-"
    path = next((link for link in bea_links() if prefix in link), None)
    if path:
        url = "https://www.bea.gov" + path
        try:
            reading = parse_bea_report(kind, download(url))
            if reading:
                return (*reading, url)
        except (OSError, ValueError):
            pass
    return None


def treasury_from_xml(body):
    upper = body.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Unsupported Treasury XML declarations")
    rates = {key: {} for key in ("DGS2", "DGS10", "T10Y2Y")}
    for node in ET.fromstring(body).findall(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties"):
        date = dt.date.fromisoformat(node.findtext(DATA_NS + "NEW_DATE")[:10]).isoformat()
        for key, label in (("DGS2", "BC_2YEAR"), ("DGS10", "BC_10YEAR")):
            value = node.findtext(DATA_NS + label)
            if value:
                rates[key][date] = float(value)
        if date in rates["DGS10"] and date in rates["DGS2"]:
            rates["T10Y2Y"][date] = rates["DGS10"][date] - rates["DGS2"][date]
    return rates


@lru_cache(maxsize=2)
def treasury(year):
    try:
        return treasury_from_xml(download(TREASURY_URL + str(year)))
    except (OSError, ValueError, TypeError, ET.ParseError):
        return {}


@lru_cache(maxsize=1)
def nyfed():
    try:
        return json.loads(download(NYFED_URL))["refRates"]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def market_observations(series, start, today):
    if series in ("DGS2", "DGS10", "T10Y2Y"):
        years = range(dt.date.fromisoformat(start).year, today.year + 1)
        rows = {day: value for year in years for day, value in treasury(year).get(series, {}).items()}
        return [(day, rows[day], "") for day in sorted(rows) if start <= day <= today.isoformat()]
    field = {"DFF": "percentRate", "DFEDTARL": "targetRateFrom", "DFEDTARU": "targetRateTo"}.get(series)
    if field:
        return sorted((row["effectiveDate"], row[field], "") for row in nyfed()
                      if isinstance(row.get(field), (int, float)) and start <= row["effectiveDate"] <= today.isoformat())
    return []
