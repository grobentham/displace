# Displace

ICT trading education site with an economic calendar and a news engine that keeps it up to date on its own. Free to run: the site is hosted on GitHub Pages, and the engine runs in GitHub Actions.

Everything here is education. The engine never writes trade signals, entries, targets or predictions.

## What's in here

| Path | What it is |
|---|---|
| `site/index.html` | The whole website (one file). |
| `site/data/` | Data the site reads. **Written by the engine. Don't edit by hand**, except as noted below. |
| `engine/engine.py` | Calendar, figures, and briefs (Python, no extra packages). |
| `engine/publicdata.py` | Public FRED calendars and CSV downloads, plus dated ALFRED snapshots. |
| `engine/agencies.py` | Keyless direct data from BLS, Census, BEA, Treasury, and the New York Fed. |
| `engine/news.py` | Latest economic news from confirmed releases and central-bank feeds. |
| `engine/schedule.json` | Release dates the engine knows about. **You add new dates here.** |
| `engine/earnings_seed.json` | Earnings dates a company has announced itself (optional). The engine also reads Nasdaq's public earnings calendar for 24 Nasdaq-100 names and merges both into `site/data/calendar/earnings.json`. A company's own date always wins. |
| `engine/forecasts.json` | Economists' consensus forecasts you enter by hand (optional). |
| `engine/manual.json` | Optional notes for the Fed tracker (market pricing, Fed commentary). |
| `.github/workflows/engine.yml` | Runs the engine on a schedule and publishes the site. |

## What the engine does

GitHub Actions checks sources around the New York release windows on weekdays and refreshes the weekly outlook on Sunday. Public downloads and RSS feeds require zero API keys. Text is generated with fixed templates.

**Latest economic news.** The News page shows source-linked policy announcements from the Federal Reserve, European Central Bank, and Bank of England, plus confirmed economic releases. The digest explains what each release measures and compares reported figures with previous readings and any recorded consensus. The page shows when the feeds were checked and identifies temporarily unavailable feeds.

**Calendar that maintains itself**
- Release dates come from the BEA calendar for GDP and PCE, and public FRED release calendars for:
  - CPI, PPI, jobs, retail sales, jobless claims and JOLTS
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

The engine checks the reported period against ALFRED snapshots when the archives are available. It can also check the direct BLS series and the dated Census or BEA releases. The event details show the source and the archive, publication, or verification date.

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

Each available series shows changes and a sparkline. Treasury yields and the effective federal funds rate can refresh directly from Treasury and the New York Fed when FRED is unavailable.

**Briefs.** The engine writes:
- **Daily brief:** latest close, today's releases with forecast and previous, anything just released, and what's in focus.
- **Weekly outlook**
- **Fed tracker:** rate, last move, days to the next decision, and where the 2-year sits against the policy rate.

**Calendar feeds.** `calendar.ics` (all releases) and `calendar-high.ics` (high impact), with 15-minute alerts, to subscribe to in Google, Apple or Outlook Calendar.

**Quality control.** Nothing is published without passing these checks.
- **Plausibility:** every figure must fall inside a hard range for its series (core CPI m/m between −1.5% and 2%, jobless claims between 100K and 1.5M, and so on). Anything outside is rejected and never published.
- **Confirmation:** a figure that's possible but extreme for its own history (more than 6 robust standard deviations from normal, for example −900K payrolls) is held until a later run sees the same number again. One bad data pull can't go live.
- **Freshness:** a figure must match the reported period and be available after the scheduled publication. Archived data also receives a before-and-after check.
- **Text:** every generated sentence is checked for template errors and trade-call language ("buy", "you should", "will rise"). Failing text is dropped.
- **Structure:** unique ids, valid dates and times, no weekend releases, no duplicates, no actuals on future dates, at least five weeks of calendar ahead, stats rows valid, market data in range and fresh (stale tiles are marked), reaction stats only shown with 6+ release days.
- **Last good data:** if a critical check fails, the last good file stays live and a GitHub issue titled "Engine quality check failed" opens.
- **Source stamp:** the site shows the series and the date of the archived observation snapshot.
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
2. **Publish the site:** **Actions → Engine → Run workflow**. Subsequent scheduled runs refresh the data and deploy the site at `https://<your-username>.github.io/displace/`.

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
python engine/test_public_news.py
python engine/test_earnings.py
python engine/test_direction.py
```

The historical research module in `engine/direction.py` has its own offline tests. The scheduled workflow publishes release facts and historical reaction statistics.
