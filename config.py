"""
All settings for the JeaFx standard confirmation backtester.
Every number here comes from BRIEF.md (section noted in brackets).
Change values here only; no other file should hold a magic number.
"""

# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
DATA_DIR = "data"        # cached / user supplied 1h CSVs (SYMBOL.csv)
RESULTS_DIR = "results"  # trade CSVs, tables, reports
CHARTS_DIR = "charts"    # all saved PNG charts

# ---------------------------------------------------------------------------
# Instruments and costs  [section 3]
# cost_type "abs" = price units per side, "bp" = basis points of price per side
# session "24h" = forex / gold / index futures (4h buckets from 00:00 UTC)
# session "stock" = exchange session (first 4 hourly candles = 4h #1, rest = 4h #2)
# ---------------------------------------------------------------------------
INSTRUMENTS = {
    # symbol       asset class    cost type  cost per side  session  roll gaps? (continuous futures)
    "EURUSD=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.00005, "session": "24h",   "futures": False},  # 0.5 pip
    "GBPUSD=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.00007, "session": "24h",   "futures": False},  # 0.7 pip
    "USDJPY=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.006,   "session": "24h",   "futures": False},  # 0.6 pip
    "AUDUSD=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.00006, "session": "24h",   "futures": False},  # 0.6 pip
    "USDCAD=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.00008, "session": "24h",   "futures": False},  # 0.8 pip
    "GBPJPY=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.012,   "session": "24h",   "futures": False},  # 1.2 pips
    "EURJPY=X":    {"asset_class": "forex",        "cost_type": "abs", "cost": 0.010,   "session": "24h",   "futures": False},  # 1.0 pip
    "GC=F":        {"asset_class": "gold",         "cost_type": "abs", "cost": 0.25,    "session": "24h",   "futures": True},   # 0.25 USD
    "NQ=F":        {"asset_class": "index_fut",    "cost_type": "abs", "cost": 0.75,    "session": "24h",   "futures": True},   # 0.75 index points
    "ES=F":        {"asset_class": "index_fut",    "cost_type": "abs", "cost": 0.35,    "session": "24h",   "futures": True},   # 0.35 index points
    "NVDA":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},  # 1.5 bp
    "AAPL":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},
    "MSFT":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},
    "AMZN":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},
    "META":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},
    "TSLA":        {"asset_class": "us_stock",     "cost_type": "bp",  "cost": 1.5,     "session": "stock", "futures": False},
    "^NSEI":       {"asset_class": "india_index",  "cost_type": "bp",  "cost": 4.0,     "session": "stock", "futures": False},  # proxy for Nifty futures
    "^NSEBANK":    {"asset_class": "india_index",  "cost_type": "bp",  "cost": 4.0,     "session": "stock", "futures": False},  # proxy for Bank Nifty futures
    "RELIANCE.NS": {"asset_class": "india_stock",  "cost_type": "bp",  "cost": 5.0,     "session": "stock", "futures": False},  # costed as stock futures
    "HDFCBANK.NS": {"asset_class": "india_stock",  "cost_type": "bp",  "cost": 5.0,     "session": "stock", "futures": False},
    "ICICIBANK.NS":{"asset_class": "india_stock",  "cost_type": "bp",  "cost": 5.0,     "session": "stock", "futures": False},
}

INDIA_CASH_DELIVERY_COST_BP = 13.0  # separate test: Indian cash shares held overnight (STT 0.1% both sides) [3]
INDIA_CASH_SYMBOLS = ["RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS"]  # symbols re-run at the delivery cost [3]

COST_MODES = ["zero", "realistic"]  # every test runs both; realistic is the one that matters [3]

# ---------------------------------------------------------------------------
# Data  [section 4]
# ---------------------------------------------------------------------------
YF_INTERVAL = "1h"               # yfinance candle interval
YF_PERIOD = "730d"               # Yahoo's hourly history limit (about 2 years)
CSV_COLUMNS = ["time", "open", "high", "low", "close"]  # required columns for user CSVs
TIMEZONE = "UTC"                 # all timestamps converted to UTC
FOUR_H_ANCHOR_HOURS = [0, 4, 8, 12, 16, 20]  # 24h markets: 4h buckets start at these UTC hours
STOCK_FIRST_4H_CANDLES = 4       # stocks: first 4 hourly candles of a session form the first 4h candle
ROLL_GAP_ATR_MULT = 3.0          # futures: a gap > 3 x ATR is treated as a contract roll

# ---------------------------------------------------------------------------
# ATR and swings  [5.1, 5.2]
# ---------------------------------------------------------------------------
ATR_PERIOD = 14                  # ATR(14), simple average of true range, separate on 1h and 4h
ZIGZAG_ATR_MULT = 2.0            # swing confirmed after a 2 x ATR move away from the extreme

# ---------------------------------------------------------------------------
# Break of structure  [5.4]
# ---------------------------------------------------------------------------
BOS_RULE = "strong_close"        # "wick", "close" or "strong_close" (JeaFx default)
BOS_BODY_RANGE_MIN = 0.60        # strong_close: body >= 60% of the candle's full range
BOS_BODY_AVG_MULT = 1.5          # strong_close: body >= 1.5 x average body of previous candles
BOS_BODY_AVG_LOOKBACK = 10       # number of previous candles for the average body

