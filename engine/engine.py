"""Displace news engine.

Runs on a schedule in GitHub Actions. No AI: everything comes from official data
(FRED, the St. Louis Fed's free data service) and fixed templates. Nothing it writes
is a trade signal, recommendation or prediction.

Each run:
  1. Builds the calendar by itself: release dates from FRED's official release calendars,
     NYSE holidays and early closes by rule, and rule-based dates for ISM, the Conference Board,
     FOMC minutes and the Beige Book. engine/schedule.json adds anything else (ECB, BoE, fixes).
  2. Fills previous figures before each release and actual figures after it, with full detail
     (e.g. CPI headline, core and year-on-year), only accepting numbers FRED published on or after release day.
  3. Analyses each new number: records, streaks and where it sits against five years of history.
  4. Measures how 2-year yields, 10-year yields and the dollar moved on past release days compared with normal days.
  5. Writes the daily brief, weekly outlook, Fed tracker, macro pulse, release stats, iCal feeds and an engine status file.

Public FRED data and ALFRED snapshots work without an API key.
"""
import datetime as dt
import json
import os
import re
import statistics
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calendar_rules as rules  # noqa: E402
import fredapi  # noqa: E402
import publicdata  # noqa: E402
import quality as qa  # noqa: E402
from catalog import (HISTORY_KEYS, MARKETS, NAMES, NOTES, REACTION_KEYS, REACTION_SERIES,  # noqa: E402
                     RELEASES, RULED, WHY)

NY = ZoneInfo("America/New_York")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "data")
ENG = os.path.join(ROOT, "engine")
NOW = dt.datetime.fromisoformat(os.environ["ENGINE_NOW"]).astimezone(NY) if os.environ.get("ENGINE_NOW") else dt.datetime.now(NY)
TODAY = NOW.date()
HIST_START = "2014-01-01"  # one long fetch per series, reused for figures and analysis
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LOG, WARN = [], []
QA = qa.Report()
SOURCE = fredapi if fredapi.KEY else publicdata
PENDING_PATH = None  # set in main
HORIZON = 150  # days of calendar ahead


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg)


def warn(msg):
    WARN.append(msg)
    print("WARNING:", msg)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save(path, obj, raw=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = raw if raw is not None else json.dumps(obj, indent=1, ensure_ascii=False) + "\n"
    try:
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == new:
                return False
    except FileNotFoundError:
        pass
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return True


def d_(s):
    return dt.date.fromisoformat(s)


def fmt_day(d):
    return f"{d.strftime('%a')} {MON[d.month - 1]} {d.day}"


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:40]


# ---------------------------------------------------------------- what kind of release is this?
KIND_PATTERNS = [
    ("holiday", None),
    ("minutes", r"minutes"),
    ("beige", r"beige"),
    ("fomc", r"FOMC rate|^FOMC(?!.*minutes)"),
    ("adp", r"\bADP\b"),
    ("jolts", r"JOLTS|job openings"),
    ("claims", r"claims"),
    ("nfp", r"payroll|employment situation"),
    ("cpi", r"\bCPI\b|consumer price"),
    ("ppi", r"\bPPI\b|producer price"),
    ("retail", r"retail"),
    ("gdp", r"\bGDP\b"),
    ("pce", r"\bPCE\b|personal income"),
    ("ism-m", r"ISM manuf"),
    ("ism-s", r"ISM serv"),
    ("umich", r"UMich|Michigan|sentiment"),
    ("durables", r"durable"),
    ("homes", r"new home|home sales"),
    ("conf", r"confidence"),
    ("ecb", r"\bECB\b|European Central"),
    ("boe", r"\bBoE\b|Bank of England"),
]


def kind_of(e):
    if e.get("impact") == "holiday":
        return "holiday"
    t = e.get("title", "")
    for k, pat in KIND_PATTERNS[1:]:
        if re.search(pat, t, re.I):
            return k
    return None


def when(e):
    t = e.get("time") or "00:00"
    h, m = map(int, t.split(":"))
    return dt.datetime.combine(d_(e["date"]), dt.time(h, m), NY)


# ---------------------------------------------------------------- building the calendar
def period_for(key, rel):
    """Label and observation date for the period a release reports, from its release date."""
    cfg = RELEASES.get(key) or {}
    lag = cfg.get("lag")
    if lag == "quarter":
        after = (rel.month - 1) % 3 + 1  # 1 = advance, 2 = second, 3 = third
        qend_month = rel.month - after
        y = rel.year if qend_month > 0 else rel.year - 1
        qend_month = qend_month if qend_month > 0 else qend_month + 12
        q = qend_month // 3
        return f"Q{q}", dt.date(y, (q - 1) * 3 + 1, 1), ["advance", "second", "third"][after - 1]
    if isinstance(lag, int):
        m, y = rel.month - lag, rel.year
        while m <= 0:
            m += 12
            y -= 1
        return MON[m - 1], dt.date(y, m, 1), None
    return None, None, None


def make_event(date, key, cfg, title, note=None, auto="fred"):
    return {"id": date.strftime("%Y%m%d") + "-" + slug(title), "date": date.isoformat(), "time": cfg["time"],
            "title": title, "cur": "USD", "impact": cfg["impact"], "src": cfg["src"],
            "note": note or NOTES.get(cfg["time"], ""), "auto": auto}


