"""Expected-move model on simulated markets where the truth is known: CPI days move 1.8x a normal day,
claims days move like any other day, and volatility drifts through calm and stressed regimes."""
import datetime as dt
import math
import random

import moves as M


def world(seed, cpi_mult=1.8):
    rnd = random.Random(seed)
    d, rows, c = dt.date(2008, 1, 2), [], 100.0
    cpi, claims = [], []
    while d < dt.date(2026, 11, 18):
        if d.weekday() < 5:
            vol = 1.0 + 0.8 * math.sin(len(rows) / 400)  # regimes
            iso = d.isoformat()
            mult = 1.0
            if d.day in range(10, 15) and not any(x[:7] == iso[:7] for x in cpi) and d.weekday() < 4:
                cpi.append(iso)
                mult = cpi_mult
            if d.weekday() == 3:
                claims.append(iso)
            rng = vol * mult * rnd.lognormvariate(0, 0.35)
            o = c
            c = o * (1 + rnd.gauss(0, rng / 250))
            hi, lo = max(o, c) * (1 + rng / 400), min(o, c) * (1 - rng / 400)
            rows.append((iso, hi, lo, c))
        d += dt.timedelta(days=1)
    return rows, {"cpi": cpi, "claims": claims}


def main():
    rows, dates = world(1)
    m = M.fit({"gold": rows}, dates, dt.date(2026, 11, 18))
    cpi, cl = m["kinds"]["cpi"]["gold"], m["kinds"]["claims"]["gold"]
    print("cpi:", {k: cpi[k] for k in ("mult", "lo", "hi", "proven")}, cpi["bt"])
    print("claims:", {k: cl[k] for k in ("mult", "proven", "why")}, cl["bt"])
    assert 1.5 < cpi["mult"] < 2.2 and cpi["proven"], cpi
    assert 0.85 < cl["mult"] < 1.15 and not cl["proven"], cl
    assert 0.7 <= cpi["bt"]["coverage"] <= 0.9
    ev = M.for_event(m, "cpi")["gold"]
    assert abs(ev["pct"] - m["markets"]["gold"]["baseline"] * cpi["mult"]) < 0.02 and ev["pts"] > 0, ev
    # no effect anywhere: nothing proven
    rows, dates = world(2, cpi_mult=1.0)
    m = M.fit({"gold": rows}, dates, dt.date(2026, 11, 18))
    assert not m["kinds"]["cpi"]["gold"]["proven"], m["kinds"]["cpi"]["gold"]
    # gap days: a jump between closes counts even when the day's own high-low is tiny
    tr = M.true_ranges([("a", 101, 99, 100), ("b", 110.5, 110, 110)])
    assert abs(tr["b"] - 10.5) < 1e-9
    print("moves tests passed")


if __name__ == "__main__":
    main()