# ---------------------------------------------------------------------------
# Zones  [5.6, 5.7, 5.8]
# ---------------------------------------------------------------------------
ORIGIN_CANDLE_LOOKBACK = 5       # last opposite candle at the origin or up to 5 candles before it
ZONE_MAX_ATR_MULT = 1.5          # zone taller than 1.5 x ATR(1h) -> use body top; still too tall -> skip
REQUIRE_IMBALANCE = True         # zone must have an unfilled imbalance between origin and BoS candle
ZONE_EXPIRY_1H = 50              # 1h zone deleted after 50 1h candles without a touch
ZONE_EXPIRY_4H = 60              # 4h zone deleted after 60 4h candles

# ---------------------------------------------------------------------------
# Higher timeframe context  [6]
# ---------------------------------------------------------------------------
USE_HTF_CONTEXT = True           # long needs 4h bullish structure OR origin low in a fresh 4h demand zone
USE_LIQUIDITY_SWEEP = False      # optional variant: origin must take out the prior active swing low/high

# ---------------------------------------------------------------------------
# Entry, stop, target, exits, sizing  [7]
# ---------------------------------------------------------------------------
STOP_ATR_BUFFER = 0.1            # stop = zone bottom - 0.1 x ATR(1h) at the BoS candle
TARGET_MODE = "4h"               # "4h" (JeaFx default), "2r" (fixed 2R) or "1h_hh" (1h higher high)
FALLBACK_TARGET_R = 2.0          # 4h target falls back to 2R when no 4h zone or level exists
FIXED_TARGET_R = 2.0             # the "fixed 2R" target version
MIN_ROOM_R = 1.5                 # room check: skip if target - entry < 1.5 x risk (4h and 1h targets)
MAX_BARS_IN_TRADE = 200          # exit at the close after 200 candles in the trade
USE_BREAKEVEN = False            # optional variant: stop to breakeven once price reaches +2R
BREAKEVEN_TRIGGER_R = 2.0        # the +2R level that triggers breakeven
RISK_PER_TRADE = 0.005           # 0.5% of current equity risked per trade
STARTING_EQUITY = 100_000        # starting account size

# ---------------------------------------------------------------------------
# Rule changes requested after step 9 (defaults below = the original brief, i.e. switched off)
# ---------------------------------------------------------------------------
MAX_WAIT_1H = ZONE_EXPIRY_1H     # candles a limit order may wait for its first touch (brief: 50)
CANCEL_ON_TARGET_TOUCH = False   # cancel the waiting order if price reaches the planned target first
SKIP_GAP_BEYOND_ZONE = False     # skip if the fill candle opens beyond the zone's far edge
MIN_STOP_ATR = 0.0               # minimum stop distance from entry in ATR(1h); 0 = no minimum
TARGET_BUFFER_ATR = 0.0          # target placed this many ATR(1h) before the 4h level
TARGET_CAP_R = None              # cap on target distance in R; None = no cap

# values used for the four requested changes (run_changes.py)
CHANGE1_MAX_WAIT = 20            # change 1: wait at most 20 candles, cancel on target touch
CHANGE2_MIN_STOP_ATR = 1.0       # change 2: stop at least 1.0 x ATR from entry, skip gaps beyond zone
CHANGE3_STOP_BUFFER = 0.5        # change 3: stop = zone edge -/+ 0.5 x ATR
CHANGE3_TEST_BUFFERS = [0.25, 0.5, 1.0]  # change 3: buffers compared on development data only
CHANGE4_TARGET_BUFFER = 0.25     # change 4: target 0.25 x ATR before the 4h level
CHANGE4_TARGET_CAP_R = 4.0       # change 4: no target further than 4R

# ---------------------------------------------------------------------------
# "Reversal shape v2" (pre-registered, see results/v2_PREREGISTRATION.md). Separate from the frozen version.
# ---------------------------------------------------------------------------
V2_DATA_DIR = "data/histdata"    # histdata.com 1h candles (built from 1-minute files)
V2_FIRST_YEAR = 2015             # first year of histdata data
V2_LAST_YEAR = 2023              # last year of histdata data
V2_PAIRS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "GBPJPY=X", "EURJPY=X"]
V2_MAJOR_ZIGZAG_ATR = 3.0        # major swing: price moves >= 3 x ATR(14) away (FROZEN after amendment 1 counts; was 5, then 4)
V2_MAJOR_ZONE_MAX_ATR = 1.0      # major zone thickness cap (from the extreme)
V2_MAJOR_ZONE_MAX_AGE_DAYS = 60  # major zone expires when older than 60 days
V2_TREND_SWINGS = 3              # 3 rising highs and 3 rising lows (amendment 1; was 4)
V2_COUNT_MIN_TRADES = 100        # amendment 1: if filled trades < 100, loosen major zigzag once
V2_FALLBACK_MAJOR_ZIGZAG_ATR = 3.0  # amendment 1: the one allowed loosening
V2_TREND_MIN_RALLY_ATR = 6.0     # rally from the first low to the final high >= 6 x ATR
V2_SWEEP_MAX_CLOSE_ATR = 0.5     # sweep: no close more than 0.5 x ATR beyond the previous swing high/low
V2_MAX_WAIT = 20                 # limit order valid for 20 candles
V2_STOP_BUFFER_ATR = 0.5         # stop = sweep extreme +/- 0.5 x ATR
V2_MIN_STOP_ATR = 1.0            # minimum stop distance from entry
V2_MIN_TARGET_R = 2.0            # skip if the major-zone target is less than 2R away
V2_FORWARD_HORIZONS = [5, 10, 20, 50]  # forward-return test horizons (candles)
V2_RANDOM_BASELINE_PER_PAIR = 2000     # random times per pair for the forward-return baseline