def auto_events():
    """Events from FRED's release calendars and from rules. Returns (events, kinds FRED answered for)."""
    out, answered = [], set()
    start = (TODAY - dt.timedelta(days=14)).isoformat()
    end = (TODAY + dt.timedelta(days=HORIZON)).isoformat()
    names = (fredapi.releases() or {}) if fredapi.KEY else {}
    fomc_dates = []
    bea = [] if fredapi.KEY else publicdata.bea_releases(NY)
    for key, cfg in RELEASES.items():
        agency = [(published, period, est) for kind, published, period, est in bea
                  if kind == key and start <= published.date().isoformat() <= end]
        if agency:
            answered.add(key)
            for published, period, est in agency:
                title = cfg["title"].format(per=period, est=est)
                out.append(make_event(published.date(), key, {**cfg, "time": published.strftime("%H:%M")}, title, auto="public"))
            continue
        rid = next((i for n, i in names.items() if re.search(cfg["fred"], n)), None) or cfg["rid"]
        dates = SOURCE.release_dates(rid, start, end)
        if dates is None:
            continue
        answered.add(key)
        for s in dates:
            d = d_(s)
            if d.weekday() >= 5:
                continue
            if key == "claims":
                title = cfg["title"] + (" (moved for the holiday)" if d.weekday() != 3 else "")
            elif key == "fomc":
                title = cfg["title"] + (" + projections (dot plot)" if d.month in (3, 6, 9, 12) else "")
                fomc_dates.append(d)
            elif key == "umich":
                lab, _, _ = period_for(key, d)
                title = cfg["title"].format(stage="preliminary" if d.day <= 15 else "final", per=lab)
            elif key == "gdp":
                lab, _, est = period_for(key, d)
                title = cfg["title"].format(est=est, per=lab)
            else:
                lab, _, _ = period_for(key, d)
                title = cfg["title"].format(per=lab)
            out.append(make_event(d, key, cfg, title, auto="fred" if fredapi.KEY else "public"))
    # rules
    hol_dates = set()
    for y in {TODAY.year, TODAY.year + 1}:
        hol_dates |= set(rules.nyse_holidays(y))
    m0 = dt.date(TODAY.year, TODAY.month, 1)
    for i in range(0, 5):
        y, m = m0.year + (m0.month - 1 + i) // 12, (m0.month - 1 + i) % 12 + 1
        im, iserv = rules.ism_dates(y, m, hol_dates)
        prev = MON[(m - 2) % 12]
        for d, k in ((im, "ism-m"), (iserv, "ism-s")):
            out.append(make_event(d, k, RULED[k], RULED[k]["title"].format(per=prev), RULED[k]["note"], auto="rule"))
        cb = rules.conference_board_date(y, m)
        out.append(make_event(cb, "conf", RULED["conf"], RULED["conf"]["title"].format(per=MON[m - 1]), RULED["conf"]["note"], auto="rule"))
    for d in fomc_dates:
        start_day = d - dt.timedelta(days=1)
        lab = f"{MON[start_day.month - 1]} {start_day.day}–{d.day}" if start_day.month == d.month else f"{MON[start_day.month - 1]} {start_day.day}–{MON[d.month - 1]} {d.day}"
        out.append(make_event(d + dt.timedelta(days=21), "minutes", RULED["minutes"], RULED["minutes"]["title"].format(per=lab), RULED["minutes"]["note"], auto="rule"))
        out.append(make_event(d - dt.timedelta(days=14), "beige", RULED["beige"], RULED["beige"]["title"], RULED["beige"]["note"], auto="rule"))
    if fomc_dates:
        answered |= {"minutes", "beige"}
    answered |= {"ism-m", "ism-s", "conf", "holiday"}
    for y in {TODAY.year, TODAY.year + 1}:
        for d, n in rules.nyse_holidays(y).items():
            out.append({"id": d.strftime("%Y%m%d") + "-" + slug(n), "date": d.isoformat(), "time": "", "title": f"{n}: US markets closed",
                        "cur": "USD", "impact": "holiday", "src": "NYSE / CME", "note": "US stock markets closed. Futures may trade shortened hours.", "auto": "rule"})
        for d, n in rules.nyse_early_closes(y).items():
            out.append({"id": d.strftime("%Y%m%d") + "-" + slug(n), "date": d.isoformat(), "time": "", "title": f"{n}: early close (13:00)",
                        "cur": "USD", "impact": "holiday", "src": "NYSE / CME", "note": "US stocks close at 13:00 New York. Thin volume.", "auto": "rule"})
    lo, hi = TODAY - dt.timedelta(days=14), TODAY + dt.timedelta(days=HORIZON)
    return [e for e in out if lo <= d_(e["date"]) <= hi], answered


def holiday_kind(e):
    return "closed" if "closed" in e["title"].lower() else "early"


def merge(events, autos, answered):
    """Add auto events that aren't there yet; drop future auto events that their source no longer lists."""
    key = lambda e: (kind_of(e), e["date"], holiday_kind(e) if kind_of(e) == "holiday" else "")
    have = {key(e): e for e in events}
    auto_keys = {key(a) for a in autos}
    public_through = {}
    added = 0
    for a in autos:
        k = key(a)
        if a.get("auto") == "public":
            public_through[k[0]] = max(public_through.get(k[0], ""), a["date"])
        if k in have:
            continue
        # weekly claims: skip if a claims event already sits within two days (e.g. a holiday shift)
        if a and kind_of(a) == "claims" and any(kind_of(e) == "claims" and abs((d_(e["date"]) - d_(a["date"])).days) <= 2 for e in events):
            continue
        events.append(a)
        have[k] = a
        added += 1
    removed = 0
    for e in list(events):
        if not fredapi.KEY and e.get("auto") in ("public", "fred") and e["date"] > public_through.get(kind_of(e), ""):
            continue
        if e.get("auto") and not e.get("actual") and d_(e["date"]) > TODAY and kind_of(e) in answered and key(e) not in auto_keys:
            events.remove(e)
            removed += 1
    if added or removed:
        log(f"calendar: {added} added, {removed} removed")


def merge_schedule(events):
    sched = load(os.path.join(ENG, "schedule.json"), {"events": []}).get("events", [])
    have = {e["id"]: e for e in events}
    for s in sched:
        if not s.get("date") or not s.get("title"):
            continue
        s.setdefault("id", s["date"].replace("-", "") + "-" + slug(s["title"]))
        if s["id"] in have:
            for f in ("date", "time", "title", "cur", "impact", "src", "note"):
                if f in s:
                    have[s["id"]][f] = s[f]
        else:
            ev = {k: v for k, v in s.items() if not k.startswith("_")}
            events.append(ev)
            have[ev["id"]] = ev


def prune(events):
    out, seen = [], set()
    for e in sorted(events, key=lambda e: (e["date"], e.get("time") or "", 0 if e.get("actual") else 1)):
        age = (TODAY - d_(e["date"])).days
        if age > 120 or (age > 14 and not e.get("actual")):
            continue
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out


