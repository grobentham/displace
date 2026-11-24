# Research correction — 24 November 2026

The original Discovery V1/V2 paired-week candidate inference is under methodological review. Preserve frozen results and original classifications for accountability. Overlapping predictor and outcome sequences within short calendar blocks can induce spurious associations under an independent-direction null.

A deterministic synthetic control (100 replications, 1,300 adjacent fair Bernoulli pairs per replication; seed 20261124) gave a mean marginal effect of +0.04194 percentage points and paired-week effect of -19.88717 points. The legacy threshold flagged 100/100; the approximate 28-day cluster-adjusted marginal diagnostic flagged 0/100. This tests a specific null, not general market validity.

A separate implementation using current cached candles at commit 38fc0026817fe2abe82a600a7c04e3261b5bbfec reproduced counts and marginal rate differences for all 192 V2 historical combinations (tolerance 1e-9); original input hashes were not checked in that manual review. The alternative threshold flagged 41 combinations, 40 of the original 100 candidates and one additional combination. No models are promoted. Range-expansion comparisons can be mechanically coupled to predictors because the outcome is defined relative to the current range. These are not executable strategies or proof of predictive skill.

Corrective action: preserve original archives, display a correction prominently, label legacy inference under review, and publish separate diagnostics. Historical splits are exploratory. Six-month prospective batches cannot meet the 30-cluster minimum. Exact exchange sessions, independent vendor data, point-in-time records and executable cost validation remain unresolved.
