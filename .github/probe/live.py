import urllib.request, time, json, collections
tv = {"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
def get(f, t):
    u = f"https://economic-calendar.tradingview.com/events?from={f}T00:00:00.000Z&to={t}T00:00:00.000Z&countries=US"
    for i in range(3):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=tv), timeout=40).read())["result"]
        except Exception as e: err = e; time.sleep(3)
    raise err
cnt = collections.Counter(); ex = {}
t0 = time.time()
for f, t in (("2023-01-01", "2023-02-01"), ("2023-02-01", "2023-03-01"), ("2019-05-01", "2019-06-01"), ("2026-10-01", "2026-11-19")):
    for e in get(f, t):
        if e.get("forecast") is not None or e.get("importance", 0) >= 0:
            key = e["title"]; cnt[key] += 1
            ex.setdefault(key, (e["date"], e.get("actual"), e.get("forecast"), e.get("previous"), e.get("unit"), e.get("scale"), e.get("importance"), e.get("period"), e.get("referenceDate")))
print("LIVE seconds", round(time.time() - t0, 1), "keys example", list(get("2026-11-10", "2026-11-11")[0].keys()))
for k, v in sorted(ex.items()):
    if v[2] is not None:
        print("LIVE", repr(k), "x", cnt[k], "::", v)