# ---------------------------------------------------------------- figures
def fmt(mode, v):
    if v is None:
        return None
    if mode in ("pct", "yoy"):
        v = round(v, 1)
        return f"{0.0 if v == 0 else v:.1f}%"
    if mode in ("diff", "thousands"):
        return f"{round(v)}K"
    if mode in ("claims", "diffPersons"):
        return f"{round(v / 1000)}K"
    if mode == "claimsM":
        return f"{v / 1e6:.2f}M"
    if mode == "millions":
        return f"{v / 1000:.2f}M"
    if mode == "rate":
        return f"{v:.2f}%"
    if mode == "pctlevel":
        return f"{v:.1f}%"
    if mode == "level1":
        return f"{v:.1f}"
    return str(v)


def transformed(obs, mode):
    """[(date, value, realtime_start)] after applying the transform."""
    out = []
    idx = {o[0]: i for i, o in enumerate(obs)}
    for i, (d, v, rt) in enumerate(obs):
        if mode == "pct":
            if i == 0:
                continue
            out.append((d, (v / obs[i - 1][1] - 1) * 100, rt))
        elif mode in ("diff", "diffPersons"):
            if i == 0:
                continue
            out.append((d, v - obs[i - 1][1], rt))
        elif mode == "yoy":
            dd = d_(d)
            j = idx.get(dd.replace(year=dd.year - 1).isoformat())
            if j is None:
                continue
            out.append((d, (v / obs[j][1] - 1) * 100, rt))
        else:
            out.append((d, v, rt))
    return out


def series_obs(series):
    return SOURCE.observations(series, HIST_START)


def event_key(e):
    k = kind_of(e)
    return k if k in RELEASES else None


def title_period(e, k):
    d = d_(e["date"])
    if k == "gdp":
        m = re.search(r"Q([1-4])", e["title"])
        if not m:
            return None
        q = int(m.group(1))
        s = (q - 1) * 3 + 1
        return dt.date(d.year if s < d.month else d.year - 1, s, 1)
    m = re.search(r"\((%s)" % "|".join(MON), e["title"])
    if not m:
        return None
    mo = MON.index(m.group(1)) + 1
    return dt.date(d.year if mo <= d.month else d.year - 1, mo, 1)


def component_figures(e, k, label, series, mode, released):
    """(actual, previous, history list) for one component."""
    obs = series_obs(series)
    if not obs:
        return None, None, None
    tr = transformed(obs, mode)
    if not tr:
        return None, None, None
    fresh = lambda row: row[2] >= e["date"]
    if k == "fomc":
        before = [r for r in tr if r[0] <= e["date"]]
        after = [r for r in tr if r[0] > e["date"]]
        return (fmt(mode, after[0][1]) if released and after else None), (fmt(mode, before[-1][1]) if before else None), tr
    if k == "claims":
        cutoff = (d_(e["date"]) - dt.timedelta(days=4)).isoformat()
        cand = [i for i, r in enumerate(tr) if r[0] <= cutoff]
        if not cand:
            return None, None, tr
        i = cand[-1]
        if released and fresh(tr[i]):
            return fmt(mode, tr[i][1]), (fmt(mode, tr[i - 1][1]) if i else None), tr[:i + 1]
        return None, (fmt(mode, tr[i][1]) if not fresh(tr[i]) else None), tr
    per = title_period(e, k)
    if not per:
        return None, None, tr
    i = next((j for j, r in enumerate(tr) if r[0] == per.isoformat()), None)
    if k == "gdp" and "advance" not in e["title"].lower():
        if i is None:
            return None, None, tr
        if released and fresh(tr[i]):
            return fmt(mode, tr[i][1]), None, tr[:i + 1]
        return None, fmt(mode, tr[i][1]), tr
    if i is not None:
        act = fmt(mode, tr[i][1]) if released and fresh(tr[i]) else None
        return act, (fmt(mode, tr[i - 1][1]) if i else None), (tr[:i + 1] if act else tr)
    want_m = per.month - (3 if k == "gdp" else 1)
    want = dt.date(per.year if want_m > 0 else per.year - 1, want_m if want_m > 0 else want_m + 12, 1)
    return None, (fmt(mode, tr[-1][1]) if tr[-1][0] == want.isoformat() else None), tr


def snapshot_dates(release):
    before = release - dt.timedelta(days=1)
    after = release + dt.timedelta(days=1)
    while after.weekday() >= 5:
        after += dt.timedelta(days=1)
    return before.isoformat(), min(TODAY, after).isoformat()


def public_figures(e, kind, series, mode, released):
    """Verify an observation against the archived snapshot before its release."""
    release = d_(e["date"])
    period = title_period(e, kind)
    if kind == "claims":
        period = release - dt.timedelta(days=(release.weekday() - 5) % 7)
        if series == "CCSA":
            period -= dt.timedelta(days=7)
    elif kind == "fomc":
        period = release + dt.timedelta(days=1)
    if period is None:
        return None, None, None

    target = period.isoformat()
    if not released:
        # The most recent earlier observation is a prior reading, never an actual.
        current = transformed(series_obs(series) or [], mode)
        earlier = [row for row in current if row[0] < target]
        return None, fmt(mode, earlier[-1][1]) if earlier else None, None

    before_date, after_date = snapshot_dates(release)
    before = publicdata.observations(series, HIST_START, before_date)
    after = publicdata.observations(series, HIST_START, after_date)
    if not before or not after:
        return None, None, None
    prior = transformed(before, mode)
    available = [row for row in transformed(after, mode) if row[0] <= target]
    old = next((row[1] for row in prior if row[0] == target), None)
    earlier = [row for row in available if row[0] < target]
    actual = available[-1] if available and available[-1][0] == target else None
    if old is not None:
        # GDP and provisional surveys can publish a second estimate of the same period.
        if kind not in ("gdp", "umich") or not actual or actual[1] == old:
            return None, fmt(mode, old), None
        return fmt(mode, actual[1]), fmt(mode, old), available
    previous = fmt(mode, earlier[-1][1]) if earlier else None
    return (fmt(mode, actual[1]), previous, available) if actual else (None, previous, None)


