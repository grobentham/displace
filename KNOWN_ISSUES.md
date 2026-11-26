# Known issues

What is known to be wrong or limited, and what is being done about it. Keep this current: fix an item, move it to
CHANGELOG.md.

## Open

- **ES / NQ divergence is as fresh as the engine run.** Bars are delayed Yahoo data, refreshed about hourly when the
  engine runs, so a divergence can appear on the page well after it formed. 5-minute history starts with the first
  ES download (about 60 days) and most 5-minute groups will read "too few cases" for a while.

- **No tested daily direction.** Every daily bias is the base rate ("NQ rose on 54% of past days"); 138 direction tests
  (82 signals, 56 calendar events, including the announcement-day and pre-holiday effects registered on 24 Nov 2026)
  and none passes its bar. The site says so. Direction research has a low prior; the range and level-touch forecasts
  are where the tested skill is (NQ: range error 19% below a 20-day average, 80% band covers 79% of days; level-touch
  Brier skill about 0.21-0.26, walk-forward since 2012).
- **Thin live record.** The bias log starts 19 Nov 2026. Until there are months of eligible forecasts, live scores mean
  little.
- **BTC daily candles look thin** (open equals low, or close equals high, on several days): Yahoo's BTC=F data. Treat BTC
  levels with caution until a better free source is found.
- **Daily candles cover a slightly different window than 1-minute sessions** (Yahoo's daily open and low can differ
  from the minute bars). Only a bad print that Iron Brain's spike filter caught is corrected (bias.despike_days).
- **The main page is one large file** (site/index.html, about 456 KB). Split it piece by piece when a section is
  being changed anyway; no big-bang rewrite.
- **Market data licensing.** Prices come from Yahoo Finance, which does not license its data for a paid product. Sort
  out licensed data, and whether paid trading content needs a licence in Singapore, before charging anyone.

- **Discovery v1/v2 results are retired**, not deleted: their within-week method is biased toward reversal. Use v3.

## Decided, not changing

- The intraday witness depends on GitHub's scheduler, which can run late or skip; a trade that starts and finishes
  between two readings is "not seen live" and isn't counted. Lock and fill times are Iron Brain's clock; the
  witness proves only that a decision was public by the commit that recorded it. Days before 25 Nov 2026 aren't
  witnessed.

- Contract rolls are detected by calendar rule, not measured per roll: free data has no per-contract prices, so the
  jump can't be subtracted, only the switch day left out. Crude (monthly, sign varies) and bitcoin are not flagged.
  ES/YM/RTY jumps (~0.1%) are below what the data can detect but follow the NQ calendar, so they are flagged too.

- **scheduler.yml waits on a runner between slots.** GitHub's cron often fires late or not at all on this repo; the
  waiting runner is what keeps the schedule. It costs nothing on a public repo. Revisit only if the repo becomes private
  (then it would use most of the free minutes).

## Integrity follow-up limitations
- Publication receipts prove successful Pages deployment at a conservative post-deploy time, not delivery to every browser. No receipt means no live credit. Old event-window reactions remain historical only; future publication-relative event models need a distinct target and validation.
- Discovery v1 is fixed, automatically runs from cached daily candles, and publishes exploratory statistics and frozen prospective quarterly batches. Weekly-block intervals are approximate; no automatic model promotion, no claim of tradable edge. Full exchange-specific calendars, independent timestamping and data rights remain open.
