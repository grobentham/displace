"""Iron Brain's live intraday plans, witnessed and scored by Displace's rules.

Iron Brain locks each plan decision (orders, a trade, or no trade) and publishes it on its desk. Its full lock
record is private, so this module is the public witness: a workflow (.github/workflows/witness.yml) reads the
published decisions every 10 minutes through the New York morning and commits what it saw to Displace's public
`witness` branch. That branch's commit history is the timestamp proof.

A finished trade counts in the scorecard only if
  1. it was locked before entry: as stop orders before the fill, or as a trade no later than its signal minute,
  2. Displace saw it unfinished before it saw the result, and
  3. none of its locked levels changed after Displace first saw them.
A trade that passes 2 and 3 but was locked after its entry minute (an hourly rule that enters at the 10:00 open and
is published at 10:13, say) is scored separately as `late_lock`, with the lag: its result uses the rule's entry
price, which someone following the published plan could not have had. Everything else stays in the ledger. Results are in NQ points and in R (points / locked risk).
"""
import datetime as dt
import json
import os
import sys
import urllib.request

SOURCE = "https://grobentham.github.io/iron-brain/data/desk.json"
SINCE = "2026-11-25"                         # first day witnessed
MIN_TRADES = 30                              # fewer finished trades than this: no claim either way
FINAL = ("stopped", "target", "closed")
LOCK_FIELDS = ("lockedAt", "buyStop", "sellStop", "dir", "entry", "stop", "at", "filledAt")
STATUSES = ("counted", "pending", "no_trade", "expired", "late_lock", "unwitnessed", "altered")


def key(r):
    return f'{r["date"]}|{r["market"]}|{r["id"]}'


def observe(store, rows, now):
    """Fold one reading of Iron Brain's published decisions into the witness store."""
    seen = now.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    recs = store.setdefault("records", {})
    for r in rows:
        if not r.get("date") or r["date"] < SINCE or not r.get("id"):
            continue
        rec = recs.setdefault(key(r), {"date": r["date"], "market": r.get("market"), "id": r["id"],
                                       "name": r.get("name") or r["id"], "first_seen": seen, "lock": {}})
        rec["state"] = r.get("state")
        for f in LOCK_FIELDS:
            v = r.get(f)
            if v is None:
                continue
            if f not in rec["lock"]:
                rec["lock"][f] = v
            elif rec["lock"][f] != v and not any(c["field"] == f and c["now"] == v for c in rec.get("changed", [])):
                rec.setdefault("changed", []).append({"field": f, "was": rec["lock"][f], "now": v, "seen": seen})
        stage = r.get("stage")
        if stage in FINAL or stage == "expired" or r.get("expired"):
            if "result_seen" not in rec:
                rec["result_seen"] = seen
                rec["result"] = {k: r.get(k) for k in ("stage", "exit", "resultPts", "resolvedAt")}
                if r.get("expired") and not stage:
                    rec["result"]["stage"] = "expired"
        elif r.get("state") in ("orders", "signal") and "result_seen" not in rec:
            rec.setdefault("open_seen", seen)          # seen while the trade or orders were still live
        if r.get("note") and r.get("state") == "none":
            rec["note"] = r["note"]
    store["last_seen"] = seen
    store["source"] = SOURCE
    return store


def status(rec):
    if rec.get("changed"):
        return "altered"
    lock, res = rec.get("lock", {}), rec.get("result") or {}
    if rec.get("state") == "none" and not res:
        return "no_trade"
    if res.get("stage") == "expired":
        return "expired"
    if res.get("stage") not in FINAL:
        return "pending"
    if not rec.get("open_seen") or rec["open_seen"] >= rec["result_seen"]:
        return "unwitnessed"
    return "counted" if lag_minutes(rec) <= 0 else "late_lock"


def lag_minutes(rec):
    """Minutes from the entry to the lock (0 or less: locked before entry). Orders locked before their fill: 0."""
    lock = rec.get("lock", {})
    locked = lock.get("lockedAt") or ""
    if lock.get("filledAt") and lock["filledAt"] > locked:
        return 0
    try:
        hh, mm = (lock.get("at") or "").split(":")
        return (int(locked[11:13]) * 60 + int(locked[14:16])) - (int(hh) * 60 + int(mm))
    except ValueError:
        return 10 ** 6                          # no entry minute published: treated as late


