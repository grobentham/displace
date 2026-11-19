# Displace

ICT trading education site with an economic calendar and a news engine that keeps it up to date on its own. Free to run: the site is hosted on GitHub Pages, and the engine runs in GitHub Actions.

Everything here is education. The engine never writes entries, targets or trade instructions. The news-outcome engine publishes historical statistics (how markets have closed after past releases) and, only where a rule passed out-of-sample tests, a probability lean with its full public track record.

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
| `engine/predict.py` | News-outcome engine: `tv.py` (consensus surprises), `bars.py` (hourly bars), `surprise.py` (the model), `moves.py` (expected move); writes `site/data/direction/`. |
| `engine/series_store.py`, `engine/prices.py` | Daily rates, dollar, gold and Nasdaq-100 closes, cached in `engine/cache/`. |
| `engine/watch.py` | Opens an issue when a major release's figure hasn't arrived 3 hours after it came out. |
| `engine/forecasts.json` | Economists' consensus forecasts you enter by hand (optional). |
| `engine/manual.json` | Optional notes for the Fed tracker (market pricing, Fed commentary). |
| `.github/workflows/engine.yml` | Runs the engine on a schedule and publishes the site. |

## What the engine does

GitHub Actions checks sources around the New York release windows on weekdays and refreshes the weekly outlook on Sunday. Public downloads and RSS feeds require zero API keys; nothing in this repo needs an account or a secret. Every download retries, because GitHub's runners sometimes take several seconds to look up a host name. Text is generated with fixed templates.

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
- **Daily brief:** a 7 a.m. Singapore edition with the NQ rates outlook, the top upcoming release, issuer-reported earnings figures, and source-linked news. Release details include the figures to watch, recorded forecasts, and confirmed results and revisions. Intraday updates appear alongside the overnight recap.
- **Weekly outlook**
- **Fed tracker:** rate, last move, days to the next decision, and where the 2-year sits against the policy rate.

**Calendar feeds.** `calendar.ics` (all releases) and `calendar-high.ics` (high impact), with 15-minute alerts, to subscribe to in Google, Apple or Outlook Calendar.

**News-outcome engine (gold, NQ, dollar, 2-year yield).** `engine/predict.py` runs after every engine run and writes `site/data/direction/current.json`, which the News calendar shows:
- **Surprise = actual vs consensus.** TradingView's free economic calendar gives every US release since 2010 with the consensus forecast (`engine/tv.py`, cached in `engine/cache/tv/`). Each report's surprise is scaled by its own typical surprise (walk-forward), and reports with several headline figures are combined (CPI core + headline; payrolls, unemployment and wages; ...). 18 reports, pooled into six themes: inflation, labor, activity, sentiment, housing and the Fed. A Fed decision's surprise is the rate against the expected rate in quarter points, and Fed cards also show what gold and NQ did after past hikes, holds and cuts.
- **Three horizons.** The first 15 minutes and the first 2 hours after the release for gold and Nasdaq-100 futures, and the release-day close for gold, the Nasdaq-100, the dollar index and the 2-year yield. Intraday history comes from Yahoo 5-minute and hourly bars, archived in `engine/cache/bars/` so it keeps growing past Yahoo's 60-day and two-year windows. Optional Dukascopy minute history for release times goes in `engine/cache/minutes/dukascopy.json`; Dukascopy blocks cloud servers, so it is fetched from a home PC.
- **Model** (`engine/surprise.py`): per market and theme, P(up) = 0.5 + k (sigmoid(b z) - 0.5). No intercept, so a market's usual drift can never pass as a news edge; k is fitted from the model's own out-of-sample record so probabilities are honest. Splitting the slope by volatility regime and Fed cycle was tested out of sample and did not help (54.5% vs 55.0% of calls right), so it is not used.
- **Proof.** Every release is replayed using only earlier releases. A lean is shown only for market x theme rules right 55%+ of the time over 30+ unseen calls (20+ for the first two hours) that survive a multiple-testing correction, beat a coin flip on calibration, held in both halves of their history and are still working on their latest 20 calls. Everything else shows the scenario map (above / near / below consensus) as the historical record.
- **Public track record:** post-release leans are logged in `site/data/direction/log.json` and scored when their window closes (15 minutes, two hours, or the close). Tested leans and the outlined "not proven" sides (15+ past releases, 60%+ one way, unlikely to be chance) are tracked separately, so you can see whether the outlined ones hold up live. Unfinished bars are never used to train or score.
- **Expected move** (`engine/moves.py`): the day's likely range for gold and NQ, scaled to recent volatility.

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
- A GitHub issue opens if the calendar runs short, or if a major release's figure hasn't arrived 3 hours after it came out.

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
python engine/test_surprise.py
python engine/test_predict.py
python engine/test_sources.py
```

`test_surprise.py` checks the model on simulated markets where the truth is known (it must find real effects, find nothing in noise and state honest probabilities). `test_predict.py` runs the whole news-outcome pipeline offline.

### Bias of the day (`engine/bias.py`)

Every run after the New York futures close (17:00 NY), the last finished daily candle of NQ and gold futures is
read the ICT way: closed above or below the prior day's high or low, or swept it and closed back inside (a failed
breakout), or an inside day (no bias). The result is a LONG / SHORT / NO BIAS call with its draw on liquidity
(the candle's high or low), the other side, and the 20-day premium/discount zone.

Each rule is tested on every day since 2000 (free Yahoo daily futures candles, cached in `engine/cache/daily/`):
how often the next day reached the draw and closed in the bias direction (close to close, because Yahoo's daily
futures opens are unreliable), next to the same rates on all days. On NQ the candle rules give no edge on the
close, but the next day reaches the draw far more often than on an ordinary day (for example 77% vs 55% after a
close above the prior high). The site shows both numbers. Live calls are logged in `site/data/bias/log.json`
and scored the day after.
