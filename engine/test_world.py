"""Tests for Displace World: parsers, rules, the frozen ledger, grading and the full run on fake sources.
Runs offline: every network call is answered from fixtures below. python engine/test_world.py
"""
import datetime as dt
import json
import math
import shutil
import tempfile
from pathlib import Path

import world_fetch as FE
import world_ledger as L
import world_markets as M
import world_nlp as N
import world_publish as P
import world_resolve as R
import world_signals as W
import world_sources as S

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 27, 0, 20, tzinfo=UTC)          # 08:20 Singapore


def gdelt_timeline(days, spike_day=None):
    pts = []
    for d in days:
        v = 100 + (hash(d) % 7)
        if d == spike_day:
            v = 420
        pts.append({"date": d.replace("-", "") + "T000000Z", "value": v, "norm": 100000})
    return json.dumps({"timeline": [{"series": "Article Count", "data": pts}]})


def gdelt_articles(titles, start):
    arts = []
    for i, t in enumerate(titles):
        seen = (start + dt.timedelta(minutes=10 * i)).strftime("%Y%m%dT%H%M%SZ")
        arts.append({"url": f"https://news{i}.example.com/a{i}", "title": t, "seendate": seen, "domain": f"news{i}.example.com",
                     "language": "English" if i % 3 else "Spanish", "sourcecountry": ["United States", "Singapore", "Japan"][i % 3]})
    return json.dumps({"articles": arts})


DAYS = [(NOW.date() - dt.timedelta(days=k)).isoformat() for k in range(60, 0, -1)]
YESTERDAY = (NOW.date() - dt.timedelta(days=1)).isoformat()
TITLES = ["Chipmaker TSMC warns of export controls on advanced chips", "TSMC warns export controls could hit advanced chips",
          "Export controls: TSMC warns on advanced chips sales", "Nvidia shares fall as chip curbs widen",
          "Samsung foundry wins new order", "Memory chip prices rise again, says Micron"]
ACCEPTED = (NOW - dt.timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fake_get(url, source, **k):
    if "gdeltproject" in url:
        if "timelinevolraw" in url:
            return gdelt_timeline(DAYS, YESTERDAY if "semiconductor" in url else None)
        if "domainis" in url:
            return gdelt_articles(["Apple names new chief financial officer as CFO steps down"], NOW + dt.timedelta(hours=1))
        return gdelt_articles(TITLES if "semiconductor" in url else ["Something else entirely"], NOW - dt.timedelta(hours=6))
    if "company_tickers" in url:
        return json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})
    if "data.sec.gov/submissions" in url:
        return json.dumps({"filings": {"recent": {
            "form": ["8-K", "8-K", "10-Q"], "filingDate": [ACCEPTED[:10], "2026-08-01", "2026-08-01"],
            "acceptanceDateTime": [ACCEPTED, "2026-08-01T20:30:00.000Z", "2026-08-01T20:31:00.000Z"],
            "accessionNumber": ["0000320193-26-000099", "0000320193-26-000050", "0000320193-26-000051"],
            "primaryDocument": ["aapl-8k.htm", "aapl-8k2.htm", "aapl-10q.htm"], "items": ["5.02,9.01", "2.02,9.01", ""]}}})
    if "query1.finance.yahoo.com" in url:
        start = dt.datetime(2026, 6, 1, 20, tzinfo=UTC)
        ts = [int((start + dt.timedelta(days=i)).timestamp()) for i in range(180)]
        closes = [200 + 5 * math.sin(i / 3) for i in range(180)]
        return json.dumps({"chart": {"result": [{"meta": {"gmtoffset": -18000}, "timestamp": ts,
                                                  "indicators": {"quote": [{"close": closes}]}}]}})
    if "federalregister.gov/api/v1/documents.json" in url:
        return json.dumps({"results": [{"document_number": "2026-23456", "title": "Adjusting Imports of Semiconductors",
                                        "type": "Presidential Document", "abstract": "Tariff on semiconductor imports.",
                                        "html_url": "https://www.federalregister.gov/d/2026-23456",
                                        "publication_date": NOW.date().isoformat(), "agencies": [{"name": "Executive Office of the President"}],
                                        "effective_on": "2027-06-15", "comments_close_on": None, "action": "Proclamation"}]})
    if "significant_week" in url:
        t = int((NOW - dt.timedelta(hours=5)).timestamp() * 1000)
        return json.dumps({"features": [{"id": "us7000abcd", "properties": {"mag": 7.2, "place": "45 km E of Hualien City, Taiwan",
                                                                            "time": t, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
                                                                            "alert": "yellow", "tsunami": 1},
                                         "geometry": {"coordinates": [121.9, 23.9, 20.0]}}]})
    if "fdsnws/event" in url:
        return json.dumps({"features": []})
    if "data.gov.sg" in url:
        return json.dumps({"code": 0, "data": {"items": [{"updatedTimestamp": NOW.isoformat(),
                                                          "readings": {"psi_twenty_four_hourly": {"national": 128}}}]}})
    raise OSError("unexpected url " + url)


