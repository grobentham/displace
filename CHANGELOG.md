# Changelog

## 2026-11-27: ES / NQ divergence (SMT)

- New page `smt.html` (Tools): today's level board (previous day, Asia and London highs and lows for both markets),
  the session chart, every recorded divergence and how NQ moved after it, tested against the base rate with 95%
  Wilson intervals. Swing and level divergences on 5-minute and hourly bars (engine/smt.py).
- The bar archive now includes ES futures (ES=F) alongside NQ and gold.

## 2026-11-26 session planning and replay

- The homepage shows session status, the next high-impact release, and a link back to saved plans. Traders can review the latest verified outcome and save a private note on their device.
- NQ, ES, and Gold have dated share links and previews. The new release replay page opens archived NQ data before the selected event. Holiday hours and MNQ sizing have dedicated pages.
- The public health workflow checks for stale snapshots and compares the published forecast, ledger, and MNQ brief.

## 2026-11-26 forecast and calendar correction

- Restored the eight November 27 outlooks from the verified pre-open deployment. The NQ range band is 590–1,723
  points. A later update briefly showed 337–979 points on the homepage and shared brief. The ledger retained the
  original band. Outlooks now keep their recorded values and timestamps through the session.
- Displace Open now uses the exchange session open as the receipt cutoff. The publish job checks that the homepage,
  ledger, and MNQ brief agree. The replay export filters out off-grid and unfinished bars.
- Removed the duplicate December 3 durable goods entry and refreshed the prior values for new home sales and durable
  goods. Historical event research is presented as observed market reactions with sample sizes and time windows.

## 2026-11-25: the homepage answers a trader's morning questions

- The first screen is now a morning check for NQ, ES and gold: the expected high-to-low range for the session
  (with the 8-in-10 band and how it compares with a normal day), the chance yesterday's high and low trade through,
  the session's major US releases in the visitor's own time, holiday and short-session warnings, and an account
  box that turns the range into dollars against the visitor's daily loss limit (saved on their device only).
- It says plainly that Displace doesn't call daily direction, because the tests find no reliable edge.
- bias.py publishes `range.avg20` and `range.med250` (normal-day ranges in points) for the comparison.
- The duplicate "Daily bias" and "News" cards under the hero were removed; everything else is unchanged.

## 2026-11-25: Iron Brain's live plans join the accountability ledger

- `engine/intraday.py` and `.github/workflows/witness.yml`: every 10 minutes through the New York morning (hourly
  after), Displace reads the plan decisions Iron Brain publishes and commits what it saw to the public `witness`
  branch. Iron Brain's own lock record is now private (it holds trade mechanics), so this commit history is the
  public timestamp proof.
- A finished trade counts only if it was locked before entry, Displace saw it live before the result, and none of
  its locked levels changed afterwards. Trades locked after their entry minute (Opening Drive v2 enters at the
  10:00 open and is usually published around 10:13) are scored apart with the lag, since a follower could not
  have had that entry. Fewer than 30 counted trades: no claim either way. Results in points and R, before costs.
- Accountability page: new "Iron Brain live intraday plans" section; the registry lists it.

## 2026-11-24: contract roll days

- `engine/rolls.py`: the days Yahoo's continuous futures switch contract, measured from 2016-2026 candles (average
  open gap on the switch day: NQ +0.41%, t 4.1; gold +0.42%, t 5.6; euro +0.21%, t 6.9). NQ/ES/YM/RTY switch on the
  first session after the 3rd Friday of Mar/Jun/Sep/Dec, gold on the first session of even months, the euro on the
  Monday of expiry week. Crude and bitcoin have no reliable switch day in free data and are not flagged.
- On a switch day the move from the previous close is partly the price gap between two contracts, so the research
  leaves that day's outcome out of the direction tests, the level-touch model and the touch ladder. Ranges are kept
  (one contract). Live forecasts for a switch day are still logged and shown but marked `roll` and left out of the
  scorecard; the next is NQ on Monday 21 Dec 2026.
- Effect: level-touch skill slightly higher everywhere (NQ high 0.266 -> 0.268, low 0.211 -> 0.216; ES high
  0.235 -> 0.245); range model unchanged (NQ 18.8%). The frozen discovery batches keep their registered data.

## 2026-11-24: exchange session engine

- `engine/exchange.py` (shared with Iron Brain): CME trading dates, holidays (full closures, early halts, early
  closes), session open, close and settlement times per market in New York time (daylight saving handled), which
  session a moment belongs to, and which session a forecast should be for. Rules and sources are in the file.