def per_label(iso, k):
    d = d_(iso)
    if k == "gdp":
        return f"Q{(d.month - 1) // 3 + 1} {d.year}"
    if k == "claims":
        return f"week to {MON[d.month - 1]} {d.day}"
    return f"{MON[d.month - 1]} {d.year}"


def facts_for(k, label, mode, hist):
    """Up to two plain facts about the latest value: a record, a streak, or where it sits against five years."""
    if not hist or len(hist) < 8:
        return []
    vals = [v for _, v, _ in hist]
    v, dates = vals[-1], [d for d, _, _ in hist]
    unit = {"claims": "week", "gdp": "quarter"}.get(k, "month")
    w0 = label.split()[0]
    label = label if (w0.isupper() and len(w0) > 1) else label[0].lower() + label[1:]
    out = []
    up = next((j for j in range(len(vals) - 2, -1, -1) if vals[j] >= v), None)
    down = next((j for j in range(len(vals) - 2, -1, -1) if vals[j] <= v), None)
    gap_hi = len(vals) - 1 - (up if up is not None else -1)
    gap_lo = len(vals) - 1 - (down if down is not None else -1)
    record = False
    if gap_hi >= 6 and v != vals[-2]:
        out.append(f"The {label} reading was the highest since {per_label(dates[up], k)}." if up is not None
                   else f"The {label} reading was the highest since at least {per_label(dates[0], k)}.")
        record = True
    elif gap_lo >= 6 and v != vals[-2]:
        out.append(f"The {label} reading was the lowest since {per_label(dates[down], k)}." if down is not None
                   else f"The {label} reading was the lowest since at least {per_label(dates[0], k)}.")
        record = True
    sign_streak = mode == "diff" or (mode == "pct" and k not in ("cpi", "pce", "ppi"))
    if sign_streak:
        sign = 1 if v > 0 else -1 if v < 0 else 0
        n = 0
        for x in reversed(vals):
            if sign and (1 if x > 0 else -1 if x < 0 else 0) == sign:
                n += 1
            else:
                break
        if 3 <= n <= 24 and not (sign > 0 and n > 6):
            out.append(f"It was the {ordinal(n)} {unit}ly {'increase' if sign > 0 else 'decline'} in a row.")
    else:
        n, direction = 0, 0
        for a, b in zip(reversed(vals[:-1]), reversed(vals[1:])):
            dirn = 1 if b > a else -1 if b < a else 0
            if not dirn or (direction and dirn != direction):
                break
            direction = dirn
            n += 1
        if n >= 3:
            if k in ("cpi", "pce", "ppi"):
                what = "picked up" if direction > 0 else "slowed"
            else:
                what = "risen" if direction > 0 else "fallen"
            out.append(f"It has {what} {n} {unit}s in a row.")
    win = vals[-61:-1] if k != "claims" else vals[-261:-1]
    if not record and len(out) < 2 and len(win) >= 24:
        pct = round(100 * sum(1 for x in win if x < v) / len(win))
        if pct >= 85:
            out.append(f"That's higher than {pct}% of readings over the past five years.")
        elif pct <= 15:
            out.append(f"That's lower than {100 - pct}% of readings over the past five years.")
    return out[:2]


def ordinal(n):
    words = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth"}
    if n in words:
        return words[n]
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def recap(e, k):
    a, f, p, r = e.get("actual"), e.get("forecast"), e.get("previous"), e.get("revised")
    name = NAMES.get(k, e["title"])

    def n(x):
        try:
            return float(re.sub(r"[^0-9.\-]", "", x or "")) * (1000 if "M" in (x or "") else 1)
        except ValueError:
            return None

    s = f"{name} came in at {a}"
    av, fv = n(a), n(f)
    if f and av is not None and fv is not None:
        s += f" against a {f} forecast, " + ("above" if av > fv else "below" if av < fv else "in line with") + " expectations."
    else:
        s += "."
    if p:
        s += f" The previous reading was {p}" + (f", revised to {r}." if r and r != p else ".")
    extra = [c for c in e.get("components", [])[1:] if c.get("actual")]
    if extra:
        s += " " + "; ".join(f"{c['label']} {c['actual']}" + (f" (previous {c['previous']})" if c.get("previous") else "") for c in extra[:3]) + "."
    for fct in e.get("facts", [])[:2]:
        s += " " + fct
    return s


def history_add(hist, k, e):
    hk = HISTORY_KEYS.get(k)
    if not hk or (k == "gdp" and "advance" not in e["title"].lower()):
        return False
    comp = RELEASES.get(k, {}).get("comps", [("", "", "")])[0]
    ser = hist.setdefault("series", {}).setdefault(hk, {"name": NAMES.get(k, hk), "metric": comp[0], "rows": []})
    per = title_period(e, k)
    if per is None:
        return False
    label = f"Q{(per.month - 1) // 3 + 1} {per.year}" if k == "gdp" else f"{MON[per.month - 1]} {per.year}"
    if any(r.get("period") == label for r in ser["rows"]):
        return False
    ser["rows"].append({"period": label, "date": e["date"], "actual": e["actual"], "forecast": e.get("forecast", "")})
    ser["rows"].sort(key=lambda r: r["date"])
    ser["rows"] = ser["rows"][-(8 if k == "gdp" else 12):]
    return True


