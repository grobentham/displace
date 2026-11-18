# Displace

ICT trading education site with an economic calendar and a news engine that keeps it up to date on its own. Free to run: the site is hosted on GitHub Pages, and the engine runs in GitHub Actions.

Everything here is education. The engine never writes trade signals, entries, targets or predictions.

## What's in here

| Path | What it is |
|---|---|
| `site/index.html` | The whole website (one file). |
| `site/data/` | Data the site reads. **Written by the engine. Don't edit by hand**, except as noted below. |
| `engine/engine.py` | The news engine (Python, no extra packages). |
| `engine/schedule.json` | Release dates the engine knows about. **You add new dates here.** |
| `engine/earnings_seed.json` | Earnings dates a company has announced itself (optional). The engine also reads Nasdaq's public earnings calendar for 24 Nasdaq-100 names and merges both into `site/data/calendar/earnings.json`. A company's own date always wins. |
| `engine/forecasts.json` | Economists' consensus forecasts you enter by hand (optional). |
| `engine/manual.json` | Optional notes for the Fed tracker (market pricing, Fed commentary). |
| `.github/workflows/engine.yml` | Runs the engine on a schedule and publishes the site. |

## What the engine does

It runs on weekdays around each New York release window, plus Sunday evening. No AI: everything comes from official data and fixed templates.

**Calendar that maintains itself**
- Release dates come from the official release calendars on FRED for:
  - CPI, PPI, jobs, retail sales, GDP, PCE, jobless claims and JOLTS
  - UMich, durable goods, new home sales, ADP and Fed decisions
- These are worked out by rule:
  - NYSE holidays and 13:00 early closes
  - ISM (first and third business day)
  - Conference Board (last Tuesday)
  - FOMC minutes (three weeks after each decision)
  - Beige Book (two weeks before)
- If an agency moves a date, the calendar follows.
- `engine/schedule.json` is only for extras (ECB, BoE) and corrections.

**Full detail for every release.** Previous before the release, actual after it, for example:
- CPI: core m/m, headline m/m, core y/y, headline y/y
- Jobs: payrolls, unemployment rate and wages
- PCE: core and headline, spending and income
- Jobless claims: initial claims, 4-week average and continuing claims

A figure only counts as released if FRED published it on or after release day, so last month's number is never mistaken for the new one.

**Analysis.** Each new number gets plain-English facts, for example:
- "The core CPI m/m reading was the highest since Apr 2026."
- "It has picked up 4 months in a row."
- "That's higher than 90% of readings over the past five years."

Each also gets a recap and goes into the 12-month release stats.

**Release-day market moves.** For CPI, jobs, PCE, retail sales, PPI, GDP, the Fed and claims, it measures how much the 2-year yield, 10-year yield and the dollar moved on each of the last 12 release days. It compares that with an average day ("CPI days move the 2-year 2.1× a normal day").

**Macro pulse.** Covers:
- 2-year and 10-year yields and the curve
- breakeven inflation and the real yield
- the effective fed funds rate and the dollar
- WTI oil, Chicago Fed financial conditions and mortgage rates

Each shows 1-day, 1-week and 1-month moves and a sparkline chart. All are public-domain Fed, Treasury and EIA series.

**Briefs.** The engine writes:
- **Daily brief:** latest close, today's releases with forecast and previous, anything just released, and what's in focus.
- **Weekly outlook**
- **Fed tracker:** rate, last move, days to the next decision, and where the 2-year sits against the policy rate.

**Calendar feeds.** `calendar.ics` (all releases) and `calendar-high.ics` (high impact), with 15-minute alerts, to subscribe to in Google, Apple or Outlook Calendar.

**Quality control.** Nothing is published without passing these checks.
- **Plausibility:** every figure must fall inside a hard range for its series (core CPI m/m between −1.5% and 2%, jobless claims between 100K and 1.5M, and so on). Anything outside is rejected and never published.
- **Confirmation:** a figure that's possible but extreme for its own history (more than 6 robust standard deviations from normal, for example −900K payrolls) is held until a later run sees the same number again. One bad data pull can't go live.
- **Freshness:** an actual only counts if FRED published it on or after release day.
- **Text:** every generated sentence is checked for template errors and trade-call language ("buy", "you should", "will rise"). Failing text is dropped.
- **Structure:** unique ids, valid dates and times, no weekend releases, no duplicates, no actuals on future dates, at least five weeks of calendar ahead, stats rows valid, market data in range and fresh (stale tiles are marked), reaction stats only shown with 6+ release days.
- **Last good data:** if a critical check fails, the last good file stays live and a GitHub issue titled "Engine quality check failed" opens.
- **Source stamp:** each actual records which FRED series it came from and when it was published, and the site shows this.
- **Report:** `site/data/engine/quality.json` lists every check, rejection and held figure. The site shows "quality checks N/N passed".

