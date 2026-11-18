"""Model v4 on simulated markets where the truth is known.

World: inflation surprises push gold down in the first 2 hours (strongly) but not at the close; labor surprises
move the 2-year yield up at the close; nothing else matters; the Nasdaq drifts up 55% of days regardless.
The model must prove the real rules in the right direction, prove nothing in noise, not mistake the Nasdaq's
drift for a news edge, and state honest probabilities."""
import datetime as dt
import random
from zoneinfo import ZoneInfo

import surprise as S

NY = ZoneInfo("America/New_York")


def world(seed, effect=0.9):
    rnd = random.Random(seed)
    rels = []
    d = dt.datetime(2010, 1, 4, 8, 30, tzinfo=NY)
    hourly, daily = [], {k: [] for k in ("gold", "nq", "usd", "y2")}
    levels = {"gold": 1000.0, "nq": 2000.0, "usd": 100.0, "y2": 2.0}
    kinds = ["cpi", "nfp", "retail", "umich", "homes"]
    while d < dt.datetime(2026, 11, 1, tzinfo=NY):
        if d.weekday() < 5:
            k = rnd.choice(kinds) if rnd.random() < 0.6 else None
            z = rnd.gauss(0, 1) if k else 0.0
            if k:
                rels.append({"when": d, "kind": k, "group": S.tv.GROUP_OF[k], "z": z, "comps": []})
            for a in levels:
                r = rnd.gauss(0, 0.8)
                if a == "y2" and k == "nfp":
                    r += 0.5 * effect * z
                if a == "nq":
                    r += 0.1  # drift up, nothing to do with the news
                levels[a] = levels[a] + r / 100 if a == "y2" else levels[a] * (1 + r / 100)
                daily[a].append((d.date().isoformat(), levels[a]))
            if d.year >= 2024:  # hourly gold bars around the release
                o = levels["gold"]
                c = o * (1 + (rnd.gauss(0, 0.3) - (effect * 0.4 * z if k == "cpi" else 0)) / 100)
                s = d.replace(minute=0)
                hourly += [(s, o, o, o, o), (s + dt.timedelta(hours=1), c, c, c, c)]
        d += dt.timedelta(days=1)
    markets = {"gold2h": S.Hourly(hourly, dt.datetime(2026, 11, 18, tzinfo=NY))}
    markets.update({a: S.Daily(rows, "bp" if a == "y2" else "pct") for a, rows in daily.items()})
    return rels, markets


def main():
    rels, markets = world(1)
    m = S.fit(rels, markets, dt.datetime(2026, 11, 18, tzinfo=NY))
    G = m["groups"]
    show = {g: {k: (v["bt"]["hits"], v["bt"]["calls"], v["proven"]) for k, v in d.items()} for g, d in G.items()}
    print(show)
    assert G["inflation"]["gold2h"]["proven"] and G["inflation"]["gold2h"]["b"] < 0, G["inflation"]["gold2h"]
    assert G["labor"]["y2"]["proven"] and G["labor"]["y2"]["b"] > 0
    assert not G["labor"]["nq"]["proven"] and not G["inflation"]["nq"]["proven"], "drift taken for an edge"
    wrong = [(g, k) for g, d in G.items() for k, v in d.items() if v["proven"] and (g, k) not in (("inflation", "gold2h"), ("labor", "y2"))]
    assert not wrong, wrong
    c = S.call(m, "inflation", "gold2h", 1.0)
    assert c["dir"] == "down" and 0.55 < c["p"] < 0.9, c
    assert S.call(m, "inflation", "gold2h", -1.0)["dir"] == "up"
    assert S.call(m, "sentiment", "gold", 1.0).get("none")
    sc = m["scenarios"]["cpi"]["assets"]["gold2h"]
    assert sc["hot"]["up"] < 0.4 < 0.6 < sc["cool"]["up"], sc
    # pure noise: nothing proven
    rels, markets = world(2, effect=0.0)
    m = S.fit(rels, markets, dt.datetime(2026, 11, 18, tzinfo=NY))
    proven = [(g, k) for g, d in m["groups"].items() for k, v in d.items() if v["proven"]]
    assert not proven, proven
    # scoring waits for the 2-hour window to close
    log = [{"asset": "gold2h", "when": "2026-10-01T08:30:00-04:00", "dir": "down"}]
    S.score(log, {"gold2h": S.Hourly([], dt.datetime(2026, 10, 1, 9, tzinfo=NY))}, None)
    assert "hit" not in log[0]
    print("surprise tests passed")


if __name__ == "__main__":
    main()
