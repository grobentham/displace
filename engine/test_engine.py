"""Self-test: runs the engine on a copy of the repo against simulated FRED responses. No network needed."""
import datetime as dt
import importlib
import json
import math
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def monthly(start, n, f, rt_fn):
    y, m = start
    out = []
    for i in range(n):
        d = dt.date(y, m, 1)
        out.append((d.isoformat(), f(i), rt_fn(d)))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def published_mid_next_month(d):
    nm = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nm + dt.timedelta(days=12)).isoformat()


def daily(start, n, base, amp):
    d = dt.date.fromisoformat(start)
    out, i = [], 0
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d.isoformat(), round(base + amp * math.sin(i / 7.0) + 0.0002 * i, 3), d.isoformat()))
            i += 1
        d += dt.timedelta(days=1)
    return out


def fake_world(upto):
    """Observations visible as of `upto` (by realtime_start)."""
    retail = monthly((2014, 1), 153, lambda i: 400 + i * 2 + (3 if i % 5 == 0 else 0), published_mid_next_month)
    retail.append(("2026-10-01", retail[-1][1] * 1.002, "2026-11-17"))  # Oct value published on release day
    cpi = monthly((2014, 1), 154, lambda i: 240 * (1.0025 ** i), published_mid_next_month)
    payems = monthly((2014, 1), 154, lambda i: 140000 + i * 150, published_mid_next_month)
    icsa = []
    d = dt.date(2025, 1, 4)
    while d <= dt.date(2026, 11, 14):
        icsa.append((d.isoformat(), 200000 + (d.toordinal() % 9) * 1000, (d + dt.timedelta(days=5)).isoformat()))
        d += dt.timedelta(days=7)
    world = {
        "RSAFS": retail, "CPILFESL": cpi, "CPIAUCSL": cpi, "PAYEMS": payems, "ICSA": icsa, "IC4WSA": icsa,
        "DFEDTARU": [("2025-01-01", 3.75, "2025-01-01"), ("2026-09-17", 4.0, "2026-09-17")],
        "DFEDTARL": [("2025-01-01", 3.5, "2025-01-01"), ("2026-09-17", 3.75, "2026-09-17")],
        "DGS2": daily("2022-11-01", 1050, 4.2, 0.2), "DGS10": daily("2022-11-01", 1050, 4.6, 0.15),
        "DTWEXBGS": daily("2022-11-01", 1050, 120, 1.5), "DCOILWTICO": daily("2025-10-01", 200, 70, 3),
        "T10Y2Y": daily("2025-10-01", 200, 0.4, 0.1), "DFF": daily("2025-10-01", 200, 3.88, 0.01),
    }
    return {k: [o for o in v if o[2] <= upto] for k, v in world.items()}


def _monthly_dates(day, start=(2024, 11), end=(2026, 9)):
    y, m, out = start[0], start[1], []
    while (y, m) <= end:
        d = dt.date(y, m, day)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append(d.isoformat())
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


REL_DATES = {
    10: _monthly_dates(12) + ["2026-10-14", "2026-11-10", "2026-12-10", "2027-01-13", "2027-02-11"],
    9: ["2026-10-15", "2026-11-17", "2026-12-16", "2027-01-15", "2027-02-17"],
    50: ["2026-10-02", "2026-11-06", "2026-12-04", "2027-01-08", "2027-02-05"],
    101: ["2026-10-28", "2026-12-09", "2027-01-27", "2027-03-17"],
    180: [(dt.date(2026, 10, 1) + dt.timedelta(weeks=i)).isoformat() for i in range(22)],
    53: ["2026-10-29", "2026-11-25", "2026-12-23", "2027-01-28"],
}


def run(tmp, now, upto):
    os.environ["ENGINE_NOW"] = now
    os.environ["FRED_API_KEY"] = "test"
    sys.path.insert(0, os.path.join(tmp, "engine"))
    for m in ("engine", "fredapi", "catalog", "calendar_rules", "direction", "prices", "quality"):
        sys.modules.pop(m, None)
    fredapi = importlib.import_module("fredapi")
    world = fake_world(upto)
    fredapi.probe = lambda *a, **k: True
    fredapi.observations = lambda s, start, initial=False: [o for o in world.get(s, []) if o[0] >= start] or None
    fredapi.releases = lambda: {"Consumer Price Index": 10, "Advance Monthly Sales for Retail and Food Services": 9,
                                "Employment Situation": 50, "FOMC Press Release": 101,
                                "Unemployment Insurance Weekly Claims": 180, "Gross Domestic Product": 53}
    fredapi.release_dates = lambda rid, s, e="9999-12-31": [x for x in REL_DATES.get(rid, []) if s <= x <= e] if rid in REL_DATES else None
    earnings = importlib.import_module("earnings")
    earnings.run = lambda *args: None
    consensus = importlib.import_module("consensus")
    consensus.apply = lambda *args, **kw: 0  # keep the live ForexFactory feed out of the fake world
    consensus.apply_tv = lambda *args, **kw: 0
    importlib.import_module("tv").sync = lambda *args, **kw: 0
    importlib.import_module("agencies").fomc_meetings = lambda: []  # the fake world's FOMC dates come from FRED
    consensus.backfill_history = lambda *args, **kw: 0
    eng = importlib.import_module("engine")
    eng.main()
    sys.path.pop(0)
    return lambda p: json.load(open(os.path.join(tmp, "site", "data", p), encoding="utf-8"))


