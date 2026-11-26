"""Publish current ES and XAUUSD context on Displace's dedicated data branch."""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import es_outlook as es
from gold_sessions import fetch_sessions
from spot_outlook import xauusd_outlook


def market_time(record):
    try:
        value = dt.datetime.fromisoformat(record["barTime"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    return value if value.tzinfo is not None else None


def refresh(previous, loaders, now, log=print):
    markets = {key: previous.get("markets", {}).get(key) for key in loaders}
    markets = {key: value for key, value in markets.items() if value and market_time(value)}
    for key, load in loaders.items():
        try:
            new = load()
            published = market_time(new) if new else None
            earlier = market_time(markets[key]) if key in markets else None
            if published and published <= now and (earlier is None or published > earlier):
                markets[key] = new
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            log(f"{key} outlook temporarily unavailable ({type(error).__name__}).")
    return markets


def publish(path, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    loaders = {"es": lambda: es.outlook(es.bars(), now), "xauusd": lambda: xauusd_outlook(now=now)}
    markets = refresh(previous, loaders, now)
    sessions = previous.get("sessions", {})
    try:
        candles = fetch_sessions()
        if candles:
            sessions = {"gold": {**sessions.get("gold", {}), **candles}}
            ordered = sorted(sessions["gold"])[-8:]
            sessions["gold"] = {key: sessions["gold"][key] for key in ordered}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        print("Gold session candles temporarily unavailable.")
    document = {"markets": markets, "sessions": sessions}
    if document != previous and (markets or sessions):
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
    print("Displace outlook coverage: " + ", ".join(sorted(markets)))


if __name__ == "__main__":
    publish(Path(sys.argv[1]))