def r_multiple(rec):
    lock, pts = rec.get("lock", {}), (rec.get("result") or {}).get("resultPts")
    risk = abs((lock.get("entry") or 0) - (lock.get("stop") or 0))
    return round(pts / risk, 3) if pts is not None and risk > 0 else None


def metrics(recs, status="counted"):
    done = [r for r in recs if r["status"] == status]
    pts = [r["result"]["resultPts"] for r in done]
    rs = [r["r"] for r in done if r["r"] is not None]
    out = {"trades": len(done), "wins": sum(p > 0 for p in pts), "points": round(sum(pts), 2),
           "mean_points": round(sum(pts) / len(pts), 2) if pts else None,
           "mean_r": round(sum(rs) / len(rs), 3) if rs else None}
    out["verdict"] = (f"{len(done)} of {MIN_TRADES} counted trades: too few to judge" if len(done) < MIN_TRADES
                      else "enough counted trades to judge the average; see the mean R and its spread")
    return out


def late_metrics(recs):
    out = metrics(recs, "late_lock")
    lags = sorted(r["lag"] for r in recs if r["status"] == "late_lock")
    out["median_lag_minutes"] = lags[len(lags) // 2] if lags else None
    del out["verdict"]
    return out


def report(store, now):
    rows = []
    for rec in store.get("records", {}).values():
        r = dict(rec)
        r["status"] = status(rec)
        r["r"] = r_multiple(rec)
        r["lag"] = lag_minutes(rec) if r["status"] in ("counted", "late_lock") else None
        rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    by = {}
    for r in rows:
        by.setdefault(r["id"], []).append(r)
    strategies = {sid: {"name": rs[0]["name"], "counts": {s: sum(x["status"] == s for x in rs) for s in STATUSES},
                        **metrics(rs), "late": late_metrics(rs)} for sid, rs in sorted(by.items())}
    return {"version": 1, "asof": now.isoformat(timespec="seconds"), "since": SINCE, "source": SOURCE,
            "witness": "https://github.com/grobentham/displace/commits/witness", "last_seen": store.get("last_seen"),
            "policy": ("A finished trade counts only if it was locked before entry, Displace saw it live before the "
                       "result, and its locked levels never changed. Trades locked after their entry minute are "
                       "scored separately, with the lag, because a follower could not have had that entry. Results "
                       f"in NQ points and R (points / locked risk), before costs. Fewer than {MIN_TRADES} counted "
                       "trades: no claim either way."),
            "strategies": strategies, "records": rows,
            "limitations": ["The witness reads every 10 minutes from 09:20 to 13:00 New York, then hourly to 17:00; "
                            "a trade that starts and finishes between two readings is unwitnessed, not counted.",
                            "Lock and fill times are Iron Brain's own clock; the witness proves only that a decision "
                            "was public no later than the commit that recorded it.",
                            "Points are before commissions and slippage. Trading rules are private; the ledger "
                            "shows decisions and results, not the rules."]}


def fetch(url=SOURCE, timeout=20):
    with urllib.request.urlopen(url + "?t=" + str(int(dt.datetime.now().timestamp())), timeout=timeout) as fh:
        doc = json.load(fh)
    return ((doc.get("lab") or {}).get("plan") or {}).get("locked") or []


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "records": {}}


def write(path, doc):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True, allow_nan=False)
    os.replace(tmp, path)


def main(argv):
    now = dt.datetime.now(dt.timezone.utc)
    if len(argv) >= 2 and argv[0] == "witness":
        try:
            rows = fetch()
        except Exception as e:                # the published desk is unreachable: record nothing, try next time
            print(f"intraday: desk unreachable ({e!r}); nothing recorded")
            return 0
        write(argv[1], observe(load(argv[1]), rows, now))
        print(f"intraday: saw {len(rows)} published decisions")
        return 0
    if len(argv) >= 3 and argv[0] == "report":
        doc = report(load(argv[1]), now)
        write(argv[2], doc)
        print("intraday:", {k: v["counts"] for k, v in doc["strategies"].items()} or "nothing witnessed yet")
        return 0
    print("usage: intraday.py witness STORE | report STORE OUT")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
