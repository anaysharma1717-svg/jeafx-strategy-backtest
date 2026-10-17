"""Hand checks for the zigzag and structure state."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx.structure import find_swings, structure_state, attach_4h  # noqa: E402


def make(closes, spread=0.5):
    """Candles whose open = previous close, high/low = body +/- spread. Constant true range."""
    closes = np.asarray(closes, float)
    opens = np.r_[closes[0], closes[:-1]]
    t = pd.date_range("2024-01-01", periods=len(closes), freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": opens, "close": closes,
                         "high": np.maximum(opens, closes) + spread,
                         "low": np.minimum(opens, closes) - spread,
                         "close_time": t + pd.Timedelta(hours=1)})


def test_swings_alternate_and_confirm_later():
    # up 20, down 20, up 30, down 10 ... steps of 1 => true range ~2, ATR ~2, 2xATR ~4
    path = list(np.arange(100, 120)) + list(np.arange(120, 100, -1)) + list(np.arange(100, 130)) + list(np.arange(130, 118, -1))
    df = make(path)
    sw = find_swings(df, mult=2.0, atr_period=3)
    kinds = sw["kind"].tolist()
    assert all(kinds[i] != kinds[i + 1] for i in range(len(kinds) - 1))  # alternate
    assert (sw["confirm_idx"] > sw["idx"]).all()                          # usable only later
    first_high = sw[sw.kind == "high"].iloc[0]
    assert first_high.price == df["high"].iloc[19:21].max()               # exact top of the first leg


def test_no_lookahead_truncation():
    rng = np.random.default_rng(0)
    df = make(100 + np.cumsum(rng.normal(0, 1, 600)))
    full = find_swings(df, 2.0, 14)
    part = find_swings(df.iloc[:300].copy(), 2.0, 14)
    known = full[full["confirm_idx"] < 300].reset_index(drop=True)
    pd.testing.assert_frame_equal(known, part.reset_index(drop=True))


def test_structure_states():
    df = make(np.zeros(10) + 100)
    sw = pd.DataFrame([("high", 1, 10.0, 2), ("low", 3, 5.0, 4), ("high", 5, 12.0, 6), ("low", 7, 7.0, 8)],
                      columns=["kind", "idx", "price", "confirm_idx"])
    st = structure_state(df, sw)
    assert st["structure"].iloc[7] == "ranging"   # only one low confirmed so far
    assert st["structure"].iloc[8] == "bullish"   # HH (12>10) and HL (7>5)


def test_attach_4h_uses_only_closed_candles():
    t1 = pd.date_range("2024-01-01", periods=8, freq="1h", tz="UTC")
    h1 = pd.DataFrame({"time": t1, "close_time": t1 + pd.Timedelta(hours=1)})
    t4 = pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC")
    h4 = pd.DataFrame({"close_time": t4 + pd.Timedelta(hours=4), "v": [1, 2]})
    m = attach_4h(h1, h4, ["v"])
    assert m["h4_v"].isna().iloc[:3].all()        # 00-03h candles: first 4h not closed yet
    assert m["h4_v"].iloc[3] == 1                 # 03:00 candle closes at 04:00 with the 4h candle
    assert m["h4_v"].iloc[7] == 2
