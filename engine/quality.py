"""Quality checks. Every figure and sentence the engine publishes passes through here.

Three layers:
  1. Plausibility: each figure must sit inside a hard range for its series ("core CPI m/m between -1.5% and 2%").
     Outside it, the figure is rejected and never published.
  2. Confirmation: a figure that is possible but extreme for its own history (robust z-score above 6) is held
     until a later run sees the same value again, so one bad data pull can't go live.
  3. Content: generated text is linted for template errors and for trade-call language; failing text is dropped.
Plus structural checks on the calendar and data files. Results go to site/data/engine/quality.json.
"""
import datetime as dt
import re
import statistics

# (series, transform) -> (min, max). Values are in the units the engine shows (% , K, M, index level).
BOUNDS = {
    ("CPILFESL", "pct"): (-1.5, 2.0), ("CPIAUCSL", "pct"): (-2.5, 2.5),
    ("CPILFESL", "yoy"): (-3, 15), ("CPIAUCSL", "yoy"): (-5, 20),
    ("PPIFIS", "pct"): (-3.5, 3.5), ("PPIFES", "pct"): (-3, 3), ("PPIFIS", "yoy"): (-12, 25),
    ("PAYEMS", "diff"): (-1500, 1500), ("UNRATE", "pctlevel"): (2, 20),
    ("CES0500000003", "pct"): (-2, 3), ("CES0500000003", "yoy"): (-3, 12),
    ("RSAFS", "pct"): (-12, 12), ("RSFSXMV", "pct"): (-12, 12), ("RSAFS", "yoy"): (-20, 35),
    ("A191RL1Q225SBEA", "pctlevel"): (-35, 35),
    ("PCEPILFE", "pct"): (-1.5, 2), ("PCEPI", "pct"): (-2, 2.5), ("PCEPILFE", "yoy"): (-3, 15),
    ("PCE", "pct"): (-10, 10), ("PI", "pct"): (-10, 15),
    ("ICSA", "claims"): (100, 1500), ("IC4WSA", "claims"): (100, 1500), ("CCSA", "claimsM"): (0.5, 10),
    ("JTSJOL", "millions"): (3, 15), ("JTSQUR", "pctlevel"): (1, 4.5),
    ("UMCSENT", "level1"): (40, 115), ("MICH", "pctlevel"): (0, 15),
    ("DGORDER", "pct"): (-25, 30), ("ADXTNO", "pct"): (-10, 10),
    ("HSN1F", "thousands"): (300, 1500), ("ADPMNUSNERSA", "diffPersons"): (-2000, 2000),
    ("DFEDTARU", "rate"): (0, 10),
}
MARKET_BOUNDS = {"DGS2": (0, 10), "DGS10": (0, 10), "T10Y2Y": (-3, 4), "T10YIE": (0, 5), "DFII10": (-2, 5), "DFF": (0, 10),
                 "DTWEXBGS": (80, 160), "DCOILWTICO": (0, 250), "NFCI": (-2, 5), "MORTGAGE30US": (1, 15)}
MARKET_DAY_MOVE = {"yield": 75, "spread": 75, "index": 4.0, "price": 30.0, "index2": 1.5}  # bp or %
HISTORY_SCALE = {"diffPersons": 1000, "claims": 1000, "claimsM": 1_000_000, "millions": 1000}

FORBIDDEN = re.compile(
    r"\b(buy|sell|go long|go short|going long|going short|entry|entries|stop[- ]loss|take[- ]profit|price target|"
    r"you should|we recommend|recommend(ed)? (that|you)|will (rise|fall|go up|go down|rally|drop|crash)|guarantee[ds]?|signal to)\b", re.I)
BROKEN = re.compile(r"\bNone\b|\bnan\b|\{|\}|\s{2,}|\.\.(?!\.)|\(\)|\bundefined\b")


def number(s):
    """'0.3%' -> 0.3, '165K' -> 165, '1.95M' -> 1.95, '52.4' -> 52.4."""
    if s is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(s).replace(",", ""))
    return float(m.group(0)) if m else None


