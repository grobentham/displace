"""Build crawlable, escaped static report pages and project sitemap.
The archived JSON remains authoritative; this is a derived presentation.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import html
import json
import re
import os
from pathlib import Path
from xml.etree import ElementTree as ET
import exchange
from exchange import NY
import publisher

ROOT=Path(__file__).resolve().parent.parent
SITE=ROOT/"site"
BASE=publisher.BASE
PAGES=("research-hub.html","macro.html","signals.html","relationships.html","atlas.html","research.html",
       "research-v2.html","research-v3.html","publications.html","open.html","search.html","backtest.html","validation.html","mnq-brief.html",
       "replay-a-release.html","mnq-position-size.html","futures-hours.html")
HEADER='<nav class="gnav" aria-label="Site"><div class="wide"><a class="brand" href="../index.html#top"><svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true"><defs><linearGradient id="dlg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2997ff"/><stop offset=".6" stop-color="#30d158"/><stop offset="1" stop-color="#ff9f0a"/></linearGradient></defs><rect width="26" height="26" rx="7" fill="url(#dlg)"/><rect x="5" y="13" width="4" height="7" rx="1" fill="#fff" opacity=".75"/><rect x="11" y="6" width="4" height="14" rx="1" fill="#fff"/><rect x="17" y="4" width="4" height="6" rx="1" fill="#fff" opacity=".75"/><rect x="9.5" y="10" width="7" height="3" rx="1" fill="#fff" opacity=".35"/></svg>Displace</a><ul><li><a href="../index.html#bias">Today</a></li><li><a href="../index.html#intraday-bias">Bias</a></li><li><a href="../index.html#calendar">News</a></li><li><a href="../index.html#tools">Tools</a></li><li><a href="../research-hub.html" aria-current="page">Research</a></li><li><a href="../world/index.html">World</a></li><li><a href="/iron-brain/">Intraday ›</a></li></ul><div class="navr"><a class="navsrch" href="../search.html" aria-label="Search Displace"><svg width="17" height="17" viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><line x1="11" y1="11" x2="15" y2="15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></a><a class="pillbtn" href="../index.html#bias">Today\'s bias</a></div></div></nav><nav class="rnav" aria-label="Research"><div class="wide"><a href="../research-hub.html">Overview</a><a href="../research-v3.html">Discovery</a><a href="../validation.html">Validation</a><a href="../open.html">Accountability</a><a href="../publications.html" aria-current="page">Publications</a><a href="../macro.html">Macro</a><a href="../signals.html">Warnings</a><a href="../relationships.html">Relationships</a><a href="../atlas.html">Atlas</a></div></nav>'   # the site's header and research menu, for pages one folder down


def gnav(prefix="../"):
    return HEADER

def esc(x):
    return html.escape(str(x),quote=True)

def page(r):
    publisher.validate_report(r)
    title=esc(r["title"])
    sections="".join('<section class="panel"><h2>'+esc(b["title"])+'</h2><ul>'+
                     "".join("<li>"+esc(line)+"</li>" for line in b["lines"])+"</ul></section>" for b in r["sections"])
    sources="".join('<p class="dp-source"><a href="../data/'+esc(s["path"])+'">'+esc(s["path"])+'</a> · '+esc(s.get("asof") or "Unavailable")+
                    '<br><span class="dp-hash">SHA-256 '+esc(s["sha256"])+'</span></p>' for s in r["sources"])
    url=BASE+"reports/"+r["id"]+".html"
    desc=esc(r["sections"][0]["lines"][0][:155])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | Displace</title><meta name="description" content="{desc}">
<link rel="canonical" href="{url}"><link rel="stylesheet" href="../assets/intelligence.css?v=20261124e">
<meta property="og:type" content="article"><meta property="og:title" content="{title}"><meta property="og:url" content="{url}">
</head><body><a class="dp-skip" href="#content">Skip to content</a>{gnav()}
<main id="content" class="dp-report"><header><p class="muted"><a href="../publications.html">Research publications</a> · {esc(r["kind"])}</p><h1>{title}</h1><p class="muted">Generated <time datetime="{esc(r["generated_at"])}">{esc(r["generated_at"])}</time> · UTC snapshot</p></header>
{sections}<section class="panel"><h2>Source evidence</h2>{sources}<p>{esc(r["limitations"])}</p><p><a href="../data/publications/reports/{esc(r["id"])}.json">Original report JSON</a> · <a href="../open.html">Displace Open</a></p></section></main></body></html>\n'''

def build_mnq_brief(data):
    """Publish a public, date-addressable snapshot of the NQ outlook used by MNQ traders."""
    bias_path=data/"bias/current.json"
    if not bias_path.is_file():
        return
    bias=publisher.load(bias_path)
    nq=bias.get("markets",{}).get("nq")
    if not nq:
        return
    session=nq.get("session") or {}
    day=date.fromisoformat(session.get("date") or bias["for"]).isoformat()

    calendar_path=data/"calendar/events.json"
    news=None
    if calendar_path.is_file():
        news=[]
        events=publisher.load(calendar_path).get("events",[])
        for event in events:
            if event.get("date")!=day or event.get("impact") not in ("high","medium"):
                continue
            time=event.get("time")
            try:
                instant=datetime.fromisoformat(day+"T"+time).replace(tzinfo=NY).isoformat() if time else None
            except (TypeError,ValueError):
                continue
            news.append({"title":event["title"],"instant":instant,"time_ny":time,"impact":event["impact"]})
        news.sort(key=lambda event: event["time_ny"] or "")

    evidence_path=data/"open/current.json"
    live_count=(publisher.load(evidence_path).get("by_market",{}).get("nq",{}).get("n")
                if evidence_path.is_file() else None)
    brief={
        "date":day,
        "asof":nq.get("forecast_at", bias["asof"]),
        "session":{key:session.get(key) for key in ("open","close","halts")},
        "range":{key:nq["range"].get(key) for key in ("points","lo","hi")},
        "levels":{key:{"price":nq["levels"].get(key),"probability":nq["takes"][key].get("p")}
                  for key in ("high","low")},
        "news":news,
        "live_count":live_count,
    }
    if nq.get("forecast_id"):
        brief["forecast_id"] = nq["forecast_id"]
    folder=data/"briefs/mnq"
    publisher.jsonwrite(folder/(day+".json"),brief)
    publisher.jsonwrite(folder/"latest.json",brief)


def format_points(value, decimals):
    rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    formatted = f"{rounded:,.{decimals}f}"
    return formatted.rstrip("0").rstrip(".") if decimals else formatted


def build_session_pages(site):
    """Give each market and session a stable link with a preview visible to crawlers."""
    data = site / "data"
    bias_path = data / "bias/current.json"
    if not bias_path.is_file():
        return []
    bias = publisher.load(bias_path)
    calendar_path = data / "calendar/events.json"
    events = publisher.load(calendar_path)["events"] if calendar_path.is_file() else []
    day_paths = []
    for key, name in (("nq", "MNQ"), ("es", "ES"), ("gold", "Gold")):
        item = bias["markets"].get(key)
        if not item or not item.get("session"):
            continue
        session = item["session"]
        day = date.fromisoformat(session["date"]).isoformat()
        path = f"sessions/{key}/{day}.html"
        title = f"{name} session brief · {day}"
        points = lambda value: format_points(value, int(key == "gold"))
        band = f'{points(item["range"]["lo"])}–{points(item["range"]["hi"])}'
        summary = f"Historical 80% range band of {band} points, prior session levels, and scheduled news."
        def stamp(value):
            at = datetime.fromisoformat(value).astimezone(NY)
            return f'<time datetime="{esc(value)}" data-local>{at:%b %d, %H:%M} New York</time>'
        opens = datetime.fromisoformat(session["open"])
        close = datetime.fromisoformat(session["close"]) if session.get("close") else None
        scheduled = []
        for event in events:
            if not event.get("time") or event["impact"] not in ("high", "medium"):
                continue
            try:
                at = datetime.fromisoformat(event["date"] + "T" + event["time"]).replace(tzinfo=NY)
            except ValueError:
                continue
            if (close and opens <= at < close) or (not close and event["date"] == day):
                scheduled.append(f'<div class="mc-row">{stamp(at.isoformat())}<div class="mc-rt">{esc(event["title"])}</div></div>')
        news = "".join(scheduled) or '<p class="mc-muted">No major scheduled releases in the available calendar.</p>'
        levels = "".join(f'<div class="mc-row"><b>Prior {side}</b> {item["levels"][side]:,.{item.get("dp", 2)}f} · {item["takes"][side]["p"]:.0%} historical estimate</div>' for side in ("high", "low"))
        hours = stamp(session["open"]) + (' to ' + stamp(session["close"]) if close else ' · Close time unavailable')
        hours += "".join(" · Holiday halt at " + stamp(at) for at in session.get("halts", []))
        made = item.get("forecast_at", bias["asof"])
        late = " Generated after the open and excluded from prospective scoring." if datetime.fromisoformat(made) >= opens else ""
        body = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · Displace</title><meta name="description" content="{esc(summary)}">
<link rel="canonical" href="{BASE}{path}"><meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)} · Displace"><meta property="og:description" content="{esc(summary)}">
<meta property="og:url" content="{BASE}{path}"><meta property="og:image" content="{BASE}og.png">
<link rel="stylesheet" href="../../assets/morning.css?v=20261126"><script src="../../assets/session-brief.js" defer></script>
</head><body class="mnq-brief">
<header class="mnq-brief-nav"><div class="wide"><a class="mnq-brief-brand" href="../../index.html">Displace</a><a href="../../index.html#calendar">Economic calendar</a></div></header>
<main class="mc"><div class="wide"><p class="mc-for">{day}</p><h1 class="mc-q">{esc(name)} session brief</h1>
<div class="mc-answer"><div class="mc-big"><span id="brief-range">{points(item['range']['points'])}</span><small>points, expected high-to-low</small></div>
<p class="mc-range">80% range band: {band} points.</p><p class="mc-window">Session hours · {hours}</p></div>
<div class="mc-grid"><section class="mc-card"><h2>Prior session levels</h2>{levels}</section><section class="mc-card"><h2>Scheduled news</h2>{news}</section></div>
<p class="mc-foot">Forecast made {stamp(made)}.{late} <a href="../../open.html#ledger">Forecast ledger</a></p>
<p class="mnq-brief-action"><a class="mnq-brief-button" href="../../index.html?market={key}#session-plan">Plan my session</a></p>
</div></main></body></html>\n'''
        publisher.write(site / path, body)
        day_paths.append(path)
    return day_paths


def build_session_tools(data):
    calendar = data / "calendar/events.json"
    archive = data / "bars/nq-5m.json"
    if calendar.is_file() and archive.is_file():
        times = {row[0] for row in publisher.load(archive)["rows"]}
        releases = []
        for event in publisher.load(calendar)["events"]:
            if event.get("impact") != "high" or not event.get("time") or not event.get("actual"):
                continue
            at = datetime.fromisoformat(event["date"] + "T" + event["time"]).replace(tzinfo=NY)
            release = int(at.timestamp())
            if all(t in times for t in range(release - 1800, release + 1800, 300)):
                releases.append({"id": event["id"], "title": event["title"], "at": at.isoformat(),
                                 "start": release - 1800, "end": release + 7200})
        publisher.jsonwrite(data / "briefs/replay.json", {"releases": sorted(releases, key=lambda item: item["at"], reverse=True)[:24]})

    bias = data / "bias/current.json"
    if bias.is_file():
        start = datetime.fromisoformat(publisher.load(bias)["asof"]).astimezone(NY).date()
        days = []
        for row in exchange.summary("nq", start, start + timedelta(days=180)):
            if row["status"] == "trade":
                continue
            session = exchange.session("nq", row["date"])
            hours = session["close"].strftime("Closes %H:%M New York") if session else (
                "Holiday halt begins 13:00 New York" if row["status"] == "halt" else "Closed")
            days.append({**row, "hours": hours})
        publisher.jsonwrite(data / "briefs/exchange-hours.json", {"asof": start.isoformat(), "days": days})


def build(site):
    data=site/"data"
    publisher.check(data)
    build_mnq_brief(data)
    session_paths = build_session_pages(site)
    build_session_tools(data)
    catalog=publisher.load(data/"publications/index.json")
    folder=site/"reports"
    folder.mkdir(parents=True,exist_ok=True)
    expected=set()
    for entry in catalog["reports"]:
        r=publisher.load(data/"publications"/entry["path"])
        name=r["id"]+".html"
        expected.add(name)
        publisher.write(folder/name,page(r))
    # Remove only obsolete files generated by this builder (never arbitrary files).
    for path in folder.glob("*.html"):
        if path.name not in expected and re.fullmatch(r"(daily|signal|research|weekly|monthly)-[a-z0-9-]+\.html",path.name):
            raise ValueError("Unexpected orphaned report page; review before deletion: "+path.name)
    ns="http://www.sitemaps.org/schemas/sitemap/0.9"
    root=ET.Element("urlset",xmlns=ns)
    try:
        world_urls=[u for u in json.loads((data/"world/urls.json").read_text())["urls"] if re.fullmatch(r"world/[a-z0-9/._-]+\.html",u)]
    except (OSError,ValueError,KeyError):
        world_urls=[]
    for path in [""]+list(PAGES)+["reports/"+name for name in sorted(expected)]+session_paths+world_urls:
        url=ET.SubElement(root,"url")
        ET.SubElement(url,"loc").text=BASE+path
    publisher.write(site/"sitemap.xml",ET.tostring(root,encoding="unicode",xml_declaration=True)+"\n")
    return len(expected)

def main():
    print("site build:",build(SITE),"static report pages")
if __name__=="__main__":
    main()
