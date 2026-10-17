# I backtested YouTuber JeaFx's trading strategy. It didn't work.

**By Anay Sharma** · final-year engineering student · Python (pandas, numpy, scipy, matplotlib)

JeaFx is a popular trading YouTuber who teaches a supply-and-demand method: wait for a **break of structure**,
then buy or sell the **imbalanced zone** that caused the break, with **4-hour context** deciding direction and
targets (his "standard confirmation entry"). I turned that method into exact, testable rules and built a backtester
from scratch to answer one question:

> **Does this entry model make money once it is written down as exact rules and tested honestly - no lookahead,
> realistic costs, and data it has never seen?**

**Short answer: no.** It showed no edge on forex (9 years of unseen data), gold, indices, stocks or crypto - and
none of the improvements I tried (better stops, stale-order cancelling, breakeven, a stricter "reversal shape",
volume and CVD filters) rescued it.

📄 **Short version: [REPORT.md](REPORT.md)** (one page, plain English).

> This tests *my rule-based translation* of JeaFx's public material (videos and free PDFs). It is not his own
> discretionary trading, I have no affiliation with him, and nothing here is financial advice.

## The verdict in one table

Average result per trade after realistic costs, in R (1R = the amount risked on the trade). A strategy with an edge
would be clearly above 0.

| Test | Data | Trades | Avg R after costs | 95% CI | Verdict |
|---|---|---|---|---|---|
| Original rules (development) | Yahoo 1h, 21 markets, 2023-25 | 194 | **-0.37** | -0.60 .. -0.12 | loses |
| All 144 rule combinations | same | - | 0 of 144 above zero | - | none work |
| Original + stale fix (holdout) | Yahoo 1h, last 40% | 52 | -0.09 | -0.73 .. +0.65 | no edge |
| **Improved "frozen" version (unseen)** | **histdata forex 1h, 7 pairs, 2015-2023** | **268** | **-0.32** | **-0.53 .. -0.10** | **loses** |
| Frozen + breakeven at +1R (unseen) | same | 268 | -0.27 | -0.44 .. -0.08 | loses |
| "Reversal shape v2" | same | 7 | +0.22 | -1.08 .. +1.84 | too rare to judge |
| Frozen on crypto (holdout) | Binance perps 1h, 2023-26 | 123 | -0.27 | -0.59 .. +0.07 | no edge |
| + volume / CVD filters (holdout) | same | 82-100 | -0.17 .. -0.30 | all include 0 | fail pass mark |
| Volume-spike momentum (side test) | same | 2,605 | -0.12% per trade | -0.25% .. 0.00% | fails |

## Everything I tried, in order

| # | What I tried | Why | What happened |
|---|---|---|---|
| 1 | Original JeaFx rules on 21 markets | the baseline | -0.37R per trade; worse than a random walk after costs |
| 2 | 144 combinations of the rules (wick/close break, imbalance, context, 3 targets, sweep, breakeven) | find out what each rule adds | every one lost money after costs |
| 3 | Settings check + first holdout | pre-registered selection rule | +0.04R, driven by one +22.8R trade; also had a bug |
| 4 | **Visual check -> found and fixed a bug** (R on gap fills) | charts of 20 trades | -0.42R -> -0.37R; unit test added |
| 5 | Cancel stale setups (target hit before fill), wait 20 not 50 candles | avoid "late" fills | removed the setups that worked -> worse (-0.49R) |
| 6 | Minimum stop of 1 x ATR, skip gaps past the zone | stops were too tight | biggest improvement (-0.20R) |
| 7 | Stop buffer 0.5 x ATR | more room | -0.08R on development data |
| 8 | Target 0.25 x ATR before the level, 4R cap | hit targets more often | worse (-0.20R), dropped |
| 9 | **Frozen version (5+6+7) on 9 years of unseen forex** | the clean test | **-0.32R, clearly negative** |
| 10 | Breakeven at +1R | a third of losers were +1R first | -0.27R, still negative |
| 11 | Flip test, forward-return test, zone-touch test | is there *any* signal? | direction carries no information; quick zone returns keep going against you |
| 12 | "Reversal shape v2" (long trend, sweep, major zones) | a stricter, more JeaFx-like setup | only 7 trades in 9 years - too rare |
| 13 | Volume and CVD (order-flow) filters on crypto | maybe order flow confirms the good breaks | filters did not separate good from bad trades; all failed |
| 14 | Volume-spike momentum on its own (side test) | the indicator alone looked predictive | gone on fresh, non-overlapping data |