class Report:
    def __init__(self):
        self.checks, self.rejected, self.held, self.dropped_text = [], [], [], []

    def check(self, name, ok, detail="", critical=False):
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail, "critical": critical})
        return ok

    @property
    def passed(self):
        return sum(1 for c in self.checks if c["ok"])

    @property
    def critical_fail(self):
        return [c for c in self.checks if c["critical"] and not c["ok"]]

    def to_json(self, asof):
        return {"asof": asof, "passed": self.passed, "total": len(self.checks),
                "critical": len(self.critical_fail), "rejected": self.rejected, "held": self.held,
                "droppedText": self.dropped_text, "failures": [c for c in self.checks if not c["ok"]][:40]}


# ---------------------------------------------------------------- figures
def plausible(series, mode, shown):
    lo, hi = BOUNDS.get((series, mode), (None, None))
    v = number(shown)
    if v is None:
        return False
    if lo is None:
        return True
    return lo <= v <= hi


def robust_z(value, history):
    """How unusual `value` is against `history` (median and MAD based, so one outlier can't skew it)."""
    h = [x for x in history if x is not None][-60:]
    if len(h) < 12:
        return 0.0
    med = statistics.median(h)
    mad = statistics.median(abs(x - med) for x in h) * 1.4826
    if mad == 0:
        return 0.0 if value == med else 99.0
    return abs(value - med) / mad


def gate_figure(rep, event_id, label, series, mode, shown, history_vals, pending, run_key):
    """Decide whether a freshly released figure can be published. Returns 'publish', 'hold' or 'reject'."""
    if not plausible(series, mode, shown):
        rep.rejected.append({"event": event_id, "component": label, "value": shown, "reason": "outside the plausible range"})
        rep.check(f"plausible: {event_id} {label}", False, f"{shown} is outside the range for {series}", critical=True)
        return "reject"
    rep.check(f"plausible: {event_id} {label}", True)
    v = number(shown)
    scale = HISTORY_SCALE.get(mode, 1)
    z = robust_z(v, [value / scale for value in history_vals if value is not None])
    if z > 6:
        key = f"{event_id}|{label}"
        prev = pending.get(key)
        if prev and prev.get("value") == shown and prev.get("run") != run_key:
            rep.check(f"confirmed: {event_id} {label}", True, f"{shown} seen again (z={z:.1f})")
            pending.pop(key, None)
            return "publish"
        pending[key] = {"value": shown, "run": run_key, "z": round(z, 1)}
        rep.held.append({"event": event_id, "component": label, "value": shown, "z": round(z, 1)})
        rep.check(f"held for confirmation: {event_id} {label}", True, f"unusual value {shown} (z={z:.1f}) waits for the next run")
        return "hold"
    return "publish"


# ---------------------------------------------------------------- text
def clean_text(rep, where, text):
    """Return the text if it passes content checks, otherwise None (and record why)."""
    if not text:
        return text
    if FORBIDDEN.search(text):
        rep.dropped_text.append({"where": where, "reason": "trade-call language", "text": text[:160]})
        rep.check(f"text: {where}", False, "contained trade-call language", critical=True)
        return None
    if BROKEN.search(text):
        rep.dropped_text.append({"where": where, "reason": "template error", "text": text[:160]})
        rep.check(f"text: {where}", False, "template error", critical=True)
        return None
    return text


def lint_event(rep, e):
    for f in ("recap", "note"):
        if e.get(f):
            t = clean_text(rep, f"{e['id']}.{f}", e[f])
            if t is None:
                e.pop(f, None)
    if e.get("facts"):
        e["facts"] = [f for f in (clean_text(rep, f"{e['id']}.fact", x) for x in e["facts"]) if f]
    b = e.get("brief") or {}
    if b.get("context") and clean_text(rep, f"{e['id']}.brief", b["context"]) is None:
        e.pop("brief", None)


def lint_doc(rep, name, obj):
    """Lint every string in a generated document; blank the bad ones. Returns obj."""
    def walk(o, path):
        if isinstance(o, dict):
            for k in list(o):
                if isinstance(o[k], str):
                    if k in ("date", "asof", "lastRun", "id", "time", "kind", "label", "d"):
                        continue
                    t = clean_text(rep, f"{name}.{path}{k}", o[k])
                    if t is None:
                        o[k] = ""
                else:
                    walk(o[k], f"{path}{k}.")
        elif isinstance(o, list):
            for i, x in enumerate(o):
                if isinstance(x, str):
                    if clean_text(rep, f"{name}.{path}{i}", x) is None:
                        o[i] = ""
                else:
                    walk(x, f"{path}{i}.")
    walk(obj, "")
    return obj


