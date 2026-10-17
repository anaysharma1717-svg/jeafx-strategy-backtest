"""New York session mask and the engine's session rules on synthetic 3-minute data."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import engine  # noqa: E402
from jeafx.intraday import build_ctx, ny_session  # noqa: E402


def frame(start, n, seed=1):
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, periods=n, freq="3min", tz="UTC")
    c = 100 + np.cumsum(rng.normal(0, 0.15, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"time": t, "close_time": t + pd.Timedelta(minutes=3), "open": o,
                         "high": np.maximum(o, c) + rng.uniform(0, .1, n), "low": np.minimum(o, c) - rng.uniform(0, .1, n),
                         "close": c})


def test_session_hours_follow_daylight_saving():
    winter = ny_session(frame("2024-01-08 00:00", 480))      # Monday, EST: 14:30-21:00 UTC
    summer = ny_session(frame("2024-07-08 00:00", 480))      # Monday, EDT: 13:30-20:00 UTC
    tw = frame("2024-01-08 00:00", 480)["time"][winter.in_session]
    ts = frame("2024-07-08 00:00", 480)["time"][summer.in_session]
    assert tw.iloc[0].strftime("%H:%M") == "14:30" and tw.iloc[-1].strftime("%H:%M") == "20:57"
    assert ts.iloc[0].strftime("%H:%M") == "13:30" and ts.iloc[-1].strftime("%H:%M") == "19:57"
    assert winter.in_session.sum() == 130                    # 6.5 hours of 3-minute candles
    sat = ny_session(frame("2024-01-13 00:00", 480))         # Saturday
    assert sat.in_session.sum() == 0


def test_engine_respects_session():
    df = frame("2024-01-01 00:00", 20 * 24 * 20, seed=3)     # 20 days of 3m candles
    m = engine.Market("BTCUSDT", df, df4=build_ctx(df))
    s = ny_session(m.df)
    v = engine.jeafx_variant(use_htf_context=False)
    tr, lg = engine.run(m, v, "zero", session=s)
    assert len(tr) > 0
    assert s.in_session[tr["bos_idx"]].all() and s.in_session[tr["entry_idx"]].all()
    assert s.in_session[tr["exit_idx"]].all()                 # flat by the session close
    sc = tr[tr["exit_reason"] == "session_close"]
    assert (sc["exit_idx"].to_numpy() == s.sess_end[sc["entry_idx"].to_numpy()]).all()
    assert (tr["exit_idx"].to_numpy() <= s.sess_end[tr["entry_idx"].to_numpy()]).all()
    assert {"outside_session"} <= set(lg["status"])