# ---------------------------------------------------------------------------
# Crypto volume / CVD experiment (results/crypto_PREREGISTRATION.md)
# ---------------------------------------------------------------------------
CRYPTO_DATA_DIR = "data/binance"          # Binance USD-M perpetual 1h klines
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CRYPTO_FIRST_MONTH = (2020, 1)            # first month downloaded
CRYPTO_LAST_MONTH = (2026, 9)             # latest full month
CRYPTO_HOLDOUT_START = "2023-01-01"       # development = before this date, holdout = from it
CRYPTO_INSTRUMENTS = {s: {"asset_class": "crypto", "cost_type": "bp", "cost": 5.0, "session": "24h", "futures": False}
                      for s in CRYPTO_SYMBOLS}  # 5 bp per side (taker fee + slippage); funding ignored
CRYPTO_VOL_LOOKBACK = 20                  # filter A: average volume of the previous 20 candles
CRYPTO_VOL_MULTS = [1.5, 2.0]             # filter A: the only setting allowed to change on development data
CRYPTO_VOL_DEFAULT = 1.5                  # kept unless 2.0 wins by the pre-registered rule
CRYPTO_MIN_TRADES_FOR_CHOICE = 100        # 2.0 needs >= 100 development trades to be chosen
CRYPTO_B_ALONE_WINDOW = 5                 # test 1 "B alone": delta sum over the event candle + 4 before
CRYPTO_RANDOM_PER_EVENT = 20              # random baseline draws per event / setup
CRYPTO_N_CHARTS = 10                      # charts per version


def instrument(symbol: str) -> dict:
    """Settings for any symbol: the brief's instruments or the crypto perpetuals."""
    return INSTRUMENTS.get(symbol) or CRYPTO_INSTRUMENTS[symbol]

# ---------------------------------------------------------------------------
# Versions to compare  [9]  (the JeaFx faithful version is the defaults above)
# ---------------------------------------------------------------------------
GRID = {
    "bos_rule": ["wick", "close", "strong_close"],
    "require_imbalance": [True, False],
    "use_htf_context": [True, False],
    "target_mode": ["4h", "2r", "1h_hh"],
    "use_liquidity_sweep": [False, True],
    "use_breakeven": [False, True],
}

# ---------------------------------------------------------------------------
# Validation tests  [10]
# ---------------------------------------------------------------------------
RANDOM_WALK_VOL_SOURCE = "EURUSD=X"  # random walk uses this symbol's average 1h volatility
RANDOM_WALK_BARS = 12_000            # length of each fake 1h series (~2 years of forex hours)
RANDOM_WALK_RUNS = 40                # number of independent fake series (more trades = tighter test)
RANDOM_WALK_STEPS_PER_HOUR = 60      # minute steps inside each fake hour, so highs/lows look realistic
TRUNCATION_POINTS = [0.5]            # truncation test cuts each symbol's data at this fraction
RANDOM_SEED = 42                     # fixed seed so tests are reproducible
N_VISUAL_TRADE_CHARTS = 20           # random trades drawn for the visual check

# ---------------------------------------------------------------------------
# Development / holdout and settings search  [11]
# ---------------------------------------------------------------------------
DEV_FRACTION = 0.60              # first 60% of each symbol = development, last 40% = holdout
SEARCH_ZIGZAG_ATR = [1.5, 2.0, 3.0]
SEARCH_BODY_RANGE = [0.50, 0.60, 0.70]
SEARCH_BODY_AVG_MULT = [1.2, 1.5, 2.0]
SEARCH_MIN_ROOM_R = [1.5, 2.0, 3.0]
SELECT_MIN_TRADES = 100          # chosen setting needs at least 100 pooled trades
SELECT_MIN_POSITIVE_SHARE = 0.5  # ...and positive average R on at least half of the symbols

# ---------------------------------------------------------------------------
# Reporting  [13]
# ---------------------------------------------------------------------------
BOOTSTRAP_SAMPLES = 10_000       # resamples for the 95% confidence interval of average R
CONFIDENCE_LEVEL = 0.95          # confidence interval width
SESSIONS_UTC = {                 # entry session buckets, hours in UTC [start, end)
    "asia": (0, 7),
    "london": (7, 13),
    "new_york": (13, 21),
    "late": (21, 24),
}
