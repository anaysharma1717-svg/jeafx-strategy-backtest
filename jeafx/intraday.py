"""3-minute data, 15-minute context candles and the New York session (results/btc3m_PREREGISTRATION.md)."""
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config
from jeafx.crypto import add_flow

STEP = pd.Timedelta(minutes=3)
CTX = pd.Timedelta(minutes=15)
DIR_3M = config.CRYPTO_DATA_DIR + "_3m"


def load_3m(sym: str):
    """Clean 3m candles (brief section 4 cleaning) with volume / delta / CVD columns. Returns (df, counts)."""
    raw = pd.read_csv(os.path.join(DIR_3M, f"{sym}.csv"))
    df = raw.copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    counts = {"rows_in": len(df)}
    n = len(df)
    df = df.dropna(subset=["time", "open", "high", "low", "close"])
    counts["dropped_missing"] = n - len(df)
    n = len(df)
    df = df[df["high"] >= df["low"]]
    counts["dropped_high_below_low"] = n - len(df)
    n = len(df)
    df = df[df["high"] > df["low"]]
    counts["dropped_zero_range"] = n - len(df)
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    df["close_time"] = df["time"] + STEP
    return add_flow(df), counts


def build_ctx(df: pd.DataFrame) -> pd.DataFrame:
    """15-minute candles from 3m candles, 00:00-UTC-anchored buckets, closed at bucket start + 15m."""
    d = df.assign(bucket=df["time"].dt.floor("15min"))
    g = d.groupby("bucket", sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "n_1h": g.size(),
                        "first_1h": g["time"].first(), "last_1h": g["time"].last()}).reset_index()
    out = out.rename(columns={"bucket": "time"})
    out["close_time"] = out["time"] + CTX
    if len(out) and out["close_time"].iloc[-1] > df["close_time"].iloc[-1]:
        out = out.iloc[:-1]            # last bucket may still be forming
    return out[["time", "close_time", "open", "high", "low", "close", "n_1h", "first_1h", "last_1h"]].reset_index(drop=True)


@dataclass
class Session:
    in_session: np.ndarray
    sess_end: np.ndarray


def ny_session(df: pd.DataFrame) -> Session:
    """09:30-16:00 America/New_York, Monday-Friday. sess_end[i] = index of the last in-session candle of the same
    session (the 15:57 candle), -1 outside the session."""
    local = df["time"].dt.tz_convert("America/New_York")
    mins = local.dt.hour * 60 + local.dt.minute
    ins = ((local.dt.weekday < 5) & (mins >= 9 * 60 + 30) & (mins < 16 * 60)).to_numpy()
    end = np.full(len(df), -1, dtype=np.int64)
    idx = np.nonzero(ins)[0]
    if len(idx):
        day = local.dt.date.to_numpy()[idx]
        last = pd.Series(idx).groupby(day).transform("max").to_numpy()
        end[idx] = last
    return Session(ins, end)
