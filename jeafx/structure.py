"""Zigzag swings and market structure  [BRIEF 5.2, 5.3].

A swing high is the exact highest high reached before price falls at least mult x ATR below it.
A swing low is the exact lowest low reached before price rises at least mult x ATR above it.
The swing is drawn at its own candle but is usable only from its confirmation candle onward.

No lookahead: the loop walks forward one candle at a time and only uses candles up to the
current one. ATR on the confirmation candle includes that candle, which is known at its close.
Same-candle rule: if a candle makes a new extreme, it cannot also confirm that extreme
(we cannot know whether the high or the low came first inside the candle).
"""
import numpy as np
import pandas as pd

import config
from jeafx.indicators import atr

BULLISH, BEARISH, RANGING = "bullish", "bearish", "ranging"


def find_swings(df: pd.DataFrame, mult: float = None, atr_period: int = None) -> pd.DataFrame:
    """Return the alternating swings: kind ('high'/'low'), idx (swing candle), price,
    confirm_idx (candle that completed the mult x ATR move), plus their times."""
    mult = config.ZIGZAG_ATR_MULT if mult is None else mult
    atr_period = config.ATR_PERIOD if atr_period is None else atr_period
    hi = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    a = atr(df, atr_period).to_numpy()
    n = len(df)

    swings = []
    direction = 0            # 0 = no swing yet, +1 = last swing was a low (hunting a high), -1 = hunting a low
    max_v, max_i = -np.inf, -1
    min_v, min_i = np.inf, -1

    for i in range(n):
        new_max = hi[i] > max_v
        new_min = lo[i] < min_v
        if new_max:
            max_v, max_i = hi[i], i
        if new_min:
            min_v, min_i = lo[i], i
        if np.isnan(a[i]):
            continue
        dist = mult * a[i]

        if direction >= 0:   # could confirm a swing high
            high_ok = (not new_max) and lo[i] <= max_v - dist
        else:
            high_ok = False
        if direction <= 0:   # could confirm a swing low
            low_ok = (not new_min) and hi[i] >= min_v + dist
        else:
            low_ok = False

        if direction == 0 and high_ok and low_ok:
            # only possible before the first swing: take the older extreme first
            if max_i < min_i:
                low_ok = False
            else:
                high_ok = False

        if high_ok:
            swings.append(("high", max_i, max_v, i))
            direction = -1
            seg = lo[max_i + 1 : i + 1]
            j = int(np.argmin(seg))
            min_v, min_i = seg[j], max_i + 1 + j
            max_v, max_i = -np.inf, -1
        elif low_ok:
            swings.append(("low", min_i, min_v, i))
            direction = 1
            seg = hi[min_i + 1 : i + 1]
            j = int(np.argmax(seg))
            max_v, max_i = seg[j], min_i + 1 + j
            min_v, min_i = np.inf, -1

    out = pd.DataFrame(swings, columns=["kind", "idx", "price", "confirm_idx"])
    out["time"] = df["time"].to_numpy()[out["idx"]] if len(out) else []
    out["confirm_time"] = df["time"].to_numpy()[out["confirm_idx"]] if len(out) else []
    return out


def structure_state(df: pd.DataFrame, swings: pd.DataFrame) -> pd.DataFrame:
    """Per candle (as known at that candle's close): active and previous swing high/low and the
    structure state. Columns:
      sh, sh_idx, sh_prev   active swing high price, its candle, previous swing high price
      sl, sl_idx, sl_prev   same for lows
      structure             bullish / bearish / ranging
    """
    n = len(df)
    cols = {k: np.full(n, np.nan) for k in ["sh", "sh_idx", "sh_prev", "sl", "sl_idx", "sl_prev"]}
    by_confirm = {}
    for s in swings.itertuples(index=False):
        by_confirm.setdefault(s.confirm_idx, []).append(s)

    sh = sh_idx = sh_prev = sl = sl_idx = sl_prev = np.nan
    for i in range(n):
        for s in by_confirm.get(i, []):
            if s.kind == "high":
                sh_prev, sh, sh_idx = sh, s.price, s.idx
            else:
                sl_prev, sl, sl_idx = sl, s.price, s.idx
        cols["sh"][i], cols["sh_idx"][i], cols["sh_prev"][i] = sh, sh_idx, sh_prev
        cols["sl"][i], cols["sl_idx"][i], cols["sl_prev"][i] = sl, sl_idx, sl_prev

    out = pd.DataFrame(cols, index=df.index)
    bull = (out["sh"] > out["sh_prev"]) & (out["sl"] > out["sl_prev"])
    bear = (out["sh"] < out["sh_prev"]) & (out["sl"] < out["sl_prev"])
    out["structure"] = np.where(bull, BULLISH, np.where(bear, BEARISH, RANGING))  # NaN compare -> ranging
    return out


def analyse(df: pd.DataFrame, mult: float = None) -> tuple:
    """Convenience: ATR, swings and structure for one timeframe. Returns (df_with_cols, swings)."""
    d = df.copy()
    d["atr"] = atr(d, config.ATR_PERIOD)
    sw = find_swings(d, mult)
    st = structure_state(d, sw)
    return pd.concat([d, st], axis=1), sw


def attach_4h(df1h: pd.DataFrame, df4h: pd.DataFrame, cols: list, prefix: str = "h4_") -> pd.DataFrame:
    """For each 1h candle, attach values from the latest 4h candle that had fully closed by the
    time the 1h candle closed (4h close_time <= 1h close_time). No lookahead."""
    right = df4h[["close_time"] + cols].rename(columns={c: prefix + c for c in cols})
    right = right.rename(columns={"close_time": "h4_close_time"}).sort_values("h4_close_time")
    left = df1h.sort_values("close_time")
    merged = pd.merge_asof(left, right, left_on="close_time", right_on="h4_close_time",
                           direction="backward", allow_exact_matches=True)
    merged.index = df1h.index
    return merged
