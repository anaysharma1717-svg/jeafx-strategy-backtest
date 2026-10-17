"""Reversal shape v2 checks on synthetic data only (no real data is touched before the single run)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import engine, setups  # noqa: E402
from jeafx.v2 import V2Planner  # noqa: E402

import pytest  # noqa: E402

import config  # noqa: E402

V2 = engine.jeafx_variant(use_htf_context=False, target_mode="v2", max_wait=20, cancel_on_target_touch=True)


@pytest.fixture(autouse=True)
def looser_thresholds(monkeypatch):
    """Pre-registered thresholds make v2 shapes very rare in random data, so these code-path tests use
    looser numbers (same code). The real run uses the pre-registered values in config.py."""
    monkeypatch.setattr(config, "V2_TREND_SWINGS", 2)
    monkeypatch.setattr(config, "V2_MAJOR_ZIGZAG_ATR", 3.0)
    monkeypatch.setattr(config, "V2_TREND_MIN_RALLY_ATR", 2.0)
    monkeypatch.setattr(config, "V2_MIN_TARGET_R", 1.0)


def trending_random(n=40000, seed=11):
    """Random walk with slowly changing drift so long trends (and v2 shapes) actually occur."""
    rng = np.random.default_rng(seed)
    drift = np.repeat(rng.normal(0, 0.0004, n // 200 + 1), 200)[:n]
    k = 12
    steps = rng.normal(0, 0.0012 / np.sqrt(k), (n, k)) + drift[:, None] / k
    path = 1.1 * np.exp(np.cumsum(steps.ravel())).reshape(n, k)
    o = np.r_[1.1, path[:-1, -1]]
    t = pd.date_range("2015-01-05", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": o, "high": np.maximum(path.max(1), o),
                         "low": np.minimum(path.min(1), o), "close": path[:, -1]})


def run(df, cost="realistic"):
    m = engine.Market("EURUSD=X", df)
    p = V2Planner(m.df)
    tr, lg = engine.run(m, V2, cost, planner=p)
    return tr, lg, p


def test_v2_finds_setups_and_trade_levels_are_consistent():
    tr, lg, p = run(trending_random())
    assert len(p.records) > 5, "synthetic data should contain some v2 shapes"
    for r in p.records:
        sg = 1 if r["side"] == "long" else -1
        assert sg * (r["entry"] - r["stop"]) > 0                     # stop on the right side
        assert sg * (r["target"] - r["entry"]) >= config.V2_MIN_TARGET_R * sg * (r["entry"] - r["stop"]) - 1e-12
        assert sg * (r["entry"] - r["stop"]) >= r["atr"] - 1e-12      # min stop 1 ATR
        highs = [x[1] for x in r["trend_highs"]]
        lows = [x[1] for x in r["trend_lows"]]
        if r["side"] == "short":                                     # prior uptrend
            assert all(np.diff(highs) > 0) and all(np.diff(lows) > 0)
        else:                                                        # prior downtrend
            assert all(np.diff(highs) < 0) and all(np.diff(lows) < 0)


def test_v2_mirror():
    df = trending_random()
    a, _, _ = run(df)
    b, _, _ = run(setups.mirror(df))
    assert len(a) == len(b) > 0
    assert (a.side.map({"long": "short", "short": "long"}).values == b.side.values).all()
    assert np.allclose(a.entry_price, -b.entry_price) and np.allclose(a.r_after_costs, b.r_after_costs)


def test_v2_truncation():
    df = trending_random()
    cut = len(df) // 2
    a, _, _ = run(df)
    b, _, _ = run(df.iloc[:cut].copy())
    a = a[a.exit_idx < cut - 1].reset_index(drop=True)
    b = b[(b.exit_reason != "data_end") & (b.exit_idx < cut - 1)].reset_index(drop=True)
    cols = ["side", "bos_idx", "entry_idx", "exit_idx", "entry_price", "stop", "target", "exit_reason", "r_after_costs"]
    assert len(a) > 0
    pd.testing.assert_frame_equal(a[cols], b[cols])
