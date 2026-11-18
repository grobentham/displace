import urllib.request, time, json
def get(u, h=None):
    hd = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
    hd.update(h or {})
    for i in range(2):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers=hd), timeout=40); return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()[:300]
        except Exception as e: err = e; time.sleep(2)
    return "ERR", repr(err).encode()
tv = {"Origin": "https://www.tradingview.com", "Referer": "https://www.tradingview.com/"}
for k, u, h in [
  ("tv_2015", "https://economic-calendar.tradingview.com/events?from=2015-01-13T00:00:00.000Z&to=2015-01-17T00:00:00.000Z&countries=US", tv),
  ("tv_2024", "https://economic-calendar.tradingview.com/events?from=2024-03-11T00:00:00.000Z&to=2024-03-16T00:00:00.000Z&countries=US", tv),
  ("tv_2010", "https://economic-calendar.tradingview.com/events?from=2010-01-11T00:00:00.000Z&to=2010-01-16T00:00:00.000Z&countries=US", tv),
  ("ff_lastweek", "https://nfs.faireconomy.media/ff_calendar_lastweek.json", None),
  ("ff_html_2020", "https://www.forexfactory.com/calendar?week=jan12.2020", None),
  ("fxstreet", "https://calendar-api.fxstreet.com/en/api/v1/eventDates/2024-03-11T00:00:00Z/2024-03-16T00:00:00Z?countries=US&volatilities=HIGH", None),
  ("investing", "https://www.investing.com/economic-calendar/cpi-733", None),
]:
    s, b = get(u, h)
    print(f"LIVE {k} {s} {len(b)}B :: {b[:200]!r}")
    if k.startswith("tv") and s == 200:
        try:
            d = json.loads(b); r = d.get("result", d)
            print(f"LIVE   {k} events {len(r)}")
            for e in r:
                if any(x in (e.get('title') or '') for x in ("CPI", "Nonfarm", "Non Farm", "Retail Sales", "Jobless", "PCE")):
                    print("LIVE    ", e.get("date"), "|", e.get("title"), "| actual", e.get("actual"), "| forecast", e.get("forecast"), "| prev", e.get("previous"), "| unit", e.get("unit"), e.get("scale"))
        except Exception as ex: print("LIVE   parse", repr(ex))
