# Known issues

What is known to be wrong or limited, and what is being done about it. Keep this current: fix an item, move it to
CHANGELOG.md.

## Open

- **No tested daily direction.** Every daily bias is the base rate ("NQ rose on 54% of past days"); no direction signal
  has passed its bar. The site says so. This is a research question, not a bug.
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

## Decided, not changing

- **scheduler.yml waits on a runner between slots.** GitHub's cron often fires late or not at all on this repo; the
  waiting runner is what keeps the schedule. It costs nothing on a public repo. Revisit only if the repo becomes private
  (then it would use most of the free minutes).
