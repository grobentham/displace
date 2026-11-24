# Displace

Quant research site for NQ and gold futures: a tested daily bias, an economic calendar with release-surprise models, and a backtester on real bars, kept up to date by an engine that runs on its own. Free to run: the site is hosted on GitHub Pages, and the engine runs in GitHub Actions.

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

### Daily bias (`engine/bias.py`, `engine/quant.py`)

Every run after the New York futures close (17:00 NY) the engine re-tests everything on free data (Yahoo daily
futures candles since 2000 for NQ, ES, YM, RTY, gold, crude, the euro and bitcoin, cached in `engine/cache/daily/`;
FRED volatility indices, credit spreads, real yields, the dollar and the 2-year yield in `engine/cache/series/`;
release dates from the calendar cache) and publishes for the next session, per market:

- **Direction:** P(next close above today's close), starting at the long-run base rate. Up to twelve price and
  cross-asset signals per market (82 in all) are each walk-forward tested (refit yearly, scored out of sample). A
  signal moves the probability only with a Diebold–Mariano t above one Bonferroni bar for every signal tried across
  all markets (about 3.2), positive Brier skill in both halves and the last three years, and, for the four stock
  indices, positive skill in most of the other indices too. Calendar effects need |z| above the same kind of global
  bar (about 3.2 over 40 tests). FRED inputs are lagged by their publication delay (a week for the dollar index).
  As of November 2026 nothing passes in any market, so the page labels every lean "base rate", not long or short.
- **Volatility:** a HAR model of the log daily range (yesterday, last week, last month, implied volatility, release
  days, Mondays), walk-forward tested against a 20-day average: 19–23% lower error for the equity indices, 12% crude,
  11% bitcoin, about 3% gold, 2.5% euro, with 80% bands that hold about 80% of days.
- **Touch ladder:** the chance the next session reaches the close ± 0.5/1/1.5/2 forecast standard deviations, using
  the σ scale fitted on earlier years only. Where today's close position in its range improved those odds out of
  sample, the conditional figure is used and the any-day rate shown beside it. The position sizer shows the touch
  odds for the chosen stop.
- **Levels:** P(trading above today's high / below today's low), about 20–26% Brier skill out of sample, with
  reliability data for the calibration chart.
- **Sessions (NQ, gold):** overnight vs New York session (Mondays measured from Friday's close) and an intraday
  momentum test, from the hourly archive. Passing needs both the up rate and the average move past |z|, |t| ≥ 2.64
  (six tests) in both halves. Only about two years of hourly bars exist, so these are marked provisional.
- **Data cleaning:** candles with high ≤ low or non-positive prices are dropped (crude's negative print on
  2020-04-20); gold starts in 2013 because earlier Yahoo candles are placeholders.
- **Live record:** every call is logged and scored the next day; direction hits count only tested calls.

numpy is installed in the workflow for these models. `test_bias.py` checks that random walks pass no direction test
while the volatility and level models find their (real) skill.

### Strategy lab (backtester)

After a rule test, MNQ Replay checks whether the result is better than luck: 100 runs of random entries at the same
rate with the same exits and costs, 1,000 Monte Carlo reshuffles of the trades (90% net range, 95th-percentile
drawdown), and a deflated Sharpe ratio that corrects for the number of distinct rule sets tried on the device.

## Autonomous discovery and verified publication

`engine/discovery.py` runs the fixed, registered `research/discovery-plan-v1.json` on completed daily candles and generates `site/data/research/discovery.json`. The research page is `site/research.html`. Historical results are exploratory; prospective quarterly results are frozen on first completion. Approximate weekly-block intervals account for the eight tests within a batch, not indefinite repeated research. No automatic promotion. Changing a registered plan requires a new version and preserving the old archive.

The strict final publication gate validates minimum contracts and blocks the candidate deployment on errors. The last successfully deployed site remains available. Daily live scoring requires a successful pre-window deployment receipt; post-release event reaction records are retained but not credited as prospective predictions. Receipts are recorded after successful Pages deployment and incorporated on the next engine run. Actual availability to individual browsers is not guaranteed.

## Macro and expanded research

Discovery v2 is registered separately from v1: 8 markets × 12 prior-session conditions × 2 outcomes = 192 candidate experiments, with frozen historical and six-month prospective batches. Macro v1 computes six descriptive US indices from FRED series, equal-weighting component percentiles only when all components have sufficient and reasonably fresh data. These are current-vintage descriptive indicators, not validated recession or return forecasts. See the registered JSON plans for definitions. Review data rights before commercial use.

## Statistical early warnings

The registered `research/signals-plan-v1.json` defines ten descriptive monitoring rules on the six macro indices. `engine/signals.py` runs after macro ingestion, uses separate entry and exit thresholds to avoid repeated toggling, records initial detections, activations, severity changes and clearances, and retains source-linked evidence. Stale inputs suspend evaluation without declaring that an existing condition cleared. All transition timestamps reflect the engine observation time, not the original release time; no forecast accuracy is claimed. `site/signals.html` displays current states and history. Thresholds are policy settings rather than validated probabilities.

## Financial relationships

The registered `research/relationships-plan-v1.json` defines 12 series and 66 pairs. `engine/relationships.py` matches exact observation interval endpoints, computes correlations of changes over 20, 60 and 252 matched observations, compares disjoint 60-observation windows, and measures an unusual residual using a regression fitted only to the prior 60 observations. Stale results are suppressed. All metrics are descriptive, current-vintage, and affected by mismatched market closes, provider delays, revisions and futures rolls. Threshold flags are not significance tests or signals to trade. See `site/relationships.html`.

## Displace Open

The public `site/open.html` transparency centre uses `engine/evidence.py` to reconcile active and archived recorded forecasts with successful deployment receipts, explicitly classify exclusions, recompute per-market prospective Brier scores, benchmark skill, range coverage and calibration, and surface original corrections, research batch counts and current code/plan hashes. Historical event reactions are kept separate. The counts cover recorded forecasts, not all potential scheduled calls; uptime and completeness require separate monitoring. Source and component health are read from the published engine snapshot, not a real-time availability probe. No current implementation hash is represented as a historical model version.

## Automated research publishing

`engine/publisher.py` generates deterministic source-linked reports from the current candidate macro, signals, relationships and evidence snapshots. The first successful daily candidate after 12:00 UTC is archived, along with one report per recorded signal transition and completed discovery batch, and weekly/monthly as-of accountability reviews for completed target periods with recorded forecasts. Historical reports are not silently revised; each carries its input hashes and generation timestamp. Missing data stays unavailable. The catalogue and RSS feed are verified against archived report hashes by the final publication gate. Open provides later settlements. Read `site/publications.html` and `site/data/publications/feed.xml`. No LLM is used.

## Displace Atlas

Atlas uses the World Bank Indicators API v2, World Development Indicators source 2, with 20 selected economies and eight annual economic indicators from 2010 onward. It refreshes each series at most weekly after success, retries failures with a six-hour cooldown, and exposes observation years, source dates, missing values, cached fallback and stale-cache states. Country comparisons use a single selected year, never latest observations from mixed years. It is an annual descriptive database, not real-time macro or a forecast engine. Central government debt has uneven coverage and is not total public-sector debt. See `research/atlas-plan-v1.json`, `engine/atlas.py` and `site/atlas.html`. Source terms and third-party indicator rights must be reviewed before commercial redistribution.

## Unified intelligence terminal

`site/terminal.html` brings ten published data snapshots into one workspace using independently loaded, source-dated panels. It distinguishes model tiers, shows missing panels without hiding other data, uses New York time for upcoming releases, compares Atlas growth using a common reference year, and links back to the full research and trading tools. `site/assets/terminal.css` and `site/assets/terminal.js` are separate modules; utility regression tests run in CI. The terminal is a read-only snapshot viewer, not a live trading feed or uptime probe.

## Product consolidation

Research pages share a dark intelligence stylesheet and consistent navigation; page-specific styles remain in external CSS files. The original trading homepage and replay desk keep their legacy layouts. `search.html` searches tools, report titles and country names; country deep links select the profile. `engine/sitebuild.py` creates escaped crawlable report HTML and a project sitemap after the strict gate, before saving and deploying the candidate. Static report pages are derived from the verified archive, not a replacement for original JSON. Sitemap is available at `/displace/sitemap.xml`; GitHub Pages project paths are not a separate domain root, so robots.txt submission is not claimed. Source terms, legal review and a full legacy frontend refactor remain open.

## Research validation

The separate implementation in `engine/validation.py` recalculates Discovery V2 conditions and rates, verifies frozen dataset fingerprints, compares marginal effects with the original within-week estimand, applies approximate 28-day cluster-robust intervals and family correction, and evaluates an exploratory early/late open-to-close cost proxy for directional conditions. It publishes discrepancies and never promotes models. This is internal code-path replication using the same cached market data, not third-party validation or point-in-time/executable strategy testing. See `research/validation-plan-v1.json`.

The validation engine includes a deterministic IID-direction null control. The paired-week contrast can create a spurious effect when the previous direction overlaps the next outcome within the same week; the new marginal diagnostics answer a different question. The 30-cluster requirement cannot be met by a six-month prospective block, so those blocks remain descriptive unless a separately registered longer evaluation is conducted.

**Research correction:** paired-week candidate inference is under review; original archives are retained. See `research/correction-2026-11-24-discovery.md`. No historical candidate is an approved trading edge.

## Bias and event model audit

Production directional model promotion is suspended: daily directions use the historical base rate; event and event-range candidate statuses are historical only. The event walk-forward replay uses a seven-calendar-day label embargo, refuses unsettled reactions, and reports Brier skill against both 50% and the prior training base rate. These remain current-vintage diagnostics, not verified first-release forecasts. `engine/modelaudit.py` independently replays a price-only range model and simple probability benchmarks, reports log-space error and anchored point-space error separately, and exposes interval scores. It is not an exact replication of the original full model and no historical output constitutes an approved trade.