- Forecast targets use it: a forecast made from Wednesday 25 Nov 2026's candle is for Friday 27 Nov (Thanksgiving
  has no CME trading date), and eligibility uses the real session open (Friday's opens Wednesday 18:00). A logged
  forecast whose target date has no session is voided with a correction. Every past entry was rechecked: no changes.
- Daily candles: Yahoo publishes a candle for US holidays on which CME only trades until its early halt (37 NQ
  candles from 2015 to 2026). bias.clean now folds each into the next trading date, as CME does, instead of treating
  it as a short day. Effect on the tested results is small (NQ range model 19.1% -> 18.8% better than a 20-day
  average; level-touch skill unchanged), so the published findings stand. The frozen discovery batches keep their
  original data, as registered.
- The registered historical event features keep their weekday next-session rule, unchanged.
- `engine/test_exchange.py`: 2026 calendar, Thanksgiving week, weekends and closures, daylight saving, settlement
  times, forecast targets, holiday candles.

## 2026-11-24: discovery v3; v1 and v2 retired

- v1/v2 compared outcomes inside each week. With a condition built from the previous result ("after an up day")
  that leans toward reversal even on coin flips (the hot-hand small-sample bias): it flags "previous up" on 100 of
  100 random runs, which is why v2 had 100 "candidates" out of 192. v2's range outcome (tomorrow vs today's range) was
  close to circular. Both stopped running; their files and pages stay, marked retired.
- `research/discovery-plan-v3.json` (registered before running) and `engine/discovery_v3.py`: the overall rate
  difference with 28-day clustered errors (`validation.marginal`), range measured against a normal day (median of
  the last 20), one of each complementary pair: 128 tests. The 2020-2026 history was already seen, so it is
  descriptive only. Prospective evidence starts 1 Dec 2026; a candidate needs 30 blocks (late March 2029).
- First run on the history: no direction test differs from chance in any market; the 26 differences are all range
  persistence (wide days follow wide days; calmer days follow up days), known effects, not direction edges.
- `engine/test_discovery_v3.py`: no false reversal on 12 random-walk runs, the range outcome isn't circular, snapshots
  freeze and the history can never produce a candidate. New page: `research-v3.html` (the Discovery link).

## 2026-11-24: macro plan v2

- `research/macro-plan-v2.json` replaces v1 (kept for the record). Each FRED series now feeds one index only: in v1,
  VIX fed both D-STRESS and D-RISK and the high-yield spread fed both D-RISK and D-CREDIT, so D-RISK was the mirror
  image of the other two. D-STRESS is now NFCI and STLFSI4; D-RISK is the VIX alone, inverted.
- A reading's age counts from the end of the period it covers: September's CPI (dated 1 Sep) was 84 days old on
  24 Nov and marked stale; from 30 Sep it is 55 days, inside the 75-day limit. D-GROWTH and D-INFLATION are back.
- Ranking windows: 5 years for daily and weekly series (credit spreads 3 years, all FRED provides), 10 years for
  monthly, so 0 and 100 mean multi-year extremes.

## 2026-11-24: two registered direction tests (both failed)

- Registered first (`research/registered-2026-11-24.json`), then tested with the engine's unchanged event test across
  all 8 markets: the announcement-day premium (CPI, payrolls, Fed; Savor and Wilson 2013) and the pre-holiday effect
  (Ariel 1990). Neither passes in any market (bar |z| >= 3.32 over 56 event tests). Results:
  `research/results-2026-11-24.json`. Both stay in the event tests, so they keep counting toward the bar.
- `bias.nyse_holidays`: the exchanges' holiday rules (observed dates, Good Friday, Juneteenth from 2022, special
  closures), used for the pre-holiday flag. A first run used gaps in Yahoo's candles, which include missing data; it
  was discarded as an implementation bug and is described in the results file.

## 2026-11-24: integrity fixes (Phase 1)

- **Invalid forecasts are voided, not deleted.** On 20 Nov 2026 the NQ and gold forecasts were logged with expected
  ranges below zero (−27,278 to −26,546; −3,688 to −3,568) and scored as misses. `bias.audit` now marks any entry that
  fails `bias.problems` (probabilities outside 0–1, a negative or upside-down range, touch levels on the wrong side) as
  `void`, with a `correction` note (what, when found), keeps the original values, and leaves it out of every score.
- **Forecasts must be issued before their session opens** (18:00 New York the evening before). Each entry records
  `eligible`; late ones stay in the log but don't count. A summer run at 21:42 UTC (17:42 New York daylight time) was
  added: the 22:42 UTC run alone was after the open from March to November.
