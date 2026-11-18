import sys, time, datetime as dt
sys.path.insert(0, "engine")
import series_store as S, prices
src = S.Public()
for sid, mode in (("CPILFESL", "pct"), ("PAYEMS", "diff"), ("ICSA", "level")):
    t = time.time(); v = src.vintages(sid); print(f"LIVE {sid} vintages {len(v)} {v[:2]}..{v[-2:]} {time.time()-t:.1f}s")
    rows = []
    t = time.time()
    for x in [y for y in v if y >= "2026-06-01"]:
        snap = src.snapshot(sid, x, (dt.date.fromisoformat(x) - dt.timedelta(days=420)).isoformat())
        S.chain(rows, x, snap, mode)
    print(f"LIVE {sid} chained {len(rows)} in {time.time()-t:.1f}s")
    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        ch = (b[1] / a[1] - 1) * 100 if mode == "pct" else b[1] - a[1] if mode == "diff" else b[1]
        print(f"LIVE   {b[0]} published {b[2]} -> {ch:.3f}")
d = src.daily("DFF", "2026-11-01"); print("LIVE DFF", d[-2:])
d = src.daily("DTWEXBGS", "2026-11-01"); print("LIVE DTWEXBGS", d[-2:])
for m in ("gold", "nq"):
    r, s = prices.closes(m, "2026-11-01"); print("LIVE", m, s, r[-2:] if r else None)
