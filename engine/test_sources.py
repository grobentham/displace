"""Keyless sources: the Fed decision from the statement or the New York Fed, release-day reactions from the
cached history, and the FRED key fallback. Offline."""
import datetime as dt
import json
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["ENGINE_NOW"] = "2026-12-10T10:00:00-05:00"

import agencies  # noqa: E402
import consensus  # noqa: E402
import engine as E  # noqa: E402
import fredapi  # noqa: E402
import publicdata  # noqa: E402
import series_store  # noqa: E402

STATEMENT = b"""<html><body><div id="article"><p>Recent indicators suggest that economic activity has continued
to expand at a solid pace.</p><p>In support of its goals, the Committee decided to lower the target range for the
federal funds rate by 1/4 percentage point to 3-1/2 to 3-3/4 percent. In considering the extent and timing of
additional adjustments...</p></div></body></html>"""
HOLD = b"<p>the Committee decided to maintain the target range for the federal funds rate at 4.25 to 4.50 percent.</p>"


def fed_decision():
    assert agencies.rate_number("3-3/4") == 3.75 and agencies.rate_number("4") == 4.0
    assert agencies.decision_from_statement(STATEMENT) == (3.5, 3.75)
    assert agencies.decision_from_statement(HOLD) == (4.25, 4.5)
    assert agencies.decision_from_statement(b"<p>No decision here.</p>") is None

    ev = {"id": "fomc", "date": "2026-12-09", "time": "14:00", "title": "FOMC rate decision + projections (dot plot)"}
    nyfed = [("2026-12-08", 4.0, ""), ("2026-12-09", 4.0, ""), ("2026-12-10", 3.75, "")]
    agencies.market_observations = lambda s, start, today: [r for r in nyfed if start <= r[0] <= today.isoformat()]
    agencies.fed_decision = lambda day, tz: (3.75, "https://www.federalreserve.gov/x.htm")
    act, prev, _, src = E.agency_figures(ev, "fomc", "DFEDTARU", "rate", True)
    assert (act, prev, src["via"]) == ("3.75%", "4.00%", "Federal Reserve"), (act, prev, src)
    agencies.fed_decision = lambda day, tz: None  # statement unreadable: next day's New York Fed range
    act, prev, _, src = E.agency_figures(ev, "fomc", "DFEDTARU", "rate", True)
    assert (act, src["via"]) == ("3.75%", "New York Fed"), (act, src)
    act, prev, _, _ = E.agency_figures(ev, "fomc", "DFEDTARU", "rate", False)
    assert act is None and prev == "4.00%"
    print("fed decision ok")


def reactions_keyless():
    tmp = tempfile.mkdtemp()
    series_store.CACHE_DIR = tmp
    rnd = random.Random(3)
    day, rows2, rows10, v2, v10 = dt.date(2023, 1, 2), [], [], 4.0, 3.8
    claims_rel = set()
    while day < E.TODAY:
        if day.weekday() < 5:
            big = day.weekday() == 3  # claims days move yields more in this world
            v2 += rnd.gauss(0, 0.08 if big else 0.03)
            v10 += rnd.gauss(0, 0.05 if big else 0.02)
            rows2.append([day.isoformat(), v2, ""])
            rows10.append([day.isoformat(), v10, ""])
            if big:
                claims_rel.add(day.isoformat())
        day += dt.timedelta(days=1)
    json.dump({"rows": rows2}, open(os.path.join(tmp, "DGS2.json"), "w"))
    json.dump({"rows": rows10}, open(os.path.join(tmp, "DGS10.json"), "w"))
    icsa = [[(dt.date.fromisoformat(d) - dt.timedelta(days=5)).isoformat(), 220000, d] for d in sorted(claims_rel)]
    json.dump({"rows": icsa}, open(os.path.join(tmp, "ICSA.initial.json"), "w"))
    fredapi.KEY, publicdata.FRED_AVAILABLE = "", False
    agencies.market_observations = lambda *a: []
    rx = E.reactions([])
    s = rx["series"]["claims"]
    assert len(s["rows"]) == 26 and s["ratio"]["y2"] > 1.5, s["ratio"]
    assert "cpi" not in rx["series"], "reactions for a report with no release dates"
    print("keyless reactions ok:", s["ratio"])


