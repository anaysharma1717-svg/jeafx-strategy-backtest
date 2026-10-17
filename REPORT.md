# Report: does the JeaFx confirmation entry work?

**Author:** Anay Sharma · **Date:** October 2026 · Full details: [README.md](README.md)

## Question
JeaFx, a trading YouTuber, teaches a supply-and-demand entry: wait for a candle to **close** beyond a swing level
(break of structure), then place a limit order at the **imbalanced zone** that caused the break, trading in the
direction of the **4-hour** trend, with the target at the next 4-hour zone. I wanted to know whether this makes money
when it is written as exact rules and tested properly.

## Method
- Wrote the method as exact rules ([BRIEF.md](BRIEF.md)) and built a Python backtester from scratch.
- 1-hour entries, 4-hour context. Realistic costs (spread, fees, slippage) and a zero-cost run for comparison.
- Proved there is no lookahead (truncation test), no fake edge (random-walk test), and that shorts mirror longs
  (28 unit tests). Checked trades by eye on charts - which found one bug, fixed before the final tests.
- Split data into development and holdout; wrote every later test down in advance ("pre-registration") and ran it
  once, with lock files to stop re-runs.

## Data
- Yahoo 1-hour: 21 markets (7 forex pairs, gold, Nasdaq and S&P futures, 6 US stocks, Indian indices and stocks), 2023-2026.
- histdata.com: 7 forex pairs, 2015-2023 (about 55,000 hourly candles each) - never used while designing.
- Binance: 5 crypto perpetuals with real buy/sell volume, 2020-2026.

## Results (average per trade after costs; R = amount risked)

| Test | Trades | Avg R | 95% range | Result |
|---|---|---|---|---|
| Original rules, 21 markets | 194 | -0.37 | -0.60 to -0.12 | loses |
| Improved version, 9 years of unseen forex | 268 | **-0.32** | -0.53 to -0.10 | loses |
| Improved + breakeven at +1R | 268 | -0.27 | -0.44 to -0.08 | loses |
| Improved version on crypto (holdout) | 123 | -0.27 | -0.59 to +0.07 | no edge |
| + volume / CVD filters | 82-100 | -0.17 to -0.30 | all include 0 | fail |

- **0 of 144** rule combinations made money after costs.
- Taking the **opposite** trade did about as well, and price after the break or after touching the zone moved
  **no differently from random** - the setup carries no information about direction.

## What I tried to fix it
Cancelling stale orders, wider and minimum stops, closer targets, breakeven, a stricter "reversal shape" setup,
volume-breakout and order-flow (CVD) filters, and a pure volume-spike strategy. Wider stops helped a little on the
data they were designed on, but nothing survived a clean test.

## Why it fails
**Adverse selection.** A limit order waiting at the zone gets filled mainly when the break is failing. Breaks that
work run away without coming back, so they never fill; breaks that come back tend to keep going (27% of trades were
stopped out within the hour they filled, and quick returns to the zone kept moving against the trade).

## Conclusion
As exact rules, the JeaFx confirmation entry has **no edge** on forex, gold, indices, stocks or crypto, and none of
the improvements tried changes that. This tests my rule-based reading of his free material - not his personal
discretionary trading - and is not financial advice.

## Limitations
Short Yahoo history (2-3 years), rule interpretations that others might make differently, estimated costs, and a
3-minute intraday test that is not finished yet (stopped by low memory; its sanity checks passed).