def find(ev, date, word):
    return next((e for e in ev if e["date"] == date and word.lower() in e["title"].lower()), None)


def main():
    tmp = fresh_copy()
    # Sunday before: calendar builds itself, no actual yet
    d = run(tmp, "2026-11-15T10:00:00-05:00", "2026-11-15")
    ev = d("calendar/events.json")["events"]
    assert find(ev, "2027-02-11", "CPI"), "CPI date from FRED calendar"
    assert find(ev, "2027-03-17", "FOMC"), "FOMC date from FRED calendar"
    assert find(ev, "2027-04-07", "minutes"), "minutes three weeks after the decision"
    assert find(ev, "2026-12-01", "ISM Manufacturing"), "ISM by rule"
    assert find(ev, "2027-01-18", "closed"), "MLK day by rule"
    assert len([e for e in ev if e["date"] == "2026-11-17" and "retail" in e["title"].lower()]) == 1, "no duplicate retail event"
    r = find(ev, "2026-11-17", "Retail")
    assert not r.get("actual")
    assert d("brief/today.json")["date"] == "2026-11-16"
    assert d("fed/current.json")["rate"] == "3.75%–4.00%"
    assert "y10" in d("markets/latest.json")["tiles"]
    rx = d("history/reactions.json")
    assert "cpi" in rx["series"] and rx["baseline"].get("y2"), rx.keys()
    st = d("engine/status.json")
    assert st["fred"] and st["calendarThrough"] >= "2027-02-11", st
    # After retail sales: actual, components, recap, history
    d = run(tmp, "2026-11-17T09:05:00-05:00", "2026-11-17")
    r = find(d("calendar/events.json")["events"], "2026-11-17", "Retail")
    assert r["actual"] == "0.2%", r
    assert any(c["label"] == "Retail sales y/y" for c in r["components"]), r["components"]
    assert "recap" in r and "Retail sales came in at 0.2%" in r["recap"], r["recap"]
    assert d("history/main.json")["series"]["retail"]["rows"][-1]["period"] == "Oct 2026"
    assert d("brief/today.json")["recent"], "just-released list"
    ics = open(os.path.join(tmp, "site", "calendar.ics"), encoding="utf-8", newline="").read()
    assert ics.startswith("BEGIN:VCALENDAR") and "TZID=America/New_York" in ics and all(len(l.encode()) <= 75 for l in ics.split("\r\n"))
    shutil.rmtree(tmp)
    quality_tests()
    edge_tests()
    print("engine self-test passed")


def fresh_copy():
    tmp = tempfile.mkdtemp()
    shutil.copytree(os.path.join(ROOT, "engine"), os.path.join(tmp, "engine"),
                    ignore=shutil.ignore_patterns("__pycache__", "STALE", "pending.json"))
    # Give the mocked release calendars a fixed seed instead of live data or overrides.
    with open(os.path.join(tmp, "engine", "schedule.json"), "w", encoding="utf-8") as f:
        json.dump({"events": []}, f)
    calendar = os.path.join(tmp, "site", "data", "calendar")
    os.makedirs(calendar)
    with open(os.path.join(calendar, "events.json"), "w", encoding="utf-8") as f:
        json.dump({"events": [{"id": "20261117-retail-sales-oct", "date": "2026-11-17",
                              "time": "08:30", "title": "Retail sales (Oct)", "cur": "USD",
                              "impact": "high", "src": "Census"}]}, f)
    return tmp