- **The forecast log is archived, never trimmed.** Entries beyond the newest 6,000 move to
  `site/data/bias/archive/log-YYYY.json`.
- **Failures are visible.** Each engine step runs through `engine/guard.py`, which records its result in
  `site/data/engine/health.json` and lets the other steps carry on. `bias.py` and `predict.py` now exit non-zero on an
  unexpected error instead of reporting success.
- **A final check before publishing.** `engine/gate.py` runs after every engine: every JSON must parse, the daily bias
  and its log must pass the forecast checks, and any file that fails is put back to its last good version. At the end
  of the run, `gate.py --report` writes a health table and turns the run red if any step failed; the site keeps the
  last good files.
- **Writes are all-or-nothing** for the bias files (write to a temporary file, then rename).
- **Clean daily highs and lows from Iron Brain** (earlier the same day): a bad print in Yahoo's daily candle is clipped
  to the spike-filtered minute data (`bias.despike_days`, kept in `cache/daily/patches.json`).
- **Pages deploy retries** twice when GitHub can't find the uploaded site.
- Tests: `engine/test_gate.py` (one test per fix); the bias test's fake data no longer changes between runs.

## Integrity follow-up (24 November 2026)
- Fail closed before deployment; minimum output contracts and nonfinite checks. No unverified restore or rebase on publication conflicts.
- Require exact daily target candle; exclude unknown eligibility and base-rate hits; include archived history.
- Preserve post-release historical observations but exclude them from live accuracy and live model training. Actual publication receipts remain a separate future improvement.

- Add successful Pages deployment receipts (forecast hash and timestamp) and require verified pre-window publication for live daily scoring.
- Add deterministic discovery v1: fixed eight registered experiments, exploratory historical study and disjoint prospective quarterly windows, persistent frozen results and offline tests. No model promotion or AI dependency.

## Macro and discovery expansion
- Separate v2 registered family of 192 candidate experiments across eight markets, 12 conditions, and two outcomes; v1 preserved.
- Six descriptive US macro indices based on current-vintage FRED observations, with freshness checks and missing-data suppression.
- Public macro dashboard and expanded research results with market/outcome filters.

## Statistical early warnings
- Add ten registered macro monitoring rules with separate entry/exit thresholds, severe-condition tiers, and source-linked transition history.
- Deduplicate repeated observations; preserve active state during data outages without displaying a current score.
- Add public early-warning page, offline tests and strict publication gate integration.

## Financial relationships
- Add 66 cross-market relationships across 12 registered series, matched interval endpoints, rolling correlations, disjoint-window shifts and prior-window residual diagnostics.
- Add source-linked interactive public explorer, missing/stale data handling and publication checks.

## Displace Open
- Add archive-inclusive forecast accountability with receipt verification, exact target outcome checks, explicit exclusions, per-market scores and calibration, original corrections, research batch accounting, and current implementation hashes.
- Add public evidence centre, source and engine snapshot health, downloadable JSON, and automated consistency tests.

## Automated publishing
- Deterministic daily intelligence editions, recorded warning bulletins, completed research summaries, weekly accountability and monthly model evidence snapshots.
- Frozen report objects, source hashes, integrity-checked archive catalogue and RSS feed, public searchable reader and offline tests.

## Displace Atlas
- Add registered 20-economy, eight-indicator annual World Development Indicators ingestion and cached refresh.
- Add explicit observation years, missing/stale states, same-year comparison, coverage counts, source links and public country profiles.

## Unified intelligence terminal
- Add responsive overview linking ten published research, market, calendar, Atlas, warning and evidence snapshots; isolate panel loading failures and preserve source dates.
- Add primary navigation and homepage terminal entry, external CSS/JS modules and Node utility tests.

## Product consolidation
- Shared navigation and external research page styling; global search with report and economy deep links.
- Crawlable source-linked static report pages, canonical URLs, generated sitemap and route/build/search regression tests.

- Add pinned Chromium desktop/mobile smoke tests for intelligence pages, country selection, search and static article navigation as a production workflow prerequisite.

## Research validation
- Separate Discovery V2 implementation, input-fingerprint-aware replication diagnostics, marginal 28-day cluster intervals, within-week effect comparisons and exploratory cost proxies.
- Public validation explorer with explicit unresolved requirements; no automatic model promotion or claim of external certification.

## Bias and event safeguards
- Seven-day label embargo, explicit completed-window checks, training-base-rate Brier skill, and suspension of automatic event and daily direction qualification.
- Independent price-only range replay, point MAE and interval scores, simple rolling direction and level-bin benchmarks, source-linked audit dashboard and tests.