def update_figures(events, hist, pending):
    fc = load(os.path.join(ENG, "forecasts.json"), {}).get("forecasts", {})
    run_key = NOW.isoformat(timespec="minutes")
    ordered = sorted(events, key=when)
    claims_next = next((e["id"] for e in ordered if kind_of(e) == "claims" and not e.get("actual") and when(e) > NOW - dt.timedelta(hours=6)), None)
    candidates = []
    for e in events:
        k = kind_of(e)
        if k in (None, "holiday", "minutes", "beige"):
            continue
        if e["id"] in fc:
            for f in ("forecast", "fsrc"):
                if fc[e["id"]].get(f):
                    e[f] = fc[e["id"]][f]
        rk = event_key(e)
        if not rk:
            continue
        e.setdefault("metric", RELEASES[rk]["comps"][0][0])
        days_out = (d_(e["date"]) - TODAY).days
        if e.get("actual") or days_out > 42 or days_out < -14:
            continue
        if rk == "claims" and e["id"] != claims_next and NOW < when(e):
            continue
        released = NOW >= when(e) + dt.timedelta(minutes=20)
        candidates.append((e, rk, released))
    if not fredapi.KEY:
        requests = {(series, HIST_START, vintage)
                    for event, kind, released in candidates
                    for _, series, _ in RELEASES[kind]["comps"]
                    for vintage in (snapshot_dates(d_(event["date"])) if released else ("",))}
        publicdata.prefetch_observations(requests)
    hist_changed = False
    for e, rk, released in candidates:
        comps, head_hist, head_ok = [], None, True
        for i, (label, series, mode) in enumerate(RELEASES[rk]["comps"]):
            if fredapi.KEY:
                act, prev, h = component_figures(e, rk, label, series, mode, released)
            else:
                act, prev, h = public_figures(e, rk, series, mode, released)
            if prev and not qa.plausible(series, mode, prev):
                QA.check(f"plausible previous: {e['id']} {label}", False, f"{prev} rejected", critical=True)
                prev = None
            if act:
                verdict = qa.gate_figure(QA, e["id"], label, series, mode, act, [r[1] for r in (h or [])[:-1]], pending, run_key)
                if verdict != "publish":
                    act = None
                    if i == 0:
                        head_ok = False
            if i == 0:
                head_hist = h
                if prev and not e.get("previous"):
                    e["previous"] = prev
                elif prev and e.get("previous") and prev != e["previous"] and act:
                    e["revised"] = prev
                if act and head_ok:
                    e["actual"] = act
                    e["provenance"] = {"via": "FRED", "series": series, "published": h[-1][2]} if fredapi.KEY else {
                        "via": "ALFRED", "series": series, "asof": h[-1][2]}
            if act or prev:
                comps.append({"label": label, **({"actual": act} if act else {}), **({"previous": prev} if prev else {})})
        if comps and (head_ok or not e.get("actual")):
            e["components"] = comps
        if e.get("actual"):
            log("actual", e["id"], e["actual"])
            label, _, mode = RELEASES[rk]["comps"][0]
            e["facts"] = facts_for(rk, label, mode, head_hist)
            if e.get("impact") == "high" or rk in ("claims", "ppi"):
                e["recap"] = recap(e, rk)
            if history_add(hist, rk, e):
                hist_changed = True
    rel = [e for e in ordered if kind_of(e) == "claims" and e.get("actual")]
    nxt = [e for e in ordered if kind_of(e) == "claims" and not e.get("actual")]
    if rel and nxt and not nxt[0].get("previous"):
        nxt[0]["previous"] = rel[-1]["actual"]
    return hist_changed


