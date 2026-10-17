"""Basic indicators. Every value at row i uses only candles up to and including row i."""
import numpy as np
import pandas as pd


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range = max(high - low, |high - previous close|, |low - previous close|)."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """ATR(period) = simple average of the true range over the last `period` closed candles [5.1].
    The value on row i includes candle i, so it is known only once candle i has closed."""
    return true_range(df).rolling(period, min_periods=period).mean()
