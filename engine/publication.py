"""Conservative public availability receipts from successful Pages deployment.
A receipt is written only after deployment succeeds, then consumed on the next run.
Old records without receipts are not credited as prospective forecasts.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import exchange

FIELDS = ("market", "candle", "for", "logged", "bias", "tier", "p_up", "base_up",
          "p_high", "p_low", "range_lo", "range_hi", "up1", "dn1", "p_up1", "p_dn1")
ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "site/data/bias/log.json"
RECEIPTS = ROOT / "site/data/bias/publication-receipts.json"


def cutoff(row):
    """Use the same session open as the outlook, including multi-day holiday sessions."""
    session = exchange.session(row["market"], row["for"])
    if not session:
        raise ValueError("Forecast target has no exchange session")
    return session["open"]


def forecast_values(view):
    touch = next((level for level in view["touch"] if level["k"] == 1.0), {})
    return {**{key: view[key] for key in ("bias", "tier", "p_up", "base_up")},
            "p_high": view["takes"]["high"]["p"], "p_low": view["takes"]["low"]["p"],
            "range_lo": view["range"]["lo"], "range_hi": view["range"]["hi"],
            "up1": touch.get("up"), "dn1": touch.get("dn"),
            "p_up1": touch.get("up_p"), "p_dn1": touch.get("dn_p"),
            "range_points": view["range"]["points"], "prior_levels": view["levels"]}


def matches(row, view):
    if not view or row.get("void") or row["candle"] != view.get("candle"):
        return False
    session = view.get("session") or {}
    if session.get("date") != row["for"] or dt.datetime.fromisoformat(session["open"]) != cutoff(row):
        return False
    return all(row[key] == value for key, value in forecast_values(view).items() if key in row)


def identity(row):
    payload = {k: row.get(k) for k in FIELDS}
    for key in ("range_points", "prior_levels"):
        if key in row:
            payload[key] = row[key]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def load(path=RECEIPTS):
    if not path.exists():
        return {}
    return json.loads(path.read_text())["receipts"]

def record(rows, existing, published, run):
    if published.tzinfo is None or not run:
        raise ValueError("deployment timestamp and run required")
    for row in rows:
        if not row.get("void") and row.get("eligible") is True:
            existing.setdefault(identity(row), {"published_at": published.isoformat(), "run": run})
    return existing

def verified(row, receipts, cutoff):
    if row.get("eligible") is not True or row.get("void"):
        return False
    try:
        stamp = dt.datetime.fromisoformat(receipts[identity(row)]["published_at"])
        generated = dt.datetime.fromisoformat(row["logged"])
        return generated <= stamp < cutoff
    except (KeyError, ValueError, TypeError):
        return False

def main():
    if not os.environ.get("GITHUB_RUN_ID"):
        raise RuntimeError("Only the successful deployment workflow may write receipts")
    rows = json.loads(LOG.read_text())["entries"]
    out = record(rows, load(), dt.datetime.now(dt.timezone.utc), os.environ["GITHUB_RUN_ID"])
    tmp = RECEIPTS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "receipts": out}, sort_keys=True, separators=(",", ":")))
    os.replace(tmp, RECEIPTS)

if __name__ == "__main__":
    main()
