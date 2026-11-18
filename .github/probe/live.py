import urllib.request, lzma, time, datetime as dt
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36", "Accept": "*/*"}
def get(u, tries=6):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40); return 200, r.read(), i
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, b"", i
            time.sleep(min(30, 3 * 2 ** i))
        except Exception:
            time.sleep(min(30, 3 * 2 ** i))
    return 503, b"", tries
days = [dt.date(2015, 1, 16) + dt.timedelta(days=37 * i) for i in range(14)]
ok = 0; t0 = time.time()
for inst in ("XAUUSD", "USATECHIDXUSD"):
    for d in days:
        if d.weekday() >= 5: continue
        u = f"https://datafeed.dukascopy.com/datafeed/{inst}/{d.year}/{d.month-1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
        s, b, tries = get(u)
        n = len(lzma.decompress(b)) // 24 if s == 200 and b else 0
        ok += s == 200
        print(f"LIVE {inst} {d} {s} after {tries} retries, {n} candles, t={time.time()-t0:.0f}s")
        time.sleep(2)
print("LIVE ok", ok)
