"""Contract roll days in Yahoo's continuous futures series.

Yahoo's NQ=F, GC=F and similar series stitch one contract to the next. On the day it switches, the move from the
previous close is partly the price difference between the two contracts (carry: the next contract trades higher
when rates exceed dividends), not market movement. Measured on 2016-2026 daily candles (24 Nov 2026), the average
open gap on the switch day versus normal days:

    NQ, ES, YM, RTY   first session after the 3rd Friday of Mar/Jun/Sep/Dec   NQ +0.41% (t 4.1); ES/YM/RTY ~0.1%
    gold              first session of Feb/Apr/Jun/Aug/Oct/Dec                +0.42% (t 5.6)
    euro FX           Monday of the quarterly expiry week (two sessions before the 3rd Wednesday)   +0.21% (t 6.9)
    crude, bitcoin    monthly rolls whose jump changes sign: no reliable day found, so not flagged (a known limit)

Free data has no per-contract history, so the jump can't be measured roll by roll and removed. Instead the research
leaves the switch day's outcome out wherever it compares the day with the one before (up or down, took the previous
high or low, reached close +/- k sigma). Ranges, which come from one contract, are kept.
"""
import datetime as dt

import exchange as X

QUARTER = (3, 6, 9, 12)
GOLD_MONTHS = (2, 4, 6, 8, 10, 12)
RULE = {"nq": "equity", "es": "equity", "ym": "equity", "rty": "equity", "gold": "gold", "6e": "fx"}


def _third(y, m, wd):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(wd - d.weekday()) % 7 + 14)


def roll_dates(market, years):
    """Switch dates for a market over the given years (empty for markets without a reliable rule)."""
    rule = RULE.get(market)
    out = set()
    for y in years:
        if rule == "equity":
            out |= {X.next_trade_date(_third(y, m, 4)) for m in QUARTER}
        elif rule == "gold":
            out |= {X.next_trade_date(dt.date(y, m, 1) - dt.timedelta(days=1)) for m in GOLD_MONTHS}
        elif rule == "fx":
            out |= {X.prev_trade_date(X.prev_trade_date(_third(y, m, 2))) for m in QUARTER}
    return out


def mask(market, keys):
    """[True if that candle's date is a switch day] for a list of ISO dates."""
    if market not in RULE or not keys:
        return [False] * len(keys)
    years = range(int(keys[0][:4]), int(keys[-1][:4]) + 2)
    days = {d.isoformat() for d in roll_dates(market, years)}
    return [k in days for k in keys]


def is_roll(market, day):
    d = str(day)[:10]
    return d in {x.isoformat() for x in roll_dates(market, [int(d[:4])])}