def sandbox():
    tmp = Path(tempfile.mkdtemp())
    site = tmp / "site"
    (site / "data/world").mkdir(parents=True)
    P.SITE, P.DATA, P.LEDGER, P.PAGES = site, site / "data/world", site / "data/world/ledger", site / "world"
    S.CACHE = tmp / "cache"
    M.STOCKS = tmp / "cache/stocks"
    S.get = fake_get
    S.GDELT_GAP = 0
    FE.time.sleep = lambda s: None
    return tmp


def test_parsers():
    arts = S.parse_gdelt_articles(gdelt_articles(TITLES, NOW))
    assert len(arts) == 6 and arts[0]["seen"].endswith("Z")
    assert S.parse_gdelt_articles("Your search contained a phrase that was too short") == []
    tl = S.parse_gdelt_timeline(gdelt_timeline(DAYS[:3]))
    assert len(tl) == 3 and all(v > 0 for v in tl.values())
    fr = S.parse_fr(fake_get(S.fr_url("tariff"), "fr"))
    assert fr[0]["number"] == "2026-23456" and fr[0]["effective_on"] == "2027-06-15"
    q = S.parse_usgs(fake_get(S.USGS_SIGNIFICANT, "usgs"))
    assert q[0]["mag"] == 7.2 and q[0]["lat"] == 23.9
    assert S.parse_psi(fake_get(S.PSI_URL, "x"))[0][1] == 128
    assert S.parse_sec_filings(fake_get("https://data.sec.gov/submissions/CIK0000320193.json", "sec"))[0]["items"] == "5.02,9.01"


def test_nlp():
    cats = dict(N.classify("TSMC warns export controls could hit advanced chips"))
    assert "semiconductors" in cats and "export" in cats["semiconductors"]
    e = N.entities("Nvidia and TSMC shares fall as China curbs widen")
    assert "NVDA" in e["companies"] and "TSM" in e["companies"] and "CN" in e["countries"]
    groups = N.cluster(S.parse_gdelt_articles(gdelt_articles(TITLES, NOW)))
    assert groups[0]["outlets"] == 3, groups[0]
    days = {d: 100 for d in DAYS}
    days[YESTERDAY] = 400
    days[DAYS[-10]] = 101
    s = N.spike(days, YESTERDAY)
    assert s["spike"] and s["ratio"] > 3
    assert N.spike({d: 100 for d in DAYS[:10]}, DAYS[9]) is None       # too little history


def test_ledger_is_frozen():
    tmp = Path(tempfile.mkdtemp())
    led = L.Ledger(tmp, tmp / "corr.json")
    sig = {"id": "W1", "kind": "market", "category": "equities", "title": "t", "published_at": "2026-11-27T00:00:00Z",
           "facts": [{"text": "x", "class": "fact"}], "sources": [{"url": "https://a.example"}]}
    claim = {"id": "W1-C1", "kind": "forecast", "statement": "s", "rule": {"type": "close_above_after"}, "due": "2026-12-05",
             "probability": 0.6, "base": {"n": 30, "hits": 18}}
    assert led.add_signal(sig, [claim]) and not led.add_signal(sig, [claim])
    led.save()
    stored = json.loads((tmp / "claims.json").read_text())
    stored["claims"][0]["statement"] = "edited after the fact"
    (tmp / "claims.json").write_text(json.dumps(stored))
    try:
        L.Ledger(tmp, tmp / "corr.json")
        raise AssertionError("an edited claim must be refused")
    except L.FrozenError:
        pass
    led2 = L.Ledger(Path(tempfile.mkdtemp()), tmp / "corr.json")
    bad = dict(claim, probability=0.7, base={"n": 5, "hits": 3})
    try:
        led2.add_signal(dict(sig, id="W2"), [dict(bad, id="W2-C1")])
        raise AssertionError("a probability without 20 cases must be refused")
    except ValueError:
        pass
    led2.add_signal(dict(sig, id="W3"), [dict(claim, id="W3-C1")])
    now = dt.datetime(2026, 12, 6, tzinfo=UTC)
    assert led2.assess("W3-C1", "hit", {}, "it happened", now)
    assert not led2.assess("W3-C1", "miss", {}, "changed my mind", now)        # hits and misses are final
    assert led2.current("W3-C1") == "hit"


