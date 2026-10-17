"""No-lookahead check for the 4h context and target: cutting the data right after a setup's BoS
candle must give the same context and target as the full data."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jeafx import data, setups  # noqa: E402
from jeafx.context import HTF  # noqa: E402


def random_market(n=3000, seed=3):
    rng = np.random.default_rng(seed)
    c = 1.10 + np.cumsum(rng.normal(0, 0.001, n))
    o = np.r_[c[0], c[:-1]]
    t = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": o, "high": np.maximum(o, c) + rng.uniform(0, 0.0008, n),
                         "low": np.minimum(o, c) - rng.uniform(0, 0.0008, n), "close": c,
                         "close_time": t + pd.Timedelta(hours=1)})


def run(df, upto):
    d4 = data.build_4h(df, "24h")
    b = setups.find_breaks(df)
    htf = HTF(df, d4)
    res = []
    for _, s in b[b["valid"] & (b["bos_idx"] <= upto)].iterrows():
        c = htf.context(s)
        if c["context_reason"]:
            htf.claim(c["zone_id"])
        e, st, r = setups.order_levels(s)
        res.append((int(s.bos_idx), s.side, c["context_reason"], *htf.target_4h(s.side, e, r, int(s.bos_idx))))
    return res


def test_context_and_target_truncation():
    df = random_market()
    cut = 1800
    full = run(df, cut)
    part = run(df.iloc[:cut + 1].copy(), cut)
    assert len(full) > 20
    assert full == part
