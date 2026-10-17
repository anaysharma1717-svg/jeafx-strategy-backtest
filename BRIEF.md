# JeaFx Standard Confirmation Backtester

Build brief for Claude Code. 1 hour execution, 4 hour context, forex, gold, indices and stocks. Local Python, no QuantConnect.

Nothing in this brief is a promise that the strategy makes money. The point is to test JeaFx's entry model honestly.

*(Source: `JeaFx_Confirmation_Backtest_Brief.docx`, sections 1 to the end, saved verbatim as the specification.)*

---

## 1. Who I am and how you should work

I am a final year engineering student building a trading portfolio. I am not strong at coding. Build a local Python project (pandas, numpy, matplotlib, yfinance, scipy) that turns the JeaFx "standard confirmation entry" into exact rules and backtests it on 1 hour candles, using 4 hour candles for context.

- First save this whole brief in the project folder as BRIEF.md and treat it as the specification.
- Work in the steps listed in section 12. After each step, explain what you built in 3 to 6 plain English lines and stop until I type next.
- If any rule in this brief is ambiguous or impossible, stop and ask me. Do not silently change a rule.
- Never invent numbers or results. I will run the code and paste outputs. If a result is bad, say so plainly.
- No lookahead, ever. At any candle, the code may only use information from candles that have already closed. Section 10 lists the tests that prove this.
- Keep every setting in one file, config.py, with a short comment next to each.

## 2. The JeaFx method this backtest must follow

These points come from JeaFx's own material (his confirmation entry video, supply and demand cheat sheet, liquidity sweep class and his high timeframe strategy PDF). The rules in sections 5 to 8 are my exact translation of them into code.

- Trade with structure, never against it. Uptrend = higher highs and higher lows. Downtrend = lower lows and lower highs.
- Break of structure (BoS) must be a candle close, not a wick. A close beyond the level shows real buying or selling pressure.
- Trade the zone that caused the break. In an uptrend he buys the demand zone that produced the move which broke structure: the last opposite candle before the impulse, at the turning point.
- Imbalanced zones only. He buys "imbalanced demand" and sells "imbalanced supply": the move out of the zone must leave an imbalance (a price gap between candles, also called a fair value gap).
- Zones work once. After the first touch a zone is "efficient" and is never used again.
- Higher timeframe context decides direction and targets. Typical thesis from his PDF: "4H demand filled, looking for longs using CE on the 1H", target "into IMB supply" on the higher timeframe. (CE = confirmation entry, IMB = imbalance.)
- Liquidity matters. Many of his trades start after liquidity below a low (or above a high) has been swept.
- Execution: buy limit at the zone, stop just below the zone, target the opposing higher timeframe zone or level. His PDF shows a loss of 1R equal to about 0.5% of the account, so risk is 0.5% per trade.
- Two contexts use the same entry model: reversal (catching the first break of a downtrend) and continuation (joining an existing trend after a pullback).

## 3. Instruments

JeaFx mainly trades forex and gold. 1 hour structure works best on markets that trade almost 24 hours (no overnight gaps), so forex, gold and index futures are the core test. Liquid stocks are a secondary test, because hourly stock charts have only about 7 candles a day and gap overnight.

| Instrument | yfinance ticker | Why it is included | Realistic cost per side |
|---|---|---|---|
| EUR/USD | EURUSD=X | Most liquid pair, JeaFx's main market | 0.5 pip (0.00005) |
| GBP/USD | GBPUSD=X | Liquid, clean trends | 0.7 pip (0.00007) |
| USD/JPY | USDJPY=X | Liquid, trends well | 0.6 pip (0.006) |
| AUD/USD | AUDUSD=X | Major, different driver (commodities) | 0.6 pip (0.00006) |
| USD/CAD | USDCAD=X | Major, oil linked | 0.8 pip (0.00008) |
| GBP/JPY | GBPJPY=X | Volatile cross, popular with structure traders | 1.2 pips (0.012) |
| EUR/JPY | EURJPY=X | Liquid cross | 1.0 pip (0.010) |
| Gold | GC=F | Gold futures as a proxy for XAU/USD | 0.25 USD |
| Nasdaq 100 | NQ=F | Index futures, near 24h | 0.75 index points |
| S&P 500 | ES=F | Index futures, near 24h | 0.35 index points |
| US stocks | NVDA, AAPL, MSFT, AMZN, META, TSLA | Most liquid, high volume, strong trends | 1.5 bp (0.015%) |
| Nifty 50 | ^NSEI | Proxy for Nifty futures | 4 bp (futures STT 0.05% on sell side, plus fees and slippage) |
| Bank Nifty | ^NSEBANK | Proxy for Bank Nifty futures | 4 bp |
| Indian stocks | RELIANCE.NS, HDFCBANK.NS, ICICIBANK.NS | Most liquid NSE names, costed as stock futures | 5 bp |