def test_graders():
    closes = {f"2026-01-{d:02d}": 100.0 + d for d in range(1, 29)}
    ctx = {"market": lambda m: closes, "series": lambda s: closes}
    now = dt.datetime(2026, 2, 1, tzinfo=UTC)
    rule = {"type": "close_above_after", "source": "market", "id": "nq", "day": "2026-01-10", "level": 110.0, "sessions": 5}
    assert R.close_above_after(rule, ctx, now)[0] == "hit"
    rule["day"] = "2026-01-27"
    assert R.close_above_after(rule, ctx, now) is None                # not enough sessions yet
    cov = {d: 100 for d in DAYS}
    for d in DAYS[-7:]:
        cov[d] = 150
    r = R.coverage_persists({"category": "x", "day": DAYS[-8], "baseline": 100, "ratio": 1.3, "days": 7}, {"coverage": lambda c: cov}, now)
    assert r[0] == "hit"
    fr = {"2026-1": {"effective_on": "2026-01-15"}, "2026-2": {"effective_on": "2026-03-01"}}
    g = lambda n, v: R.fr_date_unchanged({"number": n, "field": "effective_on", "value": v}, {"fr_doc": fr.get}, now)
    assert g("2026-1", "2026-01-15")[0] == "hit" and g("2026-2", "2026-01-20")[0] == "miss"
    psi = [("2026-01-02T08:00:00+08:00", 140.0), ("2026-01-03T08:00:00+08:00", 90.0)]
    rule = {"threshold": 100, "start": "2026-01-01T20:00:00Z", "end": "2026-01-04T20:00:00Z"}
    assert R.psi_below(rule, {"psi": lambda: psi}, now)[0] == "hit"


def test_full_run():
    tmp = sandbox()
    try:
        import world
        added, graded = world.run(NOW, network=True)
        led = L.Ledger(P.LEDGER)
        kinds = {s["kind"] for s in led.signals.values()}
        assert {"attention", "rule", "quake", "haze"} <= kinds, kinds
        att = next(s for s in led.signals.values() if s["kind"] == "attention")
        assert att["category"] == "semiconductors" and "3 outlets" in " ".join(f["text"] for f in att["facts"])
        rule = next(s for s in led.signals.values() if s["kind"] == "rule")
        assert led.claims[rule["claims"][0]]["rule"]["value"] == "2027-06-15" and rule["horizon"] == "long"
        quake = next(s for s in led.signals.values() if s["kind"] == "quake")
        assert "nq" in quake["markets"] and led.claims[quake["claims"][0]]["rule"]["type"] == "aftershock"
        filing = next(s for s in led.signals.values() if s["kind"] == "filing")
        assert "AAPL" in filing["title"] and "directors or officers" in filing["title"]
        assert sum(s["kind"] == "filing" for s in led.signals.values()) == 1          # the August filings are too old
        for name in ("index.html", "early.html", "trust.html", "radar.html", "business.html", "feed.xml"):
            assert (P.PAGES / name).exists(), name
        assert (P.DATA / "early" / "2026-11-27.json").exists()
        page = (P.PAGES / "s" / (att["id"] + ".html")).read_text()
        assert "Claims Displace will grade" in page and "<script>" not in page.split("</main>")[0]
        trust = json.loads((P.DATA / "trust.json").read_text())
        assert trust["scorecard"]["signals"] == len(led.signals) and not P.check(P.DATA)
        # a second run an hour later: no duplicates, Early is not rewritten
        before = (P.DATA / "early" / "2026-11-27.json").read_text()
        world.run(NOW + dt.timedelta(hours=1), network=True)
        led2 = L.Ledger(P.LEDGER)
        assert len(led2.signals) >= len(led.signals)
        assert (P.DATA / "early" / "2026-11-27.json").read_text() == before
        # aftershock grading: an M5.4 inside the window grades the claim as a hit
        cache = S.cache_load("aftershocks.json", {})
        cache["us7000abcd"] = {"checked": "x", "complete": False, "events": [{"id": "after1", "mag": 5.4, "time": L.iso(NOW)}]}
        S.cache_save("aftershocks.json", cache)
        world.run(NOW + dt.timedelta(hours=2), network=False)
        led3 = L.Ledger(P.LEDGER)
        assert led3.current(quake["claims"][0]) == "hit"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_connections():
    a = {"id": "a", "kind": "rule", "category": "policy", "markets": [], "entities": {"companies": [], "countries": ["US"]}, "rank": 60, "title": "A", "published_at": "x"}
    b = {"id": "b", "kind": "attention", "category": "semiconductors", "markets": ["nq"], "entities": {"companies": ["NVDA"], "countries": ["US"]}, "rank": 70, "title": "B", "published_at": "x"}
    c = {"id": "c", "kind": "market", "category": "equities", "markets": ["nq"], "entities": {"companies": [], "countries": []}, "rank": 60, "title": "C", "published_at": "x"}
    conn = P.connections([a, b, c], "2026-11-27")
    assert conn["routes"] and all(l["type"] in ("documented", "topic", "co-mentioned") for r in conn["routes"] for l in r["links"])
    d = dict(b, id="d", category="ai", kind="filing")
    assert P.link(b, d, P.relations())["type"] == "documented"          # both name NVDA
    assert P.link(a, c, P.relations()) in (None,) or P.link(a, c, P.relations())["type"] != "documented"


def test_market_history():
    closes = M.load_market("gold")
    if len(closes) < 1000:
        print("skip: no gold cache")
        return
    up, wide = M.after_big_move(closes, "pct", -1, before="2026-03-18")
    assert up["n"] >= 20 and 0 < up["hits"] < up["n"]
    tp = M.trend_persistence(closes, 126, before="2026-03-18")
    assert tp["above"]["n"] + tp["below"]["n"] > 100


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("world tests passed")
