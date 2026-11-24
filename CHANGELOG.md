# Changelog

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
