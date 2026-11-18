import urllib.request, lzma, struct, time, datetime as dt
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
def get(u):
    for i in range(3):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40); return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, b""
        except Exception as e: err = e; time.sleep(2)
    return "ERR " + repr(err), b""
for inst in ("XAUUSD", "USATECHIDXUSD", "USA100IDXUSD", "NAS100"):
    for day in (dt.date(2015, 1, 16), dt.date(2026, 11, 12)):
        u = f"https://datafeed.dukascopy.com/datafeed/{inst}/{day.year}/{day.month-1:02d}/{day.day:02d}/BID_candles_min_1.bi5"
        t = time.time(); s, b = get(u)
        print(f"LIVE {inst} {day} status {s} {len(b)}B {time.time()-t:.1f}s")
        if s == 200 and b:
            try:
                raw = lzma.decompress(b)
                n = len(raw) // 24
                rows = [struct.unpack(">5if", raw[i*24:(i+1)*24]) for i in range(n)]
                print(f"LIVE   {n} minute candles; first {rows[0]}")
                for r in rows:
                    if 13*3600 + 25*60 <= r[0] <= 13*3600 + 40*60: print("LIVE    ", dt.timedelta(seconds=r[0]), r)
            except Exception as e: print("LIVE   decode", repr(e))