# ---------------------------------------------------------------- markets and reactions
def market_tiles():
    tiles = {}
    for key, label, series, kind in MARKETS:
        obs = SOURCE.observations(series, (TODAY - dt.timedelta(days=400)).isoformat())
        if not obs or len(obs) < 2:
            continue
        v = [x[1] for x in obs]

        def chg(n):
            if len(v) <= n:
                return None
            d = v[-1] - v[-1 - n]
            if kind in ("yield", "spread"):
                return round(d * 100)  # basis points
            if kind in ("index", "price"):
                return round((v[-1] / v[-1 - n] - 1) * 100, 2)
            return round(d, 2)

        weekly = series in ("NFCI", "MORTGAGE30US")
        spark = v[-(52 if weekly else 120):]
        step = max(1, len(spark) // 60)
        tiles[key] = {"label": label, "value": round(v[-1], 2), "date": obs[-1][0], "kind": kind,
                      "d1": chg(1), "d5": chg(1 if weekly else 5), "d21": chg(4 if weekly else 21),
                      "spark": [round(x, 3) for x in spark[::step]] + ([round(spark[-1], 3)] if (len(spark) - 1) % step else [])}
    return tiles


def reactions(events):
    """How 2y/10y yields and the dollar moved on past release days, against the average day."""
    names = (fredapi.releases() or {}) if fredapi.KEY else {}
    daily = {}
    for key, series, unit in REACTION_SERIES:
        obs = SOURCE.observations(series, (TODAY - dt.timedelta(days=4 * 365)).isoformat())
        if obs and len(obs) > 30:
            daily[key] = obs
    if not daily:
        return None

    def move(key, date):
        obs = daily.get(key)
        if not obs:
            return None
        i = next((j for j, o in enumerate(obs) if o[0] == date), None)
        if not i:
            return None
        a, b = obs[i - 1][1], obs[i][1]
        return round((b - a) * 100, 1) if key != "usd" else round((b / a - 1) * 100, 2)

    out = {"asof": TODAY.isoformat(), "baseline": {}, "series": {}}
    all_rel = set()
    for k in REACTION_KEYS:
        cfg = RELEASES[k]
        rid = next((i for n, i in names.items() if re.search(cfg["fred"], n)), None) or cfg["rid"]
        start = (TODAY - dt.timedelta(days=3 * 365)).isoformat()
        if fredapi.KEY:
            dates = SOURCE.release_dates(rid, start, TODAY.isoformat())
        else:
            dates = []
            months = 6 if k != "claims" else 4
            for offset in range(0, 36, months):
                end = TODAY - dt.timedelta(days=offset * 30)
                window = SOURCE.release_dates(rid, (end - dt.timedelta(days=months * 30 - 1)).isoformat(), end.isoformat())
                dates.extend(window or [])
                if len(dates) >= (12 if k != "claims" else 26):
                    break
            dates = sorted(set(dates))
        if not dates:
            continue
        dates = [x for x in dates if x < TODAY.isoformat() and d_(x).weekday() < 5]
        all_rel |= set(dates)
        rows = []
        for x in dates[-(12 if k != "claims" else 26):]:
            r = {"date": x}
            for key in daily:
                m = move(key, x)
                if m is not None:
                    r[key] = m
            if len(r) > 1:
                rows.append(r)
        if not rows:
            continue
        avg = {key: round(statistics.mean(abs(r[key]) for r in rows if key in r), 2) for key in daily if any(key in r for r in rows)}
        out["series"][k] = {"name": NAMES.get(k, k), "avg": avg, "rows": rows[::-1]}
    one_year = (TODAY - dt.timedelta(days=365)).isoformat()
    for key, obs in daily.items():
        ch = [abs(m) for j in range(1, len(obs)) if obs[j][0] >= one_year and obs[j][0] not in all_rel
              for m in [((obs[j][1] - obs[j - 1][1]) * 100) if key != "usd" else ((obs[j][1] / obs[j - 1][1] - 1) * 100)]]
        if ch:
            out["baseline"][key] = round(statistics.mean(ch), 2)
    for k, s in out["series"].items():
        s["ratio"] = {key: round(s["avg"][key] / out["baseline"][key], 1) for key in s["avg"] if out["baseline"].get(key)}
    return out


# ---------------------------------------------------------------- brief, outlook, Fed, feeds
def next_fomc(events):
    return next((e for e in sorted(events, key=when) if kind_of(e) == "fomc" and when(e) >= NOW - dt.timedelta(hours=3)), None)


def fomc_label(e):
    d = d_(e["date"])
    p = d - dt.timedelta(days=1)
    return f"{MON[d.month - 1]} {p.day}–{d.day}" if p.month == d.month else f"{MON[p.month - 1]} {p.day}–{MON[d.month - 1]} {d.day}"


def clean(t):
    return re.sub(r"\s*\(.*?\)\s*$", "", t.split(" · ")[0])


def item_line(e):
    bits = [e["title"]]
    if e.get("actual"):
        bits.append("actual " + e["actual"])
    if e.get("forecast"):
        bits.append("forecast " + e["forecast"])
    if e.get("previous"):
        bits.append("previous " + e["previous"])
    return " · ".join(bits)


def brief_day():
    d = TODAY
    if d.weekday() >= 5 or NOW.hour >= 16:
        d += dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
    return d


def market_line(tiles):
    parts = []
    y2, y10, usd, oil = tiles.get("y2"), tiles.get("y10"), tiles.get("usd"), tiles.get("oil")
    if y10:
        bp = y10["d1"] or 0
        parts.append(f"the 10-year Treasury yield was {y10['value']:.2f}%" + (f" ({'up' if bp > 0 else 'down'} {abs(bp)} bp)" if bp else " (unchanged)"))
    if y2:
        bp = y2["d1"] or 0
        parts.append(f"the 2-year {y2['value']:.2f}%" + (f" ({'up' if bp > 0 else 'down'} {abs(bp)} bp)" if bp else ""))
    if usd:
        ch = usd["d1"] or 0
        parts.append(f"the Fed's broad dollar index {usd['value']:.1f}" + (f" ({'up' if ch > 0 else 'down'} {abs(ch):.1f}%)" if abs(ch) >= 0.05 else " (little changed)"))
    if oil:
        ch = oil["d1"] or 0
        parts.append(f"WTI crude ${oil['value']:.2f}" + (f" ({'up' if ch > 0 else 'down'} {abs(ch):.1f}%)" if abs(ch) >= 0.1 else ""))
    if not parts:
        return ""
    date = d_((y10 or y2 or usd or oil)["date"])
    return f"At the {fmt_day(date)} close, " + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] + "."


def write_brief(events, tiles):
    d = brief_day()
    todays = sorted([e for e in events if e["date"] == d.isoformat()], key=when)
    hol = [e for e in todays if e.get("impact") == "holiday"]
    rel = [e for e in todays if e.get("impact") in ("high", "medium") and e.get("time")]
    high = [e for e in rel if e.get("impact") == "high"]
    if hol and "closed" in hol[0]["title"].lower():
        head = hol[0]["title"]
    elif high:
        head = f"{clean(high[0]['title'])} at {high[0]['time']} NY" + (f", plus {len(rel) - 1} more" if len(rel) > 1 else "")
    elif rel:
        head = f"Lighter data day: {clean(rel[0]['title'])} at {rel[0]['time']} NY"
    else:
        head = "No major US data today"
    focus = [f"{clean(e['title'])}: {WHY[kind_of(e)]}" for e in (high or rel)[:2] if kind_of(e) in WHY]
    f = next_fomc(events)
    if f:
        n = (d_(f["date"]) - d).days
        focus.append("The Fed decides today." if n == 0 else f"The next Fed decision is {fomc_label(f)}, {n} days away.")
    if hol:
        focus.append(f"{hol[0]['title']}. {hol[0].get('note', '')}")
    since = NOW - dt.timedelta(hours=30)
    recent = [e for e in sorted(events, key=when) if e.get("actual") and since <= when(e) <= NOW]
    brief = {"date": d.isoformat(), "asof": NOW.isoformat(timespec="minutes"), "headline": head[:80],
             "overnight": market_line(tiles), "overnightLabel": "Latest close",
             "today": [{"time": e["time"], "item": item_line(e)} for e in rel],
             "recent": [{"title": e["title"], "line": e.get("recap") or f"{clean(e['title'])}: {e['actual']}"} for e in recent][-4:],
             "focus": " ".join(x.strip() for x in focus if x.strip()),
             "note": "Built automatically from official release schedules and Federal Reserve data. Education only, not a forecast or financial advice."}
    return save(os.path.join(DATA, "brief", "today.json"), qa.lint_doc(QA, "brief", brief))