def quality_tests():
    sys.path.insert(0, os.path.join(ROOT, "engine"))
    import quality as qa
    rep = qa.Report()
    # 1. implausible figure is rejected
    assert qa.gate_figure(rep, "x", "Core CPI m/m", "CPILFESL", "pct", "25.0%", [0.2, 0.3] * 20, {}, "r1") == "reject"
    # 2. extreme-but-possible figure is held, then published when a later run sees it again
    pend = {}
    hist = [150, 160, 140, 155, 170, 145, 150, 165, 158, 149, 152, 161] * 3
    assert qa.gate_figure(rep, "n", "Payrolls", "PAYEMS", "diff", "-900K", hist, pend, "r1") == "hold"
    assert qa.gate_figure(rep, "n", "Payrolls", "PAYEMS", "diff", "-900K", hist, pend, "r1") == "hold", "same run can't confirm"
    assert qa.gate_figure(rep, "n", "Payrolls", "PAYEMS", "diff", "-900K", hist, pend, "r2") == "publish"
    # 3. normal figure publishes straight away
    assert qa.gate_figure(rep, "c", "Core CPI m/m", "CPILFESL", "pct", "0.3%", [0.2, 0.3, 0.25] * 10, {}, "r1") == "publish"
    # 4. text with trade calls or template errors is dropped
    assert qa.clean_text(rep, "t", "Gold will rise after the report, so buy the dip.") is None
    assert qa.clean_text(rep, "t", "Payrolls came in at None.") is None
    assert qa.clean_text(rep, "t", "Retail sales came in at 0.2% against a 0.2% forecast.") is not None
    assert qa.clean_text(rep, "t", "Selling pressure eased as sales rose 0.4%.") is not None, "no false positive on 'selling'/'sales'"
    # 5. a bad FRED pull for a real release gets rejected inside the engine, not published
    tmp = fresh_copy()
    global fake_world
    real = fake_world

    def broken(upto):
        w = real(upto)
        w["RSAFS"] = w["RSAFS"][:-1] + [("2026-10-01", w["RSAFS"][-2][1] * 1.30, "2026-11-17")]  # +30% month: impossible
        return w
    fake_world = broken
    d = run(tmp, "2026-11-17T09:05:00-05:00", "2026-11-17")
    fake_world = real
    r = find(d("calendar/events.json")["events"], "2026-11-17", "Retail")
    assert not r.get("actual"), "implausible retail sales must not publish"
    q = d("engine/quality.json")
    assert q["rejected"] and q["critical"] >= 1, q
    assert os.path.exists(os.path.join(tmp, "engine", "QUALITY_FAIL"))
    shutil.rmtree(tmp)


def edge_tests():
    # FRED completely down: nothing crashes, calendar kept, warning raised
    tmp = fresh_copy()
    os.environ["ENGINE_NOW"] = "2026-11-17T09:05:00-05:00"
    os.environ["FRED_API_KEY"] = "test"
    sys.path.insert(0, os.path.join(tmp, "engine"))
    for m in ("engine", "fredapi", "catalog", "calendar_rules", "quality"):
        sys.modules.pop(m, None)
    fredapi = importlib.import_module("fredapi")
    fredapi.observations = lambda *a, **k: None
    fredapi.releases = lambda: None
    fredapi.release_dates = lambda *a, **k: None
    before = json.load(open(os.path.join(tmp, "site", "data", "calendar", "events.json")))["events"]
    earnings = importlib.import_module("earnings")
    earnings.run = lambda *args: None
    consensus = importlib.import_module("consensus")
    consensus.apply = lambda *args, **kw: 0  # keep the live ForexFactory feed out of the fake world
    consensus.apply_tv = lambda *args, **kw: 0
    importlib.import_module("tv").sync = lambda *args, **kw: 0
    importlib.import_module("agencies").fomc_meetings = lambda: []  # the fake world's FOMC dates come from FRED
    consensus.backfill_history = lambda *args, **kw: 0
    eng = importlib.import_module("engine")
    eng.main()
    sys.path.pop(0)
    after = json.load(open(os.path.join(tmp, "site", "data", "calendar", "events.json")))["events"]
    assert {e["id"] for e in before if e["date"] >= "2026-11-17"} <= {e["id"] for e in after}, "FRED outage must not drop dates"
    # period labels across the year boundary and GDP estimates
    assert eng.period_for("cpi", dt.date(2027, 1, 13))[0] == "Dec"
    assert eng.period_for("cpi", dt.date(2027, 1, 13))[1] == dt.date(2026, 12, 1)
    assert eng.period_for("gdp", dt.date(2027, 1, 28))[0::2] == ("Q4", "advance")
    assert eng.period_for("gdp", dt.date(2026, 11, 25))[0::2] == ("Q3", "second")
    assert eng.period_for("jolts", dt.date(2027, 1, 5))[0] == "Nov"
    # calendar feed keeps New York local time across the March DST switch
    ics = eng.ics([{"id": "x", "date": "2027-03-16", "time": "08:30", "title": "Retail sales (Feb)", "impact": "high", "note": ""}])
    assert "DTSTART;TZID=America/New_York:20270316T083000" in ics
    # NYSE rules: Thanksgiving claims moved to Wednesday handled by holiday set
    import calendar_rules as cr
    assert dt.date(2026, 11, 26) in cr.nyse_holidays(2026) and dt.date(2027, 3, 26) in cr.nyse_holidays(2027)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
