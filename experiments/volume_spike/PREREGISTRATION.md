# Pre-registration: "Volume spike continuation" (separate from the JeaFx project)

Written 2026-10-16, before the test was run. Run once (`run_volume_spike.py`); lock file `results/DONE.txt`.

## Data
Binance USD-M perpetual 1h klines (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT) from
`jeafx_backtest/data/binance/`. Events and trades only from **2023-01-01 to 2026-09-30** (not yet used for this
test; 2020-2022 was used in the JeaFx project's development tests). Earlier candles only warm up the averages.

## Event
- A 1h candle with volume >= **2.0 x the average volume of the previous 20 candles**.
- Direction = sign(close - open). Candles with close = open are skipped and do not start a pause.
- **Non-overlapping**: after an accepted event on a symbol, new events on that symbol are ignored for the next 50 candles.
- Events without 50 candles of later data are dropped (same events at every horizon).

## Forward move
From the event candle's close, the move after 5 / 10 / 20 / 50 candles in the event's direction:
in **ATR units** (ATR(14) = simple average of the true range, at the event candle) and in **% of the event close**.
Baseline: **20 random candles per event**, same symbol, same UTC hour of day, from 2023-01-01 on with 50 candles
of later data, same direction. Report average move, % in the right direction, the random average, and the difference
with a 95% bootstrap CI paired by event.

## Simple trade
Enter at the **next candle's open**, exit at the close of the **20th candle** after entry (no stop, no target).
Net return % = direction x (exit / entry - 1) x 100 - 0.10 (5 bp per side). Report average net return, 95% bootstrap
CI, t, win rate (net > 0), by symbol and by year of entry.

## Pass mark (set before running)
Average net return per trade > 0 **and** 95% CI lower bound > 0, **and** average net return positive in at least
**3 of the 4 years** 2023, 2024, 2025, 2026 (2026 = January to September).

## Known limitation
The five coins move together, so events on different symbols at nearby times are not independent; the bootstrap CI
treats them as independent and may be too narrow. The pass mark is applied as written regardless.