def fred_fallback():
    fredapi.KEY = "set-but-blocked"
    real = fredapi.urllib.request.urlopen
    fredapi.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))
    try:
        assert fredapi.probe() is False
    finally:
        fredapi.urllib.request.urlopen = real
        fredapi.KEY = ""
    print("fred probe ok")


def consensus_feed():
    import zoneinfo
    ny = zoneinfo.ZoneInfo("America/New_York")
    events = [{"id": "c", "date": "2026-11-19", "time": "08:30", "title": "Initial jobless claims"},
              {"id": "j", "date": "2026-12-01", "time": "10:00", "title": "JOLTS job openings (Oct)"},
              {"id": "r", "date": "2026-11-17", "time": "08:30", "title": "Retail sales (Oct)", "actual": "0.2%", "forecast": "0.2%"},
              {"id": "m", "date": "2026-11-20", "time": "10:00", "title": "UMich consumer sentiment, final (Nov)"}]
    feed = [{"title": "Unemployment Claims", "country": "USD", "date": "2026-11-19T08:30:00-05:00", "forecast": "198K"},
            {"title": "JOLTS Job Openings", "country": "USD", "date": "2026-12-01T10:00:00-05:00", "forecast": "7.20M"},
            {"title": "Retail Sales m/m", "country": "USD", "date": "2026-11-17T08:30:00-05:00", "forecast": "0.1%"},
            {"title": "Revised UoM Consumer Sentiment", "country": "USD", "date": "2026-11-20T10:00:00-05:00", "forecast": "51.7"},
            {"title": "Unemployment Claims", "country": "CAD", "date": "2026-11-19T08:30:00-05:00", "forecast": "9K"}]
    tmp = tempfile.mkdtemp()
    consensus.ARCHIVE = os.path.join(tmp, "consensus.json")
    n = consensus.apply(events, E.kind_of, ny, manual_ids={"m"}, fetch=lambda url: json.dumps(feed).encode(), log=lambda *a: None)
    got = {e["id"]: e.get("forecast") for e in events}
    assert got == {"c": "198K", "j": "7.2M", "r": "0.2%", "m": None} and n == 2, got
    arch = json.load(open(consensus.ARCHIVE))
    assert set(arch) == {"c", "j", "r", "m"}, arch  # every consensus seen is archived, even when not applied
    print("consensus feed ok")


def tv_consensus():
    raw = [{"t": "Initial Jobless Claims", "d": "2026-11-19T13:30:00Z", "a": None, "f": 197},
           {"t": "CB Consumer Confidence", "d": "2026-11-24T15:00:00Z", "a": None, "f": 92},
           {"t": "GDP Growth Rate QoQ 2nd Est", "d": "2026-11-25T13:30:00Z", "a": None, "f": 3.3},
           {"t": "New Home Sales", "d": "2026-11-25T15:00:00Z", "a": None, "f": 0.67},
           {"t": "Core Inflation Rate MoM", "d": "2026-10-14T12:30:00Z", "a": 0.3, "f": 0.2}]
    events = [{"id": "c", "date": "2026-11-19", "time": "08:30", "title": "Initial jobless claims", "forecast": "198K"},
              {"id": "b", "date": "2026-11-24", "time": "10:00", "title": "Consumer confidence (Nov)"},
              {"id": "g", "date": "2026-11-25", "time": "08:30", "title": "GDP, second estimate (Q3)"},
              {"id": "h", "date": "2026-11-25", "time": "10:00", "title": "New home sales (Oct)"}]
    n = consensus.apply_tv(events, E.kind_of, raw=raw, log=lambda *a: None)
    got = {e["id"]: e.get("forecast") for e in events}
    assert got == {"c": "198K", "b": "92.0", "g": "3.3%", "h": "670K"} and n == 3, got  # existing forecast kept
    hist = {"series": {"cpi": {"rows": [{"period": "Sep 2026", "date": "2026-10-14", "actual": "0.3%", "forecast": ""}]}}}
    assert consensus.backfill_history(hist, raw=raw) == 1 and hist["series"]["cpi"]["rows"][0]["forecast"] == "0.2%"
    print("tv consensus ok")


if __name__ == "__main__":
    fed_decision()
    reactions_keyless()
    fred_fallback()
    consensus_feed()
    tv_consensus()
    print("source tests passed")
