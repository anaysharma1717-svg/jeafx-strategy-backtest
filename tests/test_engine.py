"""Section 10 hand-made patterns and the long/short mirror test for the engine."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import engine, setups  # noqa: E402
from jeafx.indicators import atr  # noqa: E402


def frame(rows):
    a = np.asarray(rows, float)
    t = pd.date_range("2024-01-01", periods=len(a), freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3]})


def long_pattern(wick_only=False):
    """Downtrend, rally (swing high), drop to an origin low on a bearish candle, strong close above
    the swing high leaving an imbalance, pullback into the zone, rally to the target."""
    rows, p = [], 120.0
    for _ in range(30):                                   # downtrend
        rows.append([p, p + 0.3, p - 1.0, p - 0.7]); p -= 0.7
    for _ in range(5):                                    # rally -> swing high
        rows.append([p, p + 1.0, p - 0.3, p + 0.7]); p += 0.7
    swing_high = max(r[1] for r in rows[-5:])
    for _ in range(6):                                    # drop
        rows.append([p, p + 0.3, p - 1.0, p - 0.7]); p -= 0.7
    rows.append([p, p + 0.2, p - 0.6, p - 0.3])           # bearish origin candle (lowest low)
    origin_high, origin_low = p + 0.2, p - 0.6
    p -= 0.3
    rows.append([p, p + 0.9, p - 0.1, p + 0.8]); k_high = p + 0.9; p += 0.8   # candle k
    bos_idx = len(rows)
    if wick_only:
        rows.append([p, swing_high + 1.0, p - 0.1, p + 0.5]); p += 0.5
    else:
        rows.append([p, swing_high + 1.5, p - 0.05, swing_high + 1.4]); p = swing_high + 1.4
    rows.append([p, p + 0.5, k_high + 0.5, p + 0.3]); p += 0.3                 # k+2 -> imbalance
    for _ in range(3):
        rows.append([p, p + 0.3, p - 0.2, p + 0.1]); p += 0.1
    while p - 0.6 > origin_high:                          # pullback towards the zone
        rows.append([p, p + 0.1, p - 0.6, p - 0.5]); p -= 0.5
    rows.append([p, p + 0.1, origin_high - 0.05, origin_high + 0.1])           # touch -> fill
    fill_idx = len(rows) - 1
    p = origin_high + 0.1
    for _ in range(12):                                   # rally to target
        rows.append([p, p + 1.1, p - 0.1, p + 1.0]); p += 1.0
    df = frame(rows)
    exp = {"origin_low": origin_low, "origin_high": origin_high, "bos_idx": bos_idx, "fill_idx": fill_idx}
    return df, exp


BASIC = dict(use_htf_context=False, target_mode="2r")


def run(df, cost="zero", **kw):
    m = engine.Market("EURUSD=X", df)
    return engine.run(m, engine.jeafx_variant(**{**BASIC, **kw}), cost)


def test_hand_made_long():
    df, e = long_pattern()
    tr, log = run(df)
    assert len(tr) == 1
    t = tr.iloc[0]
    a = atr(df, 14).iloc[e["bos_idx"]]
    exp_stop = e["origin_low"] - 0.1 * a
    exp_entry = e["origin_high"]
    assert t.side == "long" and t.bos_idx == e["bos_idx"] and t.setup_type == "reversal"
    assert t.zone_bottom == pytest.approx(e["origin_low"]) and t.zone_top == pytest.approx(e["origin_high"])
    assert t.entry_idx == e["fill_idx"] and t.entry_price == pytest.approx(exp_entry)
    assert t.stop == pytest.approx(exp_stop)
    assert t.target == pytest.approx(exp_entry + 2 * (exp_entry - exp_stop))
    assert t.exit_reason == "target" and t.r_before_costs == pytest.approx(2.0)


def test_hand_made_short_is_mirror():
    df, e = long_pattern()
    tr, _ = run(setups.mirror(df))
    assert len(tr) == 1
    t = tr.iloc[0]
    assert t.side == "short" and t.entry_idx == e["fill_idx"]
    assert t.entry_price == pytest.approx(-e["origin_high"])
    assert t.zone_top == pytest.approx(-e["origin_low"]) and t.zone_bottom == pytest.approx(-e["origin_high"])
    assert t.exit_reason == "target" and t.r_before_costs == pytest.approx(2.0)


def test_wick_only_break_does_not_trade():
    df, e = long_pattern(wick_only=True)
    for rule in ("strong_close", "close"):
        tr, log = run(df, bos_rule=rule)
        assert e["bos_idx"] not in set(log["bos_idx"])                 # not even seen as a break
        assert len(tr) == 0 or (tr["side"] == "long").sum() == 0
    _, log = run(df, bos_rule="wick")                                  # the comparison rule does see it
    assert ((log["bos_idx"] == e["bos_idx"]) & (log["side"] == "long")).any()


def test_realistic_cost_needs_trade_through():
    df, e = long_pattern()
    df.loc[e["fill_idx"], "low"] = e["origin_high"] - 0.00001     # touch but not through by the cost
    tr, log = run(df, "realistic")
    assert len(tr) == 0
    assert "touched_no_fill" in set(log["status"])


def test_gap_fill_uses_planned_risk():
    """Bug found in the visual check: a candle opening below the limit fills at the open, but R must
    still be measured against the planned risk (limit - stop), not the smaller fill - stop."""
    df, e = long_pattern()
    j = e["fill_idx"]
    lim = e["origin_high"]
    gap_open = lim - 0.3                                   # opens below the limit, above the stop
    df.loc[j, ["open", "low"]] = [gap_open, gap_open - 0.05]
    tr, _ = run(df)
    t = tr.iloc[0]
    a = atr(df, 14).iloc[e["bos_idx"]]
    planned = lim - (e["origin_low"] - 0.1 * a)
    assert t.entry_price == pytest.approx(gap_open)
    assert t.risk_price == pytest.approx(planned)
    assert t.target == pytest.approx(lim + 2 * planned)
    assert t.r_before_costs == pytest.approx((t.exit_price - gap_open) / planned)


def test_change1_cancel_when_target_touched_first():
    df, e = long_pattern()           # after the BoS price runs far above entry + 2R before pulling back
    tr, log = run(df, cancel_on_target_touch=True)
    assert len(tr) == 0
    assert (log.loc[log.bos_idx == e["bos_idx"], "status"] == "target_before_fill").all()


def test_change1_shorter_wait_expires():
    df, e = long_pattern()
    wait = e["fill_idx"] - e["bos_idx"] - 1          # one candle too short to reach the fill
    tr, log = run(df, max_wait=wait)
    assert len(tr) == 0 and "expired" in set(log["status"])


def test_change2_skip_gap_beyond_zone_and_min_stop():
    df, e = long_pattern()
    j = e["fill_idx"]
    df.loc[j, ["open", "low"]] = [e["origin_low"] - 0.05, e["origin_low"] - 0.08]   # opens below zone bottom
    tr, _ = run(df)
    assert len(tr) == 1                                       # original rules: fill at the open
    tr, log = run(df, skip_gap_beyond_zone=True)
    assert len(tr) == 0 and "gap_beyond_zone" in set(log["status"])
    df, e = long_pattern()
    tr, _ = run(df, min_stop_atr=1.0)
    a = atr(df, 14).iloc[e["bos_idx"]]
    assert tr.iloc[0].entry_price - tr.iloc[0].stop >= 1.0 * a - 1e-9


def test_mfe_mae_of_target_trade():
    df, e = long_pattern()
    t = run(df)[0].iloc[0]
    assert t.mfe_r >= 2.0 - 1e-9 and 0 <= t.mae_r < 1.0


def random_market(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    c = 1.10 + np.cumsum(rng.normal(0, 0.0012, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.0002, n)
    return frame(np.c_[o, np.maximum(o, c) + rng.uniform(0, 0.001, n),
                       np.minimum(o, c) - rng.uniform(0, 0.001, n), c])


def test_mirrored_series_gives_mirrored_trades():
    df = random_market()
    a, _ = engine.run(engine.Market("EURUSD=X", df), engine.jeafx_variant(), "realistic")
    b, _ = engine.run(engine.Market("EURUSD=X", setups.mirror(df)), engine.jeafx_variant(), "realistic")
    assert len(a) == len(b) > 5
    assert (a.side.map({"long": "short", "short": "long"}).values == b.side.values).all()
    assert (a.entry_idx.values == b.entry_idx.values).all() and (a.exit_reason.values == b.exit_reason.values).all()
    assert np.allclose(a.entry_price, -b.entry_price) and np.allclose(a.r_after_costs, b.r_after_costs)