**Cost notes.** Forex costs assume an ECN style account (raw spread plus commission). Stocks assume a commission free broker plus slippage. Indian costs assume futures, because trades last hours to days; holding cash shares overnight counts as delivery, where STT is 0.1% on both buy and sell, so add a separate test with 13 bp per side for the Indian cash stocks. Check current charges with your broker before trusting any Indian number.

Every test is run twice: zero cost (shows whether the pattern itself has any edge) and realistic cost (shows whether it survives real trading). The realistic run is the one that matters.

## 4. Data

- Download 1h candles with yfinance (`interval="1h"`, `period="730d"`; Yahoo allows about 730 days of hourly data). Cache each symbol as CSV in `data/` and reuse the cache unless I pass `--refresh`.
- Also accept my own CSV files in `data/` named `SYMBOL.csv` with columns time, open, high, low, close. For longer forex history I may download free 1 minute data from histdata.com; add a helper that resamples 1 minute data to 1 hour.
- Convert all timestamps to UTC. Drop rows with missing values, rows where high < low, and zero range candles that are clearly placeholders (e.g. weekend forex quotes).
- Print a data report per symbol: first and last date, number of candles, missing hours, and the largest gaps.
- 4h candles are built from 1h candles. Forex, gold and index futures: 4h buckets starting at 00:00 UTC (00, 04, 08, 12, 16, 20). Stocks: per trading session, first 4 hourly candles form one 4h candle and the rest of the session forms the second. A 4h candle may only be used after its last hour has closed.
- Continuous futures (GC=F, NQ=F, ES=F) jump when contracts roll. Detect gaps larger than 3 x ATR at the roll and ignore any break of structure caused only by such a gap. Report how many were found.

## 5. Exact definitions

### 5.1 ATR
ATR(14) = simple average of the true range over the last 14 closed candles. Calculated separately on 1h and 4h.

### 5.2 Swing highs and lows (zigzag)
- Track the running extreme since the last confirmed swing. A swing high is the exact highest high reached before price falls at least 2 x ATR(14) below it. A swing low is the exact lowest low reached before price rises at least 2 x ATR(14) above it.
- The level is drawn at that exact high or low, but it becomes usable only from the candle where the 2 x ATR move is completed. Store both the swing's own candle and its confirmation candle.
- Swings alternate: high, low, high, low.
- Fresh levels only: the active resistance is the latest swing high and the active support is the latest swing low. The previous swing of each type is kept only to compare higher or lower. Older swings are ignored.
- The same rule is applied to 4h candles with 4h ATR(14).

### 5.3 Structure state
- Bullish: latest swing high is above the previous swing high AND latest swing low is above the previous swing low.
- Bearish: both are lower.
- Ranging: anything else, or fewer than 2 swings of each type.

### 5.4 Break of structure (1h)
A bullish BoS happens on the first candle whose close is above the active swing high (shorts mirror this below the active swing low). Each swing level can be broken only once. Three definitions are compared:

- **wick**: the candle's high goes above the level (included only as a comparison; JeaFx does not accept this).
- **close**: the candle closes above the level.
- **strong_close** (JeaFx version, default): closes above the level AND is a bullish candle AND its body is at least 60% of its full range AND its body is at least 1.5 x the average body of the previous 10 candles.

If the first close above the level fails the strong_close test, the level is used up and no trade is taken from it.

Setup type: **reversal** if the 1h structure was bearish or ranging just before the break, **continuation** if it was bullish.

### 5.5 Imbalance (fair value gap)
- Bullish imbalance across three consecutive candles k, k+1, k+2: low of k+2 is above high of k. The gap is from high of k up to low of k+2.
- Bearish imbalance: high of k+2 is below low of k. The gap is from high of k+2 up to low of k.
- An imbalance is filled (efficient) once a later candle trades back through the whole gap.

