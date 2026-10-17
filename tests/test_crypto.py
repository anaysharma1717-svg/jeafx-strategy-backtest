"""Volume / CVD filter checks on synthetic data."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import engine  # noqa: E402
from jeafx.crypto import FlowFilter, add_flow  # noqa: E402


def flow_frame(n=60):
    t = pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({"time": t, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                       "volume": 10.0, "taker_buy_volume": 5.0})
    return df


def test_delta_cvd_and_volume_average():
    df = flow_frame()
    df.loc[30, ["volume", "taker_buy_volume"]] = [40.0, 35.0]          # big aggressive buying candle
    d = add_flow(df)
    assert d["delta"].iloc[30] == 30.0 and d["delta"].iloc[29] == 0.0
    assert d["vol_avg"].iloc[30] == 10.0                                # previous 20 candles only
    assert d["cvd"].iloc[-1] == 30.0


def test_filter_a_and_b():
    df = flow_frame()
    df.loc[30, ["volume", "taker_buy_volume"]] = [40.0, 35.0]
    df.loc[28, ["volume", "taker_buy_volume"]] = [10.0, 0.0]            # selling at the origin candle: delta -10
    f = FlowFilter(add_flow(df), True, True, 1.5)
    long_ = {"bos_idx": 30, "origin_candle_idx": 28, "side": "long"}
    short = {"bos_idx": 30, "origin_candle_idx": 28, "side": "short"}
    assert f.checks(long_) == {"a": True, "b": True}                    # delta +30, impulse 30 - 10 = +20
    assert f.checks(short) == {"a": True, "b": False}
    assert f(short) == "cvd"
    f2 = FlowFilter(add_flow(df), True, False, 5.0)                      # 40 < 5 x 10
    assert f2(long_) == "volume"


def test_keep_all_filter_equals_base():
    rng = np.random.default_rng(5)
    n = 5000
    c = 100 + np.cumsum(rng.normal(0, 0.8, n))
    o = np.r_[c[0], c[:-1]]
    t = pd.date_range("2021-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame({"time": t, "open": o, "high": np.maximum(o, c) + rng.uniform(0, .6, n),
                       "low": np.minimum(o, c) - rng.uniform(0, .6, n), "close": c})
    m = engine.Market("BTCUSDT", df)
    v = engine.jeafx_variant(use_htf_context=False)
    a, _ = engine.run(m, v, "realistic")
    b, _ = engine.run(m, v, "realistic", setup_filter=lambda s: "")
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)
