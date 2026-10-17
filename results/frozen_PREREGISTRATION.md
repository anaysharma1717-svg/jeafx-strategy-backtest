# Pre-registration: frozen version on histdata 2015-2023, and the stale-fix holdout run

Written 2026-10-16, before either run. Each run happens once; nothing is tuned afterwards.
Code: `run_frozen.py` (runs A and B) and `run_holdout_stale.py` (run C). Lock files stop re-runs.

## Frozen version
The JeaFx version from the brief (strong_close BoS, imbalance required, 4h context rule, 4h target,
room check 1.5R, zigzag 2 x ATR, body 60% / 1.5 x average) **plus changes 1+2+3**:
1. Limit order valid 20 candles (was 50); cancelled if the planned target is touched on an earlier candle
   than the first touch of the entry (same-candle touch of both = filled).
2. Skip if the fill candle opens beyond the zone's far edge; stop at least 1.0 x ATR(1h) from entry.
3. Stop buffer 0.5 x ATR(1h) beyond the zone edge (was 0.1).
Change 4 is NOT included. R is measured against planned risk (gap-fill fix).

## Breakeven variant
The frozen version plus: once a candle's high (long) reaches entry + 1R (planned risk), the stop moves to the fill
price from the next candle on (the engine's existing breakeven rule with the trigger at +1R instead of +2R).
Not checked on the fill candle. A breakeven exit pays costs like a stop exit (2 sides + 1 slippage, realistic).
(No earlier written record of this variant was found in the project; it is recorded here before the run.)

## A. Frozen version and breakeven variant on histdata.com 2015-2023
7 pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, GBPJPY, EURJPY), 1h from 1-minute data, 4h built from 1h
(00:00 UTC buckets), zero and realistic costs (brief section 3). All 9 years, no split.
Report: trades, win rate, average R with 95% bootstrap CI and t, profit factor, max drawdown (R and %),
pooled, by pair and by year; MFE of losers.

## B. Direction tests on the frozen version's setups (same data)
- Flip test: every filled frozen-version trade, opposite direction at the same fill candle and price, stop and target
  distances mirrored, same exit rules (no breakeven) and costs. Paired difference real - flipped with 95% CI.
- Forward-return test: every setup that passed all entry rules (filled or not), close-to-close move 5/10/20/50
  candles after the BoS close in the signal direction (ATR units), vs 2000 random candles per pair with the same
  long/short mix.

## C. Original version + stale-setup fix on the old holdout (Yahoo data)
The brief's default JeaFx version (as "0 original" in results/changes_summary.csv) plus change 1 only
(20-candle wait, cancel if the target is touched first). Last 40% of each of the 21 Yahoo symbols; earlier data
only warms up indicators. Zero and realistic costs. Replaces the first holdout run, which had the gap-fill R bug.