def write_outlook(events):
    mon = TODAY - dt.timedelta(days=TODAY.weekday())
    if TODAY.weekday() >= 5:
        mon += dt.timedelta(weeks=1)
    days = [mon + dt.timedelta(days=i) for i in range(5)]
    left = [x for x in days if x >= TODAY]
    if len(left) <= 2 and TODAY.weekday() < 5:
        days = left + [mon + dt.timedelta(weeks=1, days=i) for i in range(5)]
    out, highs = [], []
    for day in days:
        evs = sorted([e for e in events if e["date"] == day.isoformat() and e.get("impact") in ("high", "medium", "holiday")], key=when)
        if not evs:
            out.append({"d": fmt_day(day), "t": "No major US releases scheduled."})
            continue
        parts = []
        for e in evs:
            if e.get("impact") == "holiday":
                parts.append(e["title"] + ".")
                continue
            line = f"{e['title']} at {e['time']} NY"
            if e.get("previous"):
                line += f" (previous {e['previous']}" + (f", forecast {e['forecast']}" if e.get("forecast") else "") + ")"
            parts.append(line + ".")
            if e.get("impact") == "high":
                highs.append((day, e))
        top = next((e for e in evs if e.get("impact") == "high"), None)
        if top and kind_of(top) in WHY:
            parts.append(WHY[kind_of(top)])
        out.append({"d": fmt_day(day), "t": " ".join(parts)})
    week = f"{MON[days[0].month - 1]} {days[0].day}–" + (f"{days[-1].day}" if days[-1].month == days[0].month else f"{MON[days[-1].month - 1]} {days[-1].day}")
    if highs:
        names = ", ".join(clean(e["title"]) + " (" + day.strftime("%a") + ")" for day, e in highs[:5])
        summary = f"{len(highs)} high-impact release{'s' if len(highs) != 1 else ''}: {names}."
    else:
        summary = "No high-impact US releases."
    f = next_fomc(events)
    if f:
        summary += f" The next Fed decision is {fomc_label(f)}, {(d_(f['date']) - TODAY).days} days from today."
    return save(os.path.join(DATA, "outlook", "current.json"), qa.lint_doc(QA, "outlook", {"week": week, "asof": TODAY.isoformat(), "summary": summary, "days": out}))


def write_fed(events, tiles):
    man = load(os.path.join(ENG, "manual.json"), {})
    lo = SOURCE.observations("DFEDTARL", "2015-01-01")
    hi = SOURCE.observations("DFEDTARU", "2015-01-01")
    fed = {"asof": TODAY.isoformat()}
    if lo and hi:
        fed["rate"] = f"{lo[-1][1]:.2f}%–{hi[-1][1]:.2f}%"
        changes = [(hi[i][0], hi[i][1] - hi[i - 1][1]) for i in range(1, len(hi)) if hi[i][1] != hi[i - 1][1]]
        if changes:
            dd, mv = changes[-1]
            d = d_(dd)
            fed["last"] = f"The target range was last {'raised' if mv > 0 else 'cut'} by {abs(mv):.2f} point, effective {MON[d.month - 1]} {d.day}, {d.year}."
            ups = 0
            for _, m in reversed(changes):
                if (m > 0) == (mv > 0):
                    ups += 1
                else:
                    break
            if ups >= 2:
                fed["last"] += f" That was the {ordinal(ups)} {'increase' if mv > 0 else 'cut'} in a row."
        mid = (lo[-1][1] + hi[-1][1]) / 2
        y2 = tiles.get("y2")
        if y2:
            gap = round((y2["value"] - mid) * 100)
            fed["gap"] = f"The 2-year Treasury yield is {abs(gap)} bp {'above' if gap >= 0 else 'below'} the middle of the target range. A 2-year yield above the policy rate usually means markets expect rates to stay higher or rise; below, that they expect cuts."
    elif man.get("rateFallback"):
        fed["rate"] = man["rateFallback"]
    f = next_fomc(events)
    if f:
        fed["next"] = fomc_label(f)
        fed["daysTo"] = (d_(f["date"]) - TODAY).days
    if tiles.get("effr"):
        fed["effr"] = f"{tiles['effr']['value']:.2f}%"
    for k, field in (("fedPricing", "pricing"), ("fedWatch", "watch")):
        v = man.get(k) or {}
        if v.get("text"):
            fed[field] = v["text"] + (f" (as of {v['asof']})" if v.get("asof") else "")
    if not fed.get("rate"):
        return False
    return save(os.path.join(DATA, "fed", "current.json"), qa.lint_doc(QA, "fed", fed))