**Main finding - adverse selection.** A limit order waiting at the zone fills *mostly when the break is failing*:
the setups that work run away and never fill, the ones that fill keep going through the zone (27% were stopped out
on the same candle they filled). That is why tightening, widening, filtering and confirming didn't fix it.

---

## Contents
1. [The rules in plain English](#1-the-rules-in-plain-english)
2. [How the test was kept honest](#2-how-the-test-was-kept-honest)
3. [Stage 1: original version on development data](#3-stage-1-original-version-on-development-data)
4. [Stage 2: first holdout run (with a bug)](#4-stage-2-first-holdout-run-with-a-bug)
5. [Stage 3: fixes and their effects](#5-stage-3-fixes-and-their-effects)
6. [Stage 4: the adverse selection finding](#6-stage-4-the-adverse-selection-finding)
7. [Stage 5: frozen version on 9 years of unseen forex data](#7-stage-5-frozen-version-on-9-years-of-unseen-forex-data)
8. [Stage 6: original version + stale fix on the old holdout](#8-stage-6-original-version--stale-fix-on-the-old-holdout)
9. [Stage 7: "Reversal shape v2" - too rare to judge](#9-stage-7-reversal-shape-v2---too-rare-to-judge)
10. [Stage 8: Volume and CVD on crypto](#10-stage-8-volume-and-cvd-on-crypto)
11. [Side test: volume-spike momentum](#11-side-test-volume-spike-momentum)
12. [Limitations](#12-limitations)
13. [Running it yourself](#13-running-it-yourself)
14. [Project layout](#14-project-layout)
---

## 1. The rules in plain English

Full specification: [BRIEF.md](BRIEF.md). All settings: [config.py](config.py).

- **Swings**: a swing high is the highest high before price falls 2 x ATR(14) below it (lows mirror this).
  A swing only becomes usable once that 2 x ATR move has happened.
- **Trend**: higher highs + higher lows = bullish, lower highs + lower lows = bearish, otherwise ranging.
- **Break of structure (BoS)**: the first candle that **closes** beyond the active swing level with a strong body
  (body >= 60% of its range and >= 1.5 x the average body of the last 10 candles). Wicks don't count.
- **Zone**: the last opposite candle at the turning point that produced the break (the "origin"), from the origin
  low to that candle's high (body only if the zone is taller than 1.5 x ATR).
- **Imbalance**: there must be an unfilled fair value gap between the origin and the break.
- **4h context**: longs only if the 4h trend is bullish or the move started inside a fresh 4h demand zone
  (shorts mirror this).
- **Order**: limit order at the zone edge, stop just beyond the zone, target at the nearest 4h opposing zone or
  4h swing level (2R if none), skipped if the target is less than 1.5R away. Zones work once.
- **Risk**: 0.5% of equity per trade; results are reported in R (profit / amount risked).
- **Costs**: two runs each: zero cost, and realistic cost (ECN spreads for forex, futures/stock costs elsewhere,
  limit orders must trade *through* the price by the cost, stops pay one extra cost as slippage).

## 2. How the test was kept honest

- **No lookahead**, checked three ways: a truncation test (cutting the data in half gives identical trades
  before the cut; 63 runs, 1,112 trades, all identical), a random-walk test (on fake EUR/USD-like prices the
  strategy makes -0.02R before costs, i.e. nothing), and hand-built price patterns with known answers.
- **Shorts are an exact mirror of longs** (same code on flipped prices), verified by tests.
- **26 unit tests** in [tests/](tests/).
- **Development / holdout split** (60% / 40%), settings chosen on development data only, and later tests
  **pre-registered** in writing before being run ([results/*PREREGISTRATION.md](results/)) with lock files
  that stop accidental re-runs.
- **Visual checks**: every stage has charts of random trades so the drawings can be compared with JeaFx's.

## 3. Stage 1: original version on development data

Yahoo hourly data (~2-3 years), 21 symbols, first 60% of each = development data.
Numbers below include the gap-fill bug fix described in stage 3.

| Cost | Trades | Win rate | Avg R | 95% CI | Profit factor | Max drawdown |
|---|---|---|---|---|---|---|
| zero | 210 | 19.5% | -0.22 | -0.44 .. +0.03 | 0.73 | 23% |
| realistic | 194 | 18.6% | **-0.37** | -0.60 .. -0.12 | 0.59 | 32% |

- That is **worse than the random walk** (-0.11R after costs): not just no edge, but a reliable loss on this data.
- **All 144 rule combinations** (break rule x imbalance x context x target x sweep x breakeven) lost money after
  costs; none had a confidence interval above zero.
- **What each filter did** (section 13 test: a filter helps only if the trades it removes are worse than those it keeps):

| Filter | Trades removed | Avg R removed | Avg R kept | Helps? |
|---|---|---|---|---|
| strong close (vs plain close) | 196 | -0.43 | -0.37 | yes, slightly |
| imbalance required | 193 | +0.07 | -0.37 | **no** |
| 4h context rule | 407 | +0.12 | -0.37 | **no** |
| room check 1.5R | 0 | - | -0.37 | no effect |
| liquidity sweep (optional) | 142 | -0.40 | -0.32 | yes, slightly |

- Indian cash stocks at delivery cost (13 bp per side) lost -1.22R per trade.
- Equity curves: [charts/step8_equity_dev.png](charts/step8_equity_dev.png).

## 4. Stage 2: first holdout run (with a bug)

The section 11 settings rule picked one setting (zigzag 1.5 x ATR, body 50%, room check 3R), the only one with
>= 100 trades that was positive on half the symbols - though its development average was itself negative
(-0.11R; this search ran before the gap-fill fix). The holdout (last 40%) was run once: +0.04R per trade, 76 trades, CI -0.64 to +0.91, entirely
due to one +22.8R trade (without the top 3 trades: -0.47R).

**This run had the gap-fill bug (next section), so it is replaced by stage 6.** It is reported here because it happened.

## 5. Stage 3: fixes and their effects

**Bug found in the visual check (gap fills).** When a candle opened beyond the limit price, the trade filled at
the open (correct), but R was measured from the fill to the stop instead of the planned risk. A META trade that
gapped to 494 with a stop at 493.85 showed -2.46R instead of -0.08R. 11 of 194 development trades were affected.
After the fix: -0.42R -> **-0.37R** per trade. A unit test now covers it.

**Rule changes tested on development data** (added one on top of the other, realistic costs):

| Stage | Trades | Win rate | Avg R | 95% CI |
|---|---|---|---|---|
| original | 194 | 18.6% | -0.37 | -0.60 .. -0.12 |
| + 1: cancel if target touched before fill; wait 20 candles, not 50 | 79 | 15.2% | -0.49 | -0.83 .. -0.10 |
| + 2: skip fills that gap past the zone; stop at least 1 x ATR | 79 | 19.0% | -0.20 | -0.65 .. +0.34 |
| + 3: stop 0.5 x ATR beyond the zone (was 0.1) | 85 | 21.2% | -0.08 | -0.55 .. +0.46 |
| + 4: target 0.25 x ATR before the level, cap 4R | 76 | 23.7% | -0.20 | -0.55 .. +0.20 |

- The "gap past the zone" rule removed 0 trades; the **1 x ATR minimum stop** did all of change 2's work.
- Change 4 made things worse and was dropped. **Changes 1+2+3 became the "frozen version".**
- Stop buffers 0.25 / 1.0 x ATR (development only): -0.26R / +0.01R. The +0.01R was *not* adopted, because picking
  the best-looking option on the same data is exactly what the brief forbids.
- Because these changes were designed after seeing development results, they needed new data to be tested -> stage 5.
- Before / after charts of the same 20 trades: [charts/trades/](charts/trades/) and [charts/trades_after/](charts/trades_after/).

## 6. Stage 4: the adverse selection finding

The most useful thing this project found is *why* the entry loses:

- **The setups that work never fill.** With change 1, 253 waiting orders were cancelled because price reached the
  target *before* coming back to the entry. Those are the breaks that "worked".
- **The orders that do fill are the ones where the pullback keeps going.** Removing the stale setups made the
  remaining trades *worse* (-0.37R -> -0.49R). In the original version 27% of trades were stopped out on the same
  candle that filled them: price sliced through a thin zone and a tight stop in one hour.
- **Many losers were in profit first.** With the frozen rules, 33% of losing trades reached +1R and 50% reached
  +0.5R before being stopped (average MFE of losers 0.89R on the 9-year data).

A limit order at the zone is filled *selectively* when the market moves against the idea - classic adverse selection.
Wider stops reduce the damage (stages 2-3) but do not remove it.

**Zone-touch forward test** (pre-registered, run once, [results/zonetouch_PREREGISTRATION.md](results/zonetouch_PREREGISTRATION.md)).
For each of the frozen version's 1,279 setups on the 9-year forex data, the first candle that touched the entry
price (990 setups; 289 never touched within 200 candles), then the move in the trade direction from that candle's
close, with no stop or target, against 20 random times per setup at the same hour of day:

| Touch | Setups | 5 candles | 10 candles | 20 candles | 50 candles |
|---|---|---|---|---|---|
| all | 990 | -0.08 (CI -0.22 .. +0.05) | -0.02 (-0.18 .. +0.15) | -0.02 (-0.23 .. +0.19) | -0.18 (-0.53 .. +0.16) |
| within 10 candles of the break | 306 | **-0.27 (-0.50 .. -0.04)** | **-0.27 (-0.53 .. -0.01)** | -0.24 (-0.59 .. +0.11) | -0.09 (-0.70 .. +0.54) |
| later | 684 | 0.00 (-0.17 .. +0.16) | +0.10 (-0.10 .. +0.30) | +0.08 (-0.19 .. +0.33) | -0.23 (-0.64 .. +0.17) |

Difference vs random in ATR units. After touching the zone, price is a coin flip (about 50% in the trade direction).
When price returns to the zone quickly, it tends to keep going *against* the trade - consistent with adverse
selection, but only 2 of 12 intervals exclude zero and both only just, so this is supporting evidence, not proof.

## 7. Stage 5: frozen version on 9 years of unseen forex data

Pre-registered in [results/frozen_PREREGISTRATION.md](results/frozen_PREREGISTRATION.md) and run once.
Data: histdata.com 1-minute bars, 2015-2023, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, GBPJPY, EURJPY
(~55,000 hourly candles per pair), never used before by this version.

| Version | Cost | Trades | Win rate | Avg R | 95% CI | Profit factor | Max drawdown |
|---|---|---|---|---|---|---|---|
| frozen | zero | 292 | 21.9% | -0.13 | -0.34 .. +0.09 | 0.84 | 64.7R / 28% |
| frozen | **realistic** | **268** | **20.1%** | **-0.32** | **-0.53 .. -0.10** | **0.64** | **97.3R / 39%** |
| + breakeven at +1R | zero | 294 | 14.3% | -0.14 | -0.30 .. +0.04 | 0.76 | 59.9R / 26% |
| + breakeven at +1R | **realistic** | **268** | **13.8%** | **-0.27** | **-0.44 .. -0.08** | **0.60** | **84.1R / 35%** |

- **By pair** (frozen, realistic): 6 of 7 pairs negative; only USD/JPY slightly positive (+0.07R, 30 trades, CI -0.76 to +1.12).
- **By year**: negative in 2015-2019 and 2021 (2019: -0.75R, 2021: -0.86R); roughly flat in 2020, 2022, 2023.
- **Breakeven at +1R** turned 86 trades into small losses (breakeven exits still pay costs) and cut winners; it
  lost slightly less but is still clearly negative.
- **Flip test** (same fill, opposite direction, mirrored stop/target): real -0.32R vs flipped -0.37R, difference
  +0.05R (CI -0.27 to +0.36). **The signal's direction carries no measurable information.**
- **Forward-return test** (1,279 setups, price 5/10/20/50 hours after the break in the signal direction, vs random
  times): differences +0.01, +0.06, +0.09, -0.11 ATR, every CI includes zero. **No directional information.**
- Full tables: [results/frozen_hist_summary.csv](results/frozen_hist_summary.csv);
  equity: [charts/frozen_hist_equity.png](charts/frozen_hist_equity.png).

## 8. Stage 6: original version + stale fix on the old holdout

Pre-registered (same file, run C) and run once: the brief's original version plus change 1 only, on the last
40% of the 21 Yahoo symbols. Replaces the bugged stage 2 run.

| Cost | Trades | Win rate | Avg R | 95% CI | Profit factor | Max drawdown |
|---|---|---|---|---|---|---|
| zero | 55 | 16.4% | -0.00 | -0.59 .. +0.69 | 1.00 | 8.2% |
| realistic | 52 | 17.3% | -0.09 | -0.73 .. +0.65 | 0.90 | 9.5% |

Too few trades to say much; the average is held up by three trades (ICICI Bank +11.0R and +6.6R, AAPL +6.7R).
Without them: -0.59R. Forex alone: -0.47R over 30 trades.

## 9. Stage 7: "Reversal shape v2" - too rare to judge

A stricter, pre-registered setup ([results/v2_PREREGISTRATION.md](results/v2_PREREGISTRATION.md)): an extended
trend (3 rising highs and lows, >= 6 x ATR), the final high arriving in an untouched major (3 x ATR) zone with a
small sweep, then a strong break, entry at the break zone, target at the next major zone (>= 2R).

Thresholds were loosened twice **using trade counts only** (no results seen), then frozen. On 9 years x 7 pairs it
produced **20 setups and 7 trades**: avg +0.22R after costs, CI -1.08 to +1.84. Flip and forward-return tests also
showed nothing. **Verdict: not enough trades to judge; closed, no further changes.**
Charts of all 20 setups: [charts/v2_setups/](charts/v2_setups/).

## 10. Stage 8: Volume and CVD on crypto

Pre-registered in [results/crypto_PREREGISTRATION.md](results/crypto_PREREGISTRATION.md). Question: does order-flow
information rescue the frozen version? Data: Binance USD-M perpetuals (BTC, ETH, SOL, BNB, XRP), 1h klines with taker
buy volume, 2020-01 to 2026-09. Development 2020-2022, holdout 2023-01 to 2026-09 (run once, locked).
delta = 2 x taker buy volume - volume; CVD = running sum of delta. Costs 5 bp per side; funding ignored.

- **A, volume breakout**: the break candle's volume >= 1.5 x the average of the previous 20 candles
  (1.5 vs 2.0 chosen on development data by a pre-written rule: 2.0 had only 51 trades, below the 100 required).
- **B, CVD confirmation**: the break candle's delta and the summed delta from the origin candle to the break both
  point in the trade direction.

**Holdout (2023-01 to 2026-09), realistic costs.** Pass mark: average R >= +0.10, 95% CI above zero, and better than Base.

| Version | Trades | Win rate | Avg R | 95% CI | Profit factor | Max drawdown | Result |
|---|---|---|---|---|---|---|---|
| Base (frozen version) | 123 | 21.1% | -0.27 | -0.59 .. +0.07 | 0.70 | 51R / 23% | - |
| A, volume | 94 | 23.4% | -0.19 | -0.55 .. +0.21 | 0.79 | 39R / 18% | **fail** |
| B, CVD | 100 | 20.0% | -0.30 | -0.64 .. +0.08 | 0.67 | 46R / 21% | **fail** |
| A+B | 82 | 23.2% | -0.17 | -0.58 .. +0.27 | 0.80 | 32R / 15% | **fail** |

At zero cost A and A+B were slightly positive (+0.12R, +0.13R, CIs wide); costs take about 0.25R per trade because
the stops are only about one hourly ATR wide.

**Trades removed vs kept by each filter** (Base trades on development data, realistic costs):

| Filter | Kept | Avg R kept | Removed | Avg R removed | Kept - removed (95% CI) |
|---|---|---|---|---|---|
| A, volume x1.5 | 81 | -0.44 | 27 | -0.42 | -0.02 (-0.67 .. +0.56) |
| A, volume x2.0 | 50 | -0.40 | 58 | -0.47 | +0.07 (-0.48 .. +0.62) |
| B, CVD | 71 | -0.58 | 37 | -0.16 | -0.42 (-1.08 .. +0.19) |
| A+B, x1.5 | 55 | -0.57 | 53 | -0.30 | -0.27 (-0.84 .. +0.28) |

No filter separated better trades from worse ones; the CVD filter, if anything, threw away the less bad trades.

**The indicators on their own do carry information.** At every development-data candle where the filter condition
held (no zones), the move in the candle's / delta's direction beat random times at every horizon: a volume-spike
candle (>= 1.5 x average, 20,006 events) was followed by +0.03 ATR after 5 candles rising to +0.18 after 50 (x2.0:
+0.05 to +0.28); delta agreeing with the last 5 candles' delta: +0.02 to +0.07. All CIs were above zero.
**Caveat:** these events overlap heavily (neighbouring candles share most of their future path), so the CIs are
too narrow; the pre-registered method did not correct for this. The information exists in the indicator but does
not pass through the JeaFx zone entry.

**Direction tests** (development): forward returns after the break did not differ from random for any version.
In the flip test, the *opposite* trades did better than the real ones for Base and B (Base, zero cost: real -0.41R,
flipped +0.11R, difference CI -1.02 .. -0.03). **This is suggestive only** - many comparisons were made - but it
points the same way as the adverse selection finding.

Charts (price with zone and orders, volume bars with the threshold line, CVD line), 10 per version:
[charts/crypto_setups/](charts/crypto_setups/).

## 11. Side test: volume-spike momentum

Not part of the JeaFx rules: a separate check of whether the volume-spike information found in stage 8 can be
traded on its own. Pre-registered in [experiments/volume_spike/PREREGISTRATION.md](experiments/volume_spike/PREREGISTRATION.md),
run once on Binance 2023-01 to 2026-09 (data not used for this question before).

- Event: a 1h candle with volume >= 2 x the previous 20 candles' average; direction = the candle's direction;
  after an event, new events on that coin are ignored for 50 candles (no overlap). 2,605 events.
- Move in the event's direction vs 20 random same-hour times: no difference after 5, 10 or 20 candles
  (e.g. 20 candles: +0.03 ATR, CI -0.13 .. +0.20); price went the event's way only 46-47% of the time.
- Simple trade (next open, exit after 20 candles, 5 bp per side): **-0.12% per trade** (CI -0.25% .. 0.00%),
  45% winners, negative in 3 of 4 years. **Fails the pass mark.**
- So the "indicator alone" result in stage 8 was mostly the same move counted many times (overlapping events).

## 12. Limitations

- **Short Yahoo history** (~2-3 years of hourly data): stages 1, 2 and 6 have only 50-200 trades.
- **Rules can't copy discretion**: JeaFx picks between competing zones, reads news and Wyckoff structure and
  skips trades. These results describe this rule set, not his trading.
- **Interpretation choices** were needed (e.g. liquidity sweep definition, 4h zone "freshness", same-candle order of
  events). They are documented in the code and pre-registrations; other reasonable choices could give different numbers.
- **The 4h zone context almost never triggers** under strict "zones work once" rules (11 of 683 setups), so the
  context rule is effectively "trade with the 4h trend".
- **Prices and costs are estimates**: Yahoo / histdata prices are not exact broker prices; Indian costs in particular
  should be checked with a broker.
- **Intra-candle order is unknown** on hourly data; the engine assumes the worse case (stop before target).
- **Development data was reused** to design changes 1-3, so stage 3 numbers are optimistic; only stages 5 and 6
  (and the crypto holdout) are clean out-of-sample tests.
- **Forex only** for the 9-year test; gold, indices and stocks were only tested on the short Yahoo history.
- **Crypto**: funding payments are ignored; costs are a flat 5 bp per side; only 5 symbols and ~4 years of holdout,
  and the five coins move together, so the trades are less independent than the CIs assume.
- **Many tests were run**, so an occasional "significant" result is expected by chance; that is why pass marks were
  fixed in advance and borderline passes treated with suspicion. No version passed anyway.

## 13. Running it yourself

Price data is not stored in the repo (about 420 MB); the download scripts re-create it in `data/`.

```bash
pip install -r requirements.txt
py -m pytest tests            # 26 unit tests
py run_data.py                # Yahoo 1h data for 21 markets + data report
py run_structure.py           # swings / structure charts
py run_setups.py              # break of structure + zones, charts
py run_validation.py          # random walk + truncation tests
py run_dev.py                 # all 144 versions on development data
py run_trade_charts.py        # 20 random trade charts
py run_changes.py             # the rule changes, one on top of the other
py download_histdata.py       # histdata.com forex 2015-2023 (1-minute -> 1h)
py download_binance.py        # Binance perpetual 1h klines with taker buy volume
py run_crypto.py              # crypto development tests (volume / CVD)
```

One-shot scripts (`run_holdout.py`, `run_holdout_stale.py`, `run_frozen.py`, `run_zonetouch.py`, `run_v2.py`,
`run_crypto_holdout.py`, `experiments/volume_spike/run_volume_spike.py`) refuse to run twice
unless given `--force`, because their results were pre-registered as single runs.

## 14. Project layout

```
BRIEF.md            the full specification I wrote before building
REPORT.md           one-page summary
config.py           every setting, with a comment
jeafx/              the backtester: data, indicators, structure, setups, 4h context, engine, stats, v2, crypto
tests/              26 unit tests (hand-made patterns, mirror, truncation, no-lookahead)
run_*.py            one script per stage (see above)
results/            tables (CSV), pre-registrations and lock files of every stage
charts/             swing, zone and trade charts for visual checks
experiments/        side test not part of the JeaFx rules (volume-spike momentum)
```