### 5.6 Demand zone (the zone that broke structure)
- Origin low: the lowest low between the candle of the broken swing high and the BoS candle. This is the turning point (the lower low in a reversal, the higher low in a continuation).
- Origin candle: the last bearish candle at the origin low or up to 5 candles before it. If there is none, use the candle that made the origin low.
- Zone: bottom = origin low, top = high of the origin candle.
- Zone too big: if the zone is taller than 1.5 x ATR(1h), use the origin candle's body top (its open) as the zone top. If it is still taller than 1.5 x ATR, skip the setup.
- Imbalanced: at least one bullish imbalance must exist between the origin candle and the BoS candle, and still be unfilled at the BoS candle's close. Without it, skip the setup.
- Supply zones mirror all of this: origin high, last bullish candle, bearish imbalance.

### 5.7 Zone life (keeping levels fresh)
- Used on the first touch only, whether or not it produces a trade.
- Deleted if any candle closes below the zone bottom (the zone failed).
- Deleted after 50 1h candles without a touch.
- If a newer valid BoS in the same direction appears while an order is waiting, the newer zone replaces the older one. A valid BoS in the opposite direction cancels the waiting order.

### 5.8 4h zones and levels
Apply 5.2 to 5.6 on 4h candles to get fresh 4h demand and supply zones and 4h swing levels. A 4h zone is used up on its first touch, deleted when a 4h candle closes through it, and deleted after 60 4h candles. Only fully closed 4h candles are used.

## 6. Higher timeframe context (JeaFx context rule)

A long setup on 1h is allowed only if at least one of these is true at the BoS candle:

- **Trend continuation**: the 4h structure is bullish.
- **HTF zone reaction**: the 1h origin low traded into a fresh 4h demand zone ("4H demand filled, looking for longs"). This marks that 4h zone as used.

Shorts mirror this (4h structure bearish, or the origin high traded into a fresh 4h supply zone). Record which of the two reasons allowed each trade.

Optional liquidity sweep filter (off by default, tested as a variant): the origin low must trade below the swing low that was active before the move started (it took the liquidity under that low).

## 7. Entry, stop, target and exits

### 7.1 Entry
- Buy limit at the zone top, placed after the BoS candle closes, valid while the zone is alive (section 5.7).
- Fill rule (realistic run): price must trade through the limit by at least the per side cost, i.e. low <= limit minus cost. This models the spread and queue. In the zero cost run, a touch fills.
- If a candle opens below the limit, fill at the open.
- If the fill price is at or below the stop, skip the trade and log it.
- One position per symbol at a time. No scaling in.

### 7.2 Stop
- Stop = zone bottom minus 0.1 x ATR(1h) at the BoS candle.
- Triggered when low <= stop. Fill at the stop, or at the open if the candle opens below the stop. In the realistic run a stopped exit pays one extra per side cost as slippage.

### 7.3 Target (three versions)
- **4h target** (JeaFx version, default): the nearest of (a) the bottom of the nearest fresh 4h imbalanced supply zone above entry and (b) the active 4h swing high if price has not closed above it. If neither exists, use 2R.
- **fixed 2R**: entry plus 2 x risk.
- **1h higher high**: the highest high made between the BoS candle and the fill.
- Room check for the 4h and 1h versions: skip the trade if target minus entry is less than 1.5 x risk.
- Target fills when high >= target plus the per side cost in the realistic run (touch in the zero cost run).

### 7.4 Exits and conflicts
- Exit at stop, target, or at the close after 200 candles in the trade.
- If stop and target are both inside one candle, assume the stop was hit first.
- On the fill candle, check only the stop.
- Optional variant (off by default): move the stop to breakeven once price reaches +2R.

### 7.5 Sizing
Risk 0.5% of current equity per trade, starting at 100,000. Report results both in R (profit divided by the amount risked) and as an equity curve in percent.

## 8. Short trades

Shorts are the exact mirror: bearish BoS (a strong close below the active swing low), supply zone from the origin high and last bullish candle, bearish imbalance, sell limit at the zone bottom, stop above the zone top plus 0.1 x ATR, targets at fresh 4h demand or the active 4h swing low. Fill rules mirror too: the sell limit fills when high >= limit plus cost, and the stop triggers when high >= stop. Write unit tests that check a mirrored price series produces mirrored trades.

## 9. Versions to compare

The JeaFx faithful version is fixed in advance: strong_close BoS, imbalanced zones, 4h context rule, 4h target, room check 1.5R, zigzag 2 x ATR. Everything else is a comparison that shows what each rule adds.

| Setting | Values to compare |
|---|---|
| Break rule | wick, close, strong_close |
| Imbalance required | on, off |
| 4h context rule | on, off |
| Target | 4h target, fixed 2R, 1h higher high |
| Liquidity sweep filter | off, on |
| Breakeven at +2R | off, on |
| Costs | zero, realistic (every version runs both) |

