# Pre-registration: does volume or CVD rescue the frozen JeaFx version? (crypto perpetuals)

Written 2026-10-16, before any data was downloaded or any code for this experiment was run.
The frozen version (changes 1+2+3, 0.5 x ATR stop buffer; see frozen_PREREGISTRATION.md) is not changed.
Code: `download_binance.py`, `run_crypto.py` (development, tests 1-4 + setting choice),
`run_crypto_holdout.py` (test 5, run once, lock file results/CRYPTO_HOLDOUT_DONE.txt).

## Data
- Binance USD-M perpetual futures, 1h klines, data.binance.vision monthly files: BTCUSDT, ETHUSDT, SOLUSDT,
  BNBUSDT, XRPUSDT, 2020-01 to 2026-09 (latest full month). A symbol starts at its first available month.
- delta = 2 x taker_buy_base_volume - volume; CVD = running sum of delta (from the symbol's first candle).
- Development: 2020-01-01 to 2022-12-31 (data truncated there). Holdout: trades whose BoS is on or after 2023-01-01;
  earlier data is used only to warm up indicators, swings and zones.
- Costs: realistic 5 bp per side (+1 extra cost on stop exits, as for every other market), and zero cost.
  Funding payments are ignored. 4h candles: 00:00 UTC buckets (24h market).

## Versions (all = frozen version + optional filter, applied after every frozen rule, just before the order)
- **Base**: no filter.
- **A, volume breakout**: BoS candle volume >= m x mean volume of the previous 20 candles (m = 1.5 or 2.0).
- **B, CVD confirmation**: BoS candle delta in the trade direction (long: > 0; short: < 0) AND the summed delta
  from the origin candle to the BoS candle (both included) in the trade direction.
- **A+B**: both.

## Setting rule (written before running)
Only m may change. On development data, realistic costs, version A: m = 2.0 if version A with m = 2.0 has a higher
average R than with m = 1.5 AND at least 100 trades; otherwise m = 1.5. A+B uses the same m.

## Tests
1. **Indicator alone** (development data, no zones): at every candle where
   - A is true: direction = sign(close - open) of that candle (skipped if close = open); both m = 1.5 and 2.0;
   - "B alone" is true: delta of the candle and the sum of delta over that candle and the 4 before it have the same
     sign; direction = that sign. (B as defined above needs an origin candle; this is the zone-free stand-in.)
   measure the close-to-close move after 5/10/20/50 candles in that direction, in ATR(14) units at the event candle.
   Baseline: 20 random candles per event, same symbol, same UTC hour, same direction. Report average move, % right
   direction, difference vs random with a 95% bootstrap CI paired by event.
2. **Backtests** of Base, A, B, A+B on development data, zero and realistic: trades, win rate, average R with
   95% CI and t, profit factor, max drawdown (R and %).
3. **Removed vs kept**: Base trades (development, realistic) split by whether each filter passes on their setup;
   average R of removed vs kept, each with a 95% CI, and the difference with a 95% bootstrap CI.
4. **Forward-return and flip tests** on each version's setups (development), as in frozen_PREREGISTRATION.md
   (forward: all setups that passed the rules, 5/10/20/50 candles from the BoS close vs 2000 random candles per
   symbol; flip: filled trades, opposite direction at the same fill, mirrored stop/target).
5. **Holdout**, once, all four versions with the chosen m, zero and realistic costs. Same metrics as test 2.

## Pass mark (decided before running)
A filtered version "works" only if, on the holdout with realistic costs: average R >= +0.10, the 95% CI lower bound
> 0, and its average R is higher than Base's on the same period. Three filtered versions are tested, so a borderline
pass is treated with suspicion.

## Charts
10 random traded setups per version (development, realistic), each with price (zone, BoS, entry/stop/target, exit),
volume bars with the 20-candle average x m line, and the CVD line.
