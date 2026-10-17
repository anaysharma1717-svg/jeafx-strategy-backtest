"""Hand checks for imbalances, BoS rules, zones and the long/short mirror."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import setups  # noqa: E402


def frame(ohlc):
    a = np.asarray(ohlc, float)
    t = pd.date_range("2024-01-01", periods=len(a), freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3],
                         "close_time": t + pd.Timedelta(hours=1)})


def test_bullish_fvg_and_fill():
    df = frame([[10, 11, 9, 10.5], [10.5, 13, 10.4, 12.8], [12.8, 14, 12, 13.5],   # gap 11..12
                [13.5, 13.6, 11.5, 12], [12, 12.2, 10.9, 11]])                       # fully filled at idx 4
    f = setups.bullish_fvgs(df)
    assert len(f) == 1
    r = f.iloc[0]
    assert (r.k, r.form_idx, r.bottom, r.top, r.fill_idx) == (0, 2, 11, 12, 4)


def make_long_pattern(break_close_strong=True, wick_only=False):
    """Downtrend -> swing high -> drop to origin -> strong candle breaks the swing high with an FVG.
    Constant candle size keeps ATR predictable (~1.0)."""
    rows = []
    p = 120.0
    for _ in range(20):                          # warm-up downtrend
        rows.append([p, p + 0.3, p - 1.0, p - 0.7]); p -= 0.7
    for _ in range(5):                           # rally -> swing high
        rows.append([p, p + 1.0, p - 0.3, p + 0.7]); p += 0.7
    top = p
    for _ in range(6):                           # drop -> confirms swing high, makes origin low
        rows.append([p, p + 0.3, p - 1.0, p - 0.7]); p -= 0.7
    rows.append([p, p + 0.2, p - 0.6, p - 0.3]); p -= 0.3           # last bearish candle = origin
    rows.append([p, p + 0.9, p - 0.1, p + 0.8]); p += 0.8           # small up candle (k of FVG)
    k_high = rows[-1][1]
    if wick_only:
        rows.append([p, top + 1.0, p - 0.1, p + 0.5]); p += 0.5
    elif break_close_strong:
        rows.append([p, top + 1.5, p - 0.05, top + 1.4]); p = top + 1.4  # big candle closes above
    else:
        rows.append([p, top + 0.6, p - 2.0, top + 0.05]); p = top + 0.05
    rows.append([p, p + 0.5, k_high + 0.5, p + 0.3])                # k+2 low above k high -> FVG
    for _ in range(5):
        rows.append([p, p + 0.4, p - 0.4, p + 0.1])
    return frame(rows)


def test_strong_close_break_makes_valid_long():
    df = make_long_pattern(True)
    b = setups.find_breaks(df, "strong_close", {"zigzag": 2.0})
    longs = b[b.side == "long"]
    assert len(longs) == 1
    s = longs.iloc[0]
    assert s.reason == "" and s.valid
    assert s.zone_bottom == df["low"].iloc[int(s.origin_idx)]
    assert df["close"].iloc[int(s.origin_candle_idx)] < df["open"].iloc[int(s.origin_candle_idx)]


def test_wick_only_is_not_a_close_break():
    df = make_long_pattern(wick_only=True)
    assert (setups.find_breaks(df, "close", {"zigzag": 2.0}).side == "long").sum() == 0
    assert (setups.find_breaks(df, "wick", {"zigzag": 2.0}).side == "long").sum() == 1


def test_weak_close_uses_up_level():
    df = make_long_pattern(False)
    b = setups.find_breaks(df, "strong_close", {"zigzag": 2.0})
    longs = b[b.side == "long"]
    assert len(longs) == 1 and longs.iloc[0].reason == "weak_close" and not longs.iloc[0].valid


def test_mirror_gives_mirrored_setups():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 1, 1500))
    o = np.r_[c[0], c[:-1]]
    df = frame(np.c_[o, np.maximum(o, c) + rng.uniform(0.1, 1, 1500),
                     np.minimum(o, c) - rng.uniform(0.1, 1, 1500), c])
    a = setups.find_breaks(df, "strong_close")
    m = setups.find_breaks(setups.mirror(df), "strong_close")
    al = a[a.side == "long"].reset_index(drop=True)
    ms = m[m.side == "short"].reset_index(drop=True)
    assert len(al) == len(ms) > 0
    assert (al.bos_idx == ms.bos_idx).all()
    assert np.allclose(al.zone_top, -ms.zone_bottom) and np.allclose(al.zone_bottom, -ms.zone_top)
    assert (al.valid == ms.valid).all()
