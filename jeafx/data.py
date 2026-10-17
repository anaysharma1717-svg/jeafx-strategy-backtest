"""Data loading, cleaning, 4h candle building and the data report  [BRIEF section 4].

Conventions used everywhere in the project:
- Every candle row has `time` (UTC start of the candle) and `close_time` (UTC moment it has closed).
- A candle's information may only be used by another candle whose close_time is >= this close_time.
"""
import os
from datetime import timedelta

import numpy as np
import pandas as pd

import config
from jeafx.indicators import atr

ONE_HOUR = pd.Timedelta(hours=1)
FOUR_HOURS = pd.Timedelta(hours=4)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def csv_path(symbol: str) -> str:
    return os.path.join(config.DATA_DIR, f"{symbol}.csv")


def download_yahoo(symbol: str) -> pd.DataFrame:
    """Download 1h candles from Yahoo (about 730 days). Raw, unadjusted prices."""
    import yfinance as yf

    tk = yf.Ticker(symbol)
    raw = tk.history(period=config.YF_PERIOD, interval=config.YF_INTERVAL, auto_adjust=False)
    if raw is None or raw.empty:
        # Yahoo sometimes rejects exactly 730d; ask for one day less.
        end = pd.Timestamp.now(tz="UTC")
        raw = tk.history(start=end - timedelta(days=729), end=end,
                         interval=config.YF_INTERVAL, auto_adjust=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    df = raw.reset_index()
    time_col = "Datetime" if "Datetime" in df.columns else df.columns[0]
    df = df.rename(columns={time_col: "time", "Open": "open", "High": "high",
                            "Low": "low", "Close": "close"})
    return df[config.CSV_COLUMNS]


def load_symbol(symbol: str, refresh: bool = False) -> pd.DataFrame:
    """Return cleaned 1h candles. Uses data/SYMBOL.csv if present (your own file or the cache),
    otherwise downloads from Yahoo and saves the cache. refresh=True forces a new download."""
    path = csv_path(symbol)
    if os.path.exists(path) and not refresh:
        raw = pd.read_csv(path)
        missing = [c for c in config.CSV_COLUMNS if c not in raw.columns]
        if missing:
            raise ValueError(f"{path} is missing columns {missing}; need {config.CSV_COLUMNS}")
        raw = raw[config.CSV_COLUMNS]
    else:
        raw = download_yahoo(symbol)
        os.makedirs(config.DATA_DIR, exist_ok=True)
        out = raw.copy()
        out["time"] = pd.to_datetime(out["time"], utc=True)
        out.to_csv(path, index=False)
    df, _ = clean(raw)
    return df


def clean(raw: pd.DataFrame):
    """UTC timestamps, drop missing values, high < low and zero range placeholders.
    Returns (clean_df, counts_of_dropped_rows)."""
    df = raw.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    counts = {"rows_in": len(df)}

    n = len(df)
    df = df.dropna(subset=config.CSV_COLUMNS)
    counts["dropped_missing"] = n - len(df)

    n = len(df)
    df = df[df["high"] >= df["low"]]
    counts["dropped_high_below_low"] = n - len(df)

    n = len(df)
    df = df[df["high"] > df["low"]]  # zero range candle = placeholder quote (e.g. weekend forex)
    counts["dropped_zero_range"] = n - len(df)

    n = len(df)
    df = df.sort_values("time").drop_duplicates("time", keep="last")
    counts["dropped_duplicate_time"] = n - len(df)

    # Candles whose open/close sit outside their own high-low range (bad prints). Counted only;
    # the brief does not say to drop or fix them, so they are reported for you to decide.
    bad = (df[["open", "close"]].max(axis=1) > df["high"]) | (df[["open", "close"]].min(axis=1) < df["low"])
    counts["open_close_outside_range"] = int(bad.sum())

    df = df.reset_index(drop=True)
    df["close_time"] = df["time"] + ONE_HOUR
    counts["rows_out"] = len(df)
    return df, counts


# ---------------------------------------------------------------------------
# histdata.com helper
# ---------------------------------------------------------------------------
def resample_histdata_1m(src_path: str, symbol: str) -> str:
    """Turn a histdata.com 1 minute ASCII file into data/SYMBOL.csv (1h candles, UTC).
    histdata format: 'YYYYMMDD HHMMSS;open;high;low;close;volume', time in EST without DST (UTC-5)."""
    m = pd.read_csv(src_path, sep=";", header=None,
                    names=["dt", "open", "high", "low", "close", "volume"])
    m["time"] = pd.to_datetime(m["dt"], format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)
    m["time"] = m["time"].dt.tz_localize("UTC")
    h = (m.set_index("time")
          .resample("1h", label="left", closed="left")
          .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
          .dropna()
          .reset_index())
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = csv_path(symbol)
    h[config.CSV_COLUMNS].to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# 4h candles
# ---------------------------------------------------------------------------
def _agg(group: pd.DataFrame) -> dict:
    return {
        "open": group["open"].iloc[0],
        "high": group["high"].max(),
        "low": group["low"].min(),
        "close": group["close"].iloc[-1],
        "n_1h": len(group),
        "first_1h": group["time"].iloc[0],
        "last_1h": group["time"].iloc[-1],
    }


def build_4h(df1h: pd.DataFrame, session: str) -> pd.DataFrame:
    """Build 4h candles from 1h candles.
    24h markets: buckets starting 00, 04, 08, 12, 16, 20 UTC; closed at bucket start + 4h.
    stock: per trading day, first 4 hourly candles = one 4h candle, the rest = the second;
           closed when its last 1h candle has closed.
    The final 4h candle is dropped if it may still be forming (not fully closed)."""
    d = df1h.copy()
    if session == "24h":
        d["bucket"] = d["time"].dt.floor("4h")  # floor is anchored at 00:00 UTC
        rows = []
        for b, g in d.groupby("bucket", sort=True):
            r = _agg(g)
            r["time"] = b
            r["close_time"] = b + FOUR_HOURS
            rows.append(r)
        out = pd.DataFrame(rows)
        # Last bucket: only keep it if the data clearly runs past its end.
        if len(out) and out["close_time"].iloc[-1] > df1h["close_time"].iloc[-1]:
            out = out.iloc[:-1]
    elif session == "stock":
        d["day"] = d["time"].dt.date  # US and Indian sessions both sit inside one UTC date
        d["pos"] = d.groupby("day").cumcount()
        d["half"] = np.where(d["pos"] < config.STOCK_FIRST_4H_CANDLES, 0, 1)
        rows = []
        for (day, half), g in d.groupby(["day", "half"], sort=True):
            r = _agg(g)
            r["time"] = g["time"].iloc[0]
            r["close_time"] = g["close_time"].iloc[-1]
            r["session_half"] = int(half)
            rows.append(r)
        out = pd.DataFrame(rows)
        # Last day's session may be unfinished: drop its candles if the day is the data's final day
        # and the day has fewer 1h candles than a normal full session.
        if len(out):
            full = d.groupby("day").size()
            normal = int(full.mode().iloc[0])
            last_day = d["day"].iloc[-1]
            if full.loc[last_day] < normal:
                out = out[out["time"].dt.date != last_day]
    else:
        raise ValueError(f"unknown session type {session}")
    cols = ["time", "close_time", "open", "high", "low", "close", "n_1h", "first_1h", "last_1h"]
    if "session_half" in out.columns:
        cols.append("session_half")
    return out[cols].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Futures roll gaps
# ---------------------------------------------------------------------------
def flag_roll_gaps(df: pd.DataFrame) -> pd.Series:
    """True on a candle whose open jumps more than ROLL_GAP_ATR_MULT x ATR from the previous close.
    ATR is taken from the previous candle (already closed), so no lookahead."""
    prev_atr = atr(df, config.ATR_PERIOD).shift(1)
    gap = (df["open"] - df["close"].shift(1)).abs()
    return (gap > config.ROLL_GAP_ATR_MULT * prev_atr).fillna(False)


# ---------------------------------------------------------------------------
# Data report
# ---------------------------------------------------------------------------
def _missing_hours(df: pd.DataFrame, session: str) -> int:
    t = df["time"]
    if session == "24h":
        full = pd.date_range(t.iloc[0], t.iloc[-1], freq="1h")
        missing = full.difference(pd.DatetimeIndex(t))
        # Normal weekend closure (Fri 21:00 UTC to Sun 22:00 UTC, allowing for DST) is not "missing".
        wd, hr = missing.dayofweek, missing.hour
        weekend = (wd == 5) | ((wd == 4) & (hr >= 20)) | ((wd == 6) & (hr < 23))
        return int((~weekend).sum())
    # stocks: count short sessions against the most common number of hourly candles per day
    per_day = df.groupby(df["time"].dt.date).size()
    normal = int(per_day.mode().iloc[0])
    return int((normal - per_day).clip(lower=0).sum())


def report_symbol(symbol: str, df: pd.DataFrame, counts: dict, n_4h: int, n_roll: int) -> dict:
    gaps = df["time"].diff()
    top = gaps.nlargest(3)
    largest = "; ".join(
        f"{df['time'].iloc[i - 1]:%Y-%m-%d %H:%M} -> {df['time'].iloc[i]:%Y-%m-%d %H:%M} ({g})"
        for i, g in zip(top.index, top.values.astype("timedelta64[h]"))
    )
    info = config.INSTRUMENTS[symbol]
    return {
        "symbol": symbol,
        "asset_class": info["asset_class"],
        "first": f"{df['time'].iloc[0]:%Y-%m-%d %H:%M}",
        "last": f"{df['time'].iloc[-1]:%Y-%m-%d %H:%M}",
        "candles_1h": len(df),
        "candles_4h": n_4h,
        "missing_hours": _missing_hours(df, info["session"]),
        "dropped_missing": counts.get("dropped_missing", 0),
        "dropped_high_below_low": counts.get("dropped_high_below_low", 0),
        "dropped_zero_range": counts.get("dropped_zero_range", 0),
        "open_close_outside_range": counts.get("open_close_outside_range", 0),
        "roll_gaps": n_roll if info["futures"] else "",
        "largest_gaps": largest,
    }