def ics(events, only_high=False):
    def esc(s):
        return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Displace//Economic calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:Displace{' · high impact' if only_high else ''}", "X-WR-TIMEZONE:America/New_York",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    stamp = NOW.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in sorted(events, key=when):
        if d_(e["date"]) < TODAY - dt.timedelta(days=7):
            continue
        if only_high and e.get("impact") not in ("high", "holiday"):
            continue
        if e.get("impact") not in ("high", "medium", "holiday"):
            continue
        desc = [x for x in [e.get("note", ""), ("Previous: " + e["previous"]) if e.get("previous") else "",
                            ("Forecast: " + e["forecast"]) if e.get("forecast") else "", ("Actual: " + e["actual"]) if e.get("actual") else "",
                            "Education only, not financial advice."] if x]
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@displace", f"DTSTAMP:{stamp}"]
        if e.get("time"):
            start = when(e)
            lines += [f"DTSTART;TZID=America/New_York:{start.strftime('%Y%m%dT%H%M%S')}",
                      f"DTEND;TZID=America/New_York:{(start + dt.timedelta(minutes=15)).strftime('%Y%m%dT%H%M%S')}",
                      "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(e['title'])}", "TRIGGER:-PT15M", "END:VALARM"]
        else:
            dd = d_(e["date"])
            lines += [f"DTSTART;VALUE=DATE:{dd.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(dd + dt.timedelta(days=1)).strftime('%Y%m%d')}"]
        mark = {"high": "🔴 ", "medium": "🟠 ", "holiday": ""}.get(e.get("impact"), "")
        lines += [f"SUMMARY:{esc(mark + e['title'])}", f"DESCRIPTION:{esc(' '.join(desc))}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    out = []
    for line in lines:  # fold at 75 octets
        b = line.encode()
        while len(b) > 75:
            cut = 75
            while (b[cut] & 0xC0) == 0x80:
                cut -= 1
            out.append(b[:cut].decode())
            b = b" " + b[cut:]
        out.append(b.decode())
    return "\r\n".join(out) + "\r\n"


# ---------------------------------------------------------------- run
def main():
    source_name = "FRED API" if fredapi.KEY else "public FRED and ALFRED"
    log("engine run", NOW.isoformat(timespec="minutes"), "using", source_name)
    cal = load(os.path.join(DATA, "calendar", "events.json"), {"events": []})
    hist = load(os.path.join(DATA, "history", "main.json"), {"series": {}})
    events = cal.get("events", [])
    pending_path = os.path.join(ENG, "pending.json")
    pending = load(pending_path, {})
    autos, answered = auto_events()
    for k in RELEASES:
        QA.check(f"source: release calendar for {k}", k in answered, "no dates returned; keeping existing dates")
    merge(events, autos, answered)
    merge_schedule(events)
    events = prune(events)
    hist_changed = update_figures(events, hist, pending)
    save(pending_path, pending)
    for e in events:
        k = kind_of(e)
        if e.get("impact") == "high" and k in WHY and not e.get("brief") and 0 <= (d_(e["date"]) - TODAY).days <= 10:
            bits = [f"The previous reading was {e['previous']}."] if e.get("previous") else []
            bits.append(WHY[k])
            f = next_fomc(events)
            if f and f["id"] != e["id"]:
                bits.append(f"The next Fed decision is {fomc_label(f)}.")
            e["brief"] = {"asof": TODAY.isoformat(), "context": " ".join(bits)}
    events.sort(key=lambda e: (e["date"], e.get("time") or "00:00", e["title"]))
    for e in events:
        qa.lint_event(QA, e)
    qa.check_calendar(QA, events, kind_of, TODAY)
    calendar_ok = not any(c["name"].startswith(("calendar:", "figure format")) for c in QA.critical_fail)
    body = {"through": events[-1]["date"] if events else TODAY.isoformat(), "events": events}
    old = load(os.path.join(DATA, "calendar", "events.json"), {})
    if not calendar_ok:
        warn("calendar failed quality checks: kept the last good calendar")
    elif {"through": old.get("through"), "events": old.get("events")} != body:
        save(os.path.join(DATA, "calendar", "events.json"), {"updated": TODAY.isoformat(), **body})
        log("calendar saved")
    if not calendar_ok:
        events = old.get("events", events)
    if calendar_ok and hist_changed:
        n0 = len(QA.critical_fail)
        qa.check_history(QA, hist)
        if len(QA.critical_fail) == n0:
            hist["asof"] = TODAY.isoformat()
            save(os.path.join(DATA, "history", "main.json"), hist)
        else:
            warn("release stats failed quality checks: kept the last good version")
    tiles = {**load(os.path.join(DATA, "markets", "latest.json"), {}).get("tiles", {}), **market_tiles()}
    if tiles:
        tiles = qa.check_markets(QA, tiles, {k: s for k, _, s, _ in MARKETS}, TODAY)
        save(os.path.join(DATA, "markets", "latest.json"), {"asof": TODAY.isoformat(), "tiles": tiles})
    if TODAY.weekday() == 6 or not load(os.path.join(DATA, "history", "reactions.json"), {}).get("series"):
        rx = qa.check_reactions(QA, reactions(events))
        if rx and rx["series"]:
            save(os.path.join(DATA, "history", "reactions.json"), rx)
    write_brief(events, tiles)
    write_outlook(events)
    write_fed(events, tiles)
    try:  # company earnings dates for the Nasdaq-100 heavyweights; never let them break the calendar
        import earnings
        earnings.run(ROOT, TODAY, log)
    except Exception as ex:
        warn(f"earnings dates error: {ex!r}")
    save(os.path.join(ROOT, "site", "calendar.ics"), None, ics(events))
    save(os.path.join(ROOT, "site", "calendar-high.ics"), None, ics(events, only_high=True))
    # schedule health
    future = [e for e in events if kind_of(e) not in ("claims", "holiday", None) and e["date"] >= TODAY.isoformat()]
    through = max((e["date"] for e in future), default=TODAY.isoformat())
    stale_path = os.path.join(ENG, "STALE")
    if d_(through) < TODAY + dt.timedelta(days=35):
        warn(f"release calendar only runs to {through}")
        with open(stale_path, "w") as fh:
            fh.write(f"The release calendar only runs to {through}. Check source coverage or add confirmed dates to engine/schedule.json.\n")
    elif os.path.exists(stale_path):
        os.remove(stale_path)
    source_stats = SOURCE.STATS
    if source_stats["errors"]:
        warn(f"Data source errors on {source_stats['errors']} request(s): {', '.join(map(str, source_stats['failed'][:8]))}")
    qrep = QA.to_json(NOW.isoformat(timespec="minutes"))
    save(os.path.join(DATA, "engine", "quality.json"), qrep)
    fail_path = os.path.join(ENG, "QUALITY_FAIL")
    if QA.critical_fail:
        with open(fail_path, "w") as fh:
            fh.write("Critical quality checks failed on the last engine run. Bad output was not published.\n\n")
            for c in QA.critical_fail[:20]:
                fh.write(f"- {c['name']}: {c['detail']}\n")
        warn(f"{len(QA.critical_fail)} critical quality check(s) failed")
    elif os.path.exists(fail_path):
        os.remove(fail_path)
    log(f"quality: {QA.passed}/{len(QA.checks)} checks passed, {len(QA.held)} held, {len(QA.rejected)} rejected")
    status = {"lastRun": NOW.isoformat(timespec="minutes"), "source": source_name, "fredCalls": source_stats["calls"],
              "fred": bool(fredapi.KEY or source_stats["calls"] > source_stats["errors"]),
              "quality": {"passed": QA.passed, "total": len(QA.checks), "held": len(QA.held), "rejected": len(QA.rejected), "critical": len(QA.critical_fail)},
              "fredErrors": source_stats["errors"], "calendarThrough": through, "events": len(events),
              "upcoming": sum(1 for e in events if e["date"] >= TODAY.isoformat()), "warnings": WARN, "log": LOG[-30:]}
    save(os.path.join(DATA, "engine", "status.json"), status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
