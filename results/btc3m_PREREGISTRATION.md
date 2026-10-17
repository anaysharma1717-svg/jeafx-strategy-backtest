# Pre-registration: all tests on BTCUSDT 3-minute candles, New York session only

Written 2026-10-16, before any 3-minute data was downloaded. Code: `download_binance.py 3m`, `run_3m.py`
(phases `report`, `dev`, `holdout`); the holdout phase runs once and is locked (results/BTC3M_HOLDOUT_DONE.txt).
No rule of any version is changed except the timeframe mapping below.

## Data and timeframe mapping
- Binance USD-M perpetual BTCUSDT, 3m klines (data.binance.vision), 2020-01 to 2026-09, with taker buy volume.
  (US stock 3-minute data is not freely available without an API key; this was the user's alternative.)
- Execution timeframe 3m (replaces 1h). Context timeframe **15m** (replaces 4h), built from 3m candles in
  00:00-UTC-anchored 15-minute buckets, usable only once closed. All candle counts in the rules stay as written
  (ATR(14), zigzag in ATR, 50/20-candle order waits, 200-candle time exit, 60-candle context zone expiry, etc.).
- **Session**: 09:30-16:00 America/New_York (daylight saving handled), Monday-Friday; US holidays not removed.
  Indicators, swings and zones use all candles (crypto trades 24/7). A setup is taken only if its BoS candle is in
  the session; an order can fill only up to the session's last 3m candle (15:57-16:00), after which it is cancelled;
  an open trade is closed at the close of that last candle ("session_close") if not exited earlier.
- Development = first 60% of candles; holdout = the rest (trades whose BoS is in it; earlier data only warms up).
- Costs: zero, and realistic 5 bp per side (+1 extra on stop exits), trade-through fill rule as everywhere else.
  Funding ignored.

## Tests on development data
1. Data report; 3 swing charts (3m and 15m); 5 zone charts.
2. Random-walk test (fake 3m prices with BTC's 3m volatility on the real timestamps, so the session logic is the
   same) for the original version and the frozen version, realistic costs; truncation test (cut at 50%) for the
   original, a close/2R/no-context version and the frozen version.
3. Full 144-version grid (brief section 9), zero and realistic; one-change-at-a-time table; filter removed-vs-kept.
4. Settings check (brief section 11: zigzag 1.5/2/3, body 50/60/70%, 1.2/1.5/2 x average, room 1.5/2/3R),
   selection rule as written in the brief; with one symbol, "positive on at least half the symbols" = positive.
5. Frozen version (changes 1+2+3) and its breakeven-at-+1R variant, zero and realistic; MFE of losers.
6. Flip test and forward-return test (5/10/20/50 candles) on the frozen version; zone-touch test (as in
   zonetouch_PREREGISTRATION.md, touch search 200 candles, 20 random same-hour times, split at 10 candles).
7. Volume / CVD (as in crypto_PREREGISTRATION.md): Base = frozen, A volume >= m x previous-20 average,
   B CVD confirmation (true taker delta), A+B; m chosen by the same rule (2.0 only if higher avg R and >= 100 trades);
   indicator-alone test; removed-vs-kept; flip and forward tests per version.
8. Charts: 20 random frozen-version trades; 10 per volume/CVD version with volume and CVD panels.

## Holdout (run once)
Original version with the settings chosen in test 4; frozen version; frozen + breakeven at +1R; Base, A, B, A+B
with the chosen m. Zero and realistic costs. Flip, forward-return and zone-touch tests on the frozen version.

## Pass marks (decided now)
- A, B, A+B: realistic average R >= +0.10, 95% CI lower bound > 0, and above Base on the holdout.
- Frozen version / breakeven variant / original: same thresholds (avg R >= +0.10 and CI above zero) to be called
  "has an edge on 3m BTC in the NY session". Many versions are tested; a borderline pass is treated with suspicion.
