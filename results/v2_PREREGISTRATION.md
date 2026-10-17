# Pre-registration: "Reversal shape v2"

Written 2026-10-16, **before** any v2 code was run on any data. The frozen JeaFx version is not changed.
v2 is run **once** on histdata.com forex data 2015-2023 (7 pairs), zero and realistic costs.
Nothing is tuned after seeing results. Settings live in `config.py` (section "Reversal shape v2").

Rules are written for a **SHORT**; longs are the exact mirror (prices flipped), as in the frozen version.

## Amendment 1 (2026-10-16, before any v2 run on real data)
Reason: on synthetic trending data (600,000 hourly candles) the rules above produced 4 setups and 0 trades.
No v2 result on the real histdata data had been seen. Decided by the user:
- Prior trend: **3 rising highs and 3 rising lows** (L1<L2<L3, H1<H2<H3; order L1, H1, L2, H2, L3, H3),
  rally measured from L1 to H3. (Replaces "4 rising highs + 4 rising lows" in section 2.)
- Major swing zigzag: **4 x ATR** instead of 5 x ATR (section 1).
- Then a **counts-only** run on the real data: number of v2 setups and filled trades per pair and year,
  no win rate / R / P&L shown or computed for reporting.
- If total filled trades (realistic run) < 100: major zigzag loosened **once** to 3 x ATR, counts-only again,
  then the rules are frozen whatever the count.
- Then the full test is run once and everything is reported, including "not enough trades to judge".

### Counts-only results and freeze (2026-10-16, no win rate / R / P&L seen)
- Major zigzag 4 x ATR: 8 setups, 3 filled trades (2015-2023, 7 pairs) -> below 100.
- Major zigzag 3 x ATR (the one allowed loosening): 20 setups, 7 filled trades.
- **Rules frozen** at: 3 rising highs/lows, major zigzag 3 x ATR, everything else as in sections 1-7.
  Counts tables: results/v2_counts_*_major4.csv and *_major3.csv.

## 1. Major levels
- **Major swing**: zigzag on 1h with a 5 x ATR(14) threshold (same zigzag code as the frozen version).
  Usable only from the candle where the 5 x ATR move completes (its confirmation candle).
- **Major supply zone** (from a major swing high): top = the swing high; bottom = the body edge of the
  swing candle nearest the extreme, i.e. max(open, close). If thicker than 1 x ATR (ATR of the swing
  candle), bottom = top - 1 x ATR. Demand zones mirror this (bottom = swing low, top = min(open, close)).
- A major zone is valid until **(a)** a candle closes through it (supply: close > top), **(b)** it has been used
  for one trade (marked when a v2 order is placed from it), or **(c)** it is older than 60 calendar days
  (age measured from the swing candle). Age below 60 days never expires it.

## 2. Prior trend (short)
- On normal 1h swings (2 x ATR zigzag), the swings confirmed before the BoS candle must end with an
  alternating run of **4 rising swing lows and 4 rising swing highs**: L0<L1<L2<L3 and H0<H1<H2<H3,
  in the order L0, H0, L1, H1, L2, H2, L3, H3 (user's choice: "4 rising highs + 4 rising lows").
- H3 (the final high) is the highest high between L3 and the BoS candle. It may or may not already be
  confirmed as a 2 x ATR swing; if it is, it must be the last confirmed swing.
- Rally size: H3 - L0 >= 6 x ATR(14), ATR taken at the BoS candle.

## 3. Arrival and sweep
- **Arrival**: there is a major supply zone that (i) was confirmed before price first touched it,
  (ii) was first touched (high >= zone bottom) during the final leg, from the L3 candle to the H3 candle,
  (iii) has H3 >= its bottom, (iv) was not closed through up to and including the BoS candle,
  (v) was not older than 60 days at the H3 candle, and (vi) has not been used for a trade.
  ("Inside" is read as: the final high reached the zone and the zone held; a wick above the top is allowed
  as long as no candle closed above it.) If several qualify, the most recent one is used.
- **Sweep**: H3 > H2 (always true in a run of rising highs), and no candle from the first candle that traded
  above H2 up to the BoS candle closes more than 0.5 x ATR (ATR at the BoS candle) above H2.

## 4. Break and entry
- **BoS**: the frozen strong_close rule (close below the active swing low = L3; bearish candle; body >= 60% of
  range and >= 1.5 x the average body of the previous 10 candles). The frozen zone rules apply: supply zone
  from the origin high and the last bullish candle, 1.5 x ATR size rule, **unfilled bearish imbalance required**.
- **Entry**: sell limit at the bottom of that supply zone, placed at the BoS close, valid 20 candles,
  **cancelled if the target is touched before the order fills** (same-candle touch of both = order filled).
- **Stop**: H3 + 0.5 x ATR (ATR at the BoS candle); if that is less than 1 x ATR from entry, stop = entry + 1 x ATR.
- **Target**: the top edge of the nearest untouched, valid major demand zone below entry, as known at the BoS
  candle ("untouched" = no candle low <= its top since it was confirmed). **No such zone -> setup skipped.**
  Skip if (entry - target) < 2R. No cap.
- No 4h context rule (not part of v2).

## 5. Execution (unchanged frozen engine rules)
Fill: realistic run needs price to trade through the limit by the per-side cost; zero-cost run fills on touch;
a candle opening beyond the limit fills at the open; fill at/beyond the stop -> skipped. R is measured against the
planned risk (limit to stop). Stop checked first; on the fill candle only the stop is checked; exit after 200
candles at the close. One position per pair; a newer valid v2 setup replaces a waiting one. Costs per side as in
section 3 of the brief (forex ECN), plus one extra cost on stop exits in the realistic run.

## 6. Data
histdata.com GENERIC ASCII 1-minute bars, 2015-01-01 to 2023-12-31, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD,
GBPJPY, EURJPY. Converted from EST (no DST, UTC-5) to UTC and resampled to 1h; then the frozen cleaning rules.
All 9 years are used in the single run (no further split).

## 7. Reports
- Trades per pair per year; per pair and pooled: trades, win rate, average R with 95% bootstrap CI and t, profit
  factor, max drawdown (R and % at 0.5% risk) - zero and realistic costs.
- MFE/MAE of losers (as in the previous step).
- **Signal direction test (user's choice: both)**:
  1. *Flip test*: for every v2 trade that filled, the opposite trade at the same fill candle and price, with stop and
     target distances mirrored, same exit rules and costs. Report average R real vs flipped and the paired
     difference with a 95% bootstrap CI. If real is not clearly better than flipped, the signal carries no
     direction information.
  2. *Forward-return test*: for every v2 setup that passed all conditions (filled or not), the close-to-close move
     5/10/20/50 candles after the BoS close, in the signal direction, in ATR units. Baseline: the same measure at
     2000 random candles per pair with the same long/short mix. Report means, 95% CIs and the difference.
- Charts of the first 20 setups (chronological, all pairs): major zones, the 8 trend swings, the sweep (H2 line
  and H3), the BoS level and candle, entry zone, entry/stop/target and the exit if traded.