Run the full grid only for comparison tables. Do not pick the best looking combination and call it the strategy.

## 10. Proving there is no lookahead or bug

- **Random walk test**: generate fake 1h prices with the same average volatility as EUR/USD and run the JeaFx version with realistic costs. Average R should be close to minus the costs. A clearly positive result means a bug.
- **Truncation test**: run on data up to a date in the middle, then on all data. Every trade that closed before that date must be identical in both runs. Any difference means future data leaked in.
- **Hand made patterns**: build a small price series with a known downtrend, a strong close BoS, an imbalance and a pullback into the zone. Check the exact zone, entry, stop, target and result. Do the same for a short, and for a wick only break that must NOT trade.
- **Visual check**: save candle charts of 20 random trades showing 1h swings, BoS level, the zone, the imbalance, 4h zone or level, entry, stop, target and exit. I will compare them with how JeaFx marks his charts.

## 11. Development data, holdout data and settings

- Split each symbol's history: first 60% = development, last 40% = holdout.
- Settings may only be explored on development data: zigzag 1.5, 2 or 3 x ATR; body filter 50% / 60% / 70% of range and 1.2 / 1.5 / 2 x average body; room check 1.5 / 2 / 3R.
- Choose settings with this rule, written before seeing results: the setting with the highest average R across all symbols pooled, with at least 100 trades, that is also positive on at least half of the symbols. If nothing qualifies, keep the defaults in this brief.
- Run the holdout once with the chosen settings and report it exactly as it comes out.

## 12. Build steps (stop after each)

1. Project setup: folders `data/`, `results/`, `charts/`, `tests/`; `config.py` with every setting from this brief; save BRIEF.md.
2. Data loader and data report (section 4), including 4h candle building.
3. ATR, zigzag swings and structure state on 1h and 4h. Save 3 charts with swings drawn so I can check them by eye.
4. Imbalances, BoS detection and zones. Save 5 charts with zones and imbalances drawn.
5. 4h context rule and 4h targets.
6. Backtest engine (sections 7 and 8) plus the unit tests from section 10.
7. Random walk test and truncation test.
8. Full runs on development data: all versions, zero and realistic costs.
9. Settings check on development data (section 11), then the single holdout run.
10. Final report and README.

## 13. Results to report

- For every version and cost setting: number of trades, win rate, average R, total R, profit factor, max drawdown in R and in % (0.5% risk), longest losing streak, average holding time.
- Average R with a 95% bootstrap confidence interval and its t statistic. Say clearly if the interval includes zero (no proven edge).
- Breakdowns for the JeaFx version: by symbol, by asset class, long vs short, reversal vs continuation, by which context reason allowed the trade, and by session of the entry in UTC (Asia 00:00 to 07:00, London 07:00 to 13:00, New York 13:00 to 21:00, late 21:00 to 24:00).
- How many setups each filter removed, and how those removed setups would have performed. A filter only helps if the trades it removes are worse than the ones it keeps.
- Equity curves (cumulative R and % equity) for the main versions, zero vs realistic costs on the same chart.
- All trades saved as CSV with: symbol, side, setup type, context reason, BoS time and level, zone top and bottom, imbalance, entry time and price, stop, target, target type, exit time and price, exit reason, R before costs, R after costs.
- README for GitHub: the rules in plain English, the comparison tables, holdout result, charts, and a limitations section.

## 14. Limitations to state honestly in the README

- Yahoo hourly data covers only about 2 years, which may be too few trades per symbol to prove anything.
- JeaFx makes discretionary choices that rules cannot fully copy: picking between several zones (inducement), news, Wyckoff style reads, and when to skip.
- Chart prices from Yahoo are not exactly broker prices, and costs are estimates.
- Results describe this rule set, not JeaFx's real trading results.

## Sources for the JeaFx rules

- JeaFx, "This entry model will change how you trade" (standard confirmation entry video), summary at videohighlight.com/v/4Ymh5Rvm0C8
- JeaFx, Supply & Demand Cheat Sheet (PDF), jeafx.com/wp-content/uploads/2024/03/Supply-Demand-Cheat-Sheet.pdf
- JeaFx, High Timeframe Strategy (PDF with trade theses), jeafx.com/wp-content/uploads/2023/10/High-Timeframe-Strategy.pdf
- JeaFx, "How to Master Liquidity Sweeps in Trading", summary at glasp.co/youtube/9nRFcetXqkA
- Indian STT rates after Budget 2026: groww.in/blog/what-is-stt