Known limitation: percent changes (CPI, PCE, retail sales…) are calculated from the published index levels, so very occasionally one can differ by 0.1 from the agency's own rounded figure.

**Self-monitoring**
- `site/data/engine/status.json` records every run, any FRED errors and how far ahead the calendar goes.
- The site shows when the engine last ran.
- A GitHub issue opens if the calendar runs short.

Not covered automatically, because the data isn't free to republish:
- consensus forecasts
- ISM and Conference Board values
- intraday prices

Add forecasts by hand if you want them (see below).

## One-time setup

1. **Turn on Pages:** repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Publish the site:** **Actions → Publish Displace → Run workflow**. The site appears at `https://<your-username>.github.io/displace/` with the bundled data.

To start refreshing data, get a FRED key from **My Account → API Keys** at https://fred.stlouisfed.org. In **Settings → Secrets and variables → Actions**, add the key as the repository secret `FRED_API_KEY` and set the repository variable `DISPLACE_ENGINE_ENABLED` to `true`. Then go to **Actions → Engine → Run workflow**. The Engine workflow will take over publishing from that point.

## Day-to-day

- **Extra or corrected dates.** The calendar fills itself from FRED. For anything else (ECB, BoE, a one-off change), add lines to `engine/schedule.json`:
  ```json
  {"date": "2027-03-05", "time": "08:30", "title": "Non-farm payrolls · Employment situation (Feb)", "cur": "USD", "impact": "high", "src": "BLS", "note": "Lands an hour before the 9:30 open."}
  ```
  - Put the month in brackets in the title, like `(Feb)`, or the quarter for GDP, like `(Q1)`. The engine uses it to find the right figure.
  - Holidays use `"time": ""` and `"impact": "holiday"`.
- **Forecasts (optional).** Find the event's `id` in `site/data/calendar/events.json`, then add it to `engine/forecasts.json`:
  ```json
  {"forecasts": {"20261210-cpi-inflation-nov": {"forecast": "0.3%", "fsrc": "Reuters poll"}}}
  ```
- **Fed notes (optional).** Fill `fedPricing` / `fedWatch` in `engine/manual.json`, with the date you wrote them.
- **Run now.** Go to **Actions → Engine → Run workflow**.

You can edit any of these files straight on github.com. Committing a change runs the engine and republishes the site.

## Pro

`site/data/config/site.json` has `"proOpen": true`, which unlocks every Pro feature for everyone during launch. Paid accounts need a login and payment backend (for example Supabase and Stripe); that's the next step.

## Test

```
python engine/test_engine.py
```

## Direction engine (v2)

`engine/direction.py` decides which way gold, the dollar, EUR/USD, the Nasdaq 100 and the 2- and 10-year yields tend to close on release day. The full method is at the top of the file. In short:

- **Surprise score:** headline plus key components (core and headline CPI; payrolls, unemployment and wages; and so on), from first-published FRED/ALFRED figures since 2010, against consensus where recorded, otherwise the trend.
- **Market regime:** Fed hiking, cutting or on hold, inflation above or below 3%, and each market's 5-day trend. Days with another big release count half.
- **Two models:** a tally by surprise bucket and a regularised logistic regression, blended by whichever predicted better on unseen data. Probabilities are calibrated against the model's own out-of-sample record.
- **Proof gate:** at least 30 out-of-sample calls; a hit rate of 55% or more; significant after a false-discovery-rate correction across all rules; better than a coin flip on probability accuracy; worked in both halves of history; markets clearly respond to the surprise; and still right on its latest 20 calls (circuit breaker).
- **Live scoring:** live calls are logged in `engine/direction_log.json`, scored at the close, and fed back into the circuit breaker.
- **Tests** (`engine/test_direction.py`, run before every engine run): finds real effects in the right direction, finds 0 of 96 rules in pure-noise worlds, picks up regime-only effects, keeps stated probabilities close to realised ones, and switches off a rule that stops working.