# ---------------------------------------------------------------- structure
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def check_calendar(rep, events, kind_of, today):
    ids = [e.get("id") for e in events]
    rep.check("calendar: unique ids", len(ids) == len(set(ids)), f"{len(ids) - len(set(ids))} duplicate ids", critical=True)
    bad = []
    for e in events:
        try:
            d = dt.date.fromisoformat(e["date"])
        except (KeyError, ValueError):
            bad.append(f"{e.get('id')}: bad date")
            continue
        if e.get("impact") not in ("high", "medium", "low", "holiday"):
            bad.append(f"{e['id']}: impact {e.get('impact')}")
        if e.get("impact") != "holiday" and not TIME.match(e.get("time") or ""):
            bad.append(f"{e['id']}: time {e.get('time')}")
        if e.get("impact") != "holiday" and d.weekday() >= 5:
            bad.append(f"{e['id']}: release on a weekend")
        if not e.get("title"):
            bad.append(f"{e['id']}: no title")
    rep.check("calendar: every event well-formed", not bad, "; ".join(bad[:6]), critical=True)
    keys = [(kind_of(e), e["date"], "closed" in e.get("title", "").lower()) for e in events if e.get("date")]
    dup = len(keys) - len(set(keys))
    rep.check("calendar: no duplicate releases", dup == 0, f"{dup} duplicates", critical=True)
    future = [e for e in events if e.get("date", "") >= today.isoformat() and e.get("impact") in ("high", "medium")]
    rep.check("calendar: at least 5 weeks of releases ahead",
              bool(future) and max(e["date"] for e in future) >= (today + dt.timedelta(days=35)).isoformat(),
              f"runs to {max((e['date'] for e in future), default='nothing')}")
    stray = [e["id"] for e in events if e.get("actual") and e.get("date", "") > today.isoformat()]
    rep.check("calendar: no actual figure on a future release", not stray, ", ".join(stray[:5]), critical=True)
    for e in events:
        for c in e.get("components", []) or []:
            if c.get("actual") is not None and number(c["actual"]) is None:
                rep.check(f"figure format: {e['id']} {c.get('label')}", False, str(c["actual"]), critical=True)


def check_markets(rep, tiles, series_of, today):
    for key, t in list(tiles.items()):
        series = series_of.get(key)
        lo, hi = MARKET_BOUNDS.get(series, (None, None))
        ok_range = lo is None or lo <= t["value"] <= hi
        lim = MARKET_DAY_MOVE.get(t.get("kind"), None)
        ok_move = t.get("d1") is None or lim is None or abs(t["d1"]) <= lim
        age = (today - dt.date.fromisoformat(t["date"])).days
        weekly = series in ("NFCI", "MORTGAGE30US")
        fresh = age <= (16 if weekly else 7)
        if not (ok_range and ok_move):
            rep.check(f"market: {key}", False, f"value {t['value']} / day move {t.get('d1')} failed sanity checks", critical=True)
            tiles.pop(key)
            continue
        if not fresh:
            t["stale"] = True
        rep.check(f"market: {key}", True if fresh else False, "" if fresh else f"last data {t['date']} ({age} days old)")
    return tiles


def check_reactions(rep, rx):
    if not rx:
        return rx
    for k in list(rx.get("series", {})):
        n = len(rx["series"][k].get("rows", []))
        if n < 6:
            rep.check(f"reactions: {k} sample size", False, f"only {n} release days, hidden until there are 6")
            rx["series"].pop(k)
        else:
            rep.check(f"reactions: {k} sample size", True)
    return rx


def check_history(rep, hist):
    for k, s in hist.get("series", {}).items():
        rows = s.get("rows", [])
        dates = [r.get("date", "") for r in rows]
        ok = dates == sorted(dates) and len(rows) <= 12 and all(number(r.get("actual")) is not None for r in rows)
        rep.check(f"stats: {k} rows valid", ok, f"{len(rows)} rows", critical=True)
