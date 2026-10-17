# Pre-registration: zone-touch forward test (frozen version, histdata 2015-2023)

Written 2026-10-16 before running. No rule changes. Run once (`run_zonetouch.py`, lock file results/ZONETOUCH_DONE.txt).

- **Setups**: every frozen-version setup (changes 1+2+3, see frozen_PREREGISTRATION.md) that passed all entry rules
  in the realistic run on histdata 2015-2023, 7 pairs - whatever happened to the order afterwards.
- **Zone touch**: the first candle after the BoS candle whose low <= the planned entry price (long; zone top) or
  whose high >= the planned entry (short; zone bottom). Searched up to 200 candles after the BoS; setups with no
  touch in that window are counted and excluded. Fills, cancellations and expiry are ignored.
- **Move**: from the touch candle's close, close after 5 / 10 / 20 / 50 candles minus that close, times +1 (long)
  or -1 (short), divided by ATR(14) at the touch candle. No stop, no target. Horizons past the end of data dropped.
- **Baseline**: 20 random candles per setup, same pair, same UTC hour of day as the touch candle, any date with
  enough data after it, same direction; same move measure. Seeded (RANDOM_SEED).
- **Report per horizon**: setups' average move and % > 0; baseline average and % > 0; difference of averages with
  a 95% bootstrap CI paired by setup (each setup's move minus the mean of its 20 random moves, resampled).
  Same table for touches within 10 candles of the BoS (touch index - BoS index <= 10) and for later touches.
