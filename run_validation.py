"""Step 7: random walk test and truncation test  [BRIEF section 10].

Random walk: fake EUR/USD-like hourly prices with no pattern in them. The JeaFx version with
realistic costs should lose about the costs (average R before costs near 0). A clearly positive
result would mean a bug.

Truncation: run on data up to the middle, then on all data. Every trade that closed before the cut
must be identical in both runs. Any difference means future data leaked in.

Usage: py run_validation.py
"""
import os

import numpy as np
import pandas as pd

import config
from jeafx import data, engine, stats


# ---------------------------------------------------------------------------
def eurusd_hourly_sigma():
    df = data.load_symbol(config.RANDOM_WALK_VOL_SOURCE)
    r = np.log(df["close"]).diff().dropna()
    return float(r.std()), float(df["close"].iloc[-1])


def fake_market(n_hours, sigma_h, start_price, rng):
    """Random walk built from minute steps; each hour's OHLC comes from its 60 minutes."""
    k = config.RANDOM_WALK_STEPS_PER_HOUR
    steps = rng.normal(0, sigma_h / np.sqrt(k), size=n_hours * k)
    path = start_price * np.exp(np.cumsum(steps)).reshape(n_hours, k)
    prev_close = np.r_[start_price, path[:-1, -1]]
    o = prev_close
    h = np.maximum(path.max(axis=1), o)
    l = np.minimum(path.min(axis=1), o)
    c = path[:, -1]
    t = pd.date_range("2020-01-06", periods=n_hours, freq="1h", tz="UTC")
    return pd.DataFrame({"time": t, "open": o, "high": h, "low": l, "close": c,
                         "close_time": t + pd.Timedelta(hours=1)})


def random_walk_test():
    sigma, price = eurusd_hourly_sigma()
    rng = np.random.default_rng(config.RANDOM_SEED)
    all_tr = []
    for k in range(config.RANDOM_WALK_RUNS):
        df = fake_market(config.RANDOM_WALK_BARS, sigma, price, rng)
        tr, _ = engine.run(engine.Market(config.RANDOM_WALK_VOL_SOURCE, df), engine.jeafx_variant(), "realistic")
        if len(tr):
            tr["run"] = k
            all_tr.append(tr)
    t = pd.concat(all_tr, ignore_index=True)
    t["cost_R"] = t["r_before_costs"] - t["r_after_costs"]
    t.to_csv(os.path.join(config.RESULTS_DIR, "validation_random_walk_trades.csv"), index=False)
    before = stats.summary(t, "r_before_costs")
    after = stats.summary(t, "r_after_costs")
    print(f"RANDOM WALK TEST  ({config.RANDOM_WALK_RUNS} fake series x {config.RANDOM_WALK_BARS} hours, "
          f"hourly sigma {sigma:.6f} from {config.RANDOM_WALK_VOL_SOURCE}, JeaFx version, realistic costs)")
    print(f"  trades: {len(t)}   win rate: {after['win_rate_%']}%")
    print(f"  avg R before costs: {before['avg_R']:+.3f}  95% CI [{before['ci95_low']:+.3f}, {before['ci95_high']:+.3f}]  t = {before['t_stat']}")
    print(f"  avg cost per trade: {t['cost_R'].mean():.3f} R   ->  expected avg R after costs ~ {-t['cost_R'].mean():+.3f}")
    print(f"  avg R after costs:  {after['avg_R']:+.3f}  95% CI [{after['ci95_low']:+.3f}, {after['ci95_high']:+.3f}]  t = {after['t_stat']}")
    verdict = "PASS (no edge found in random data)" if before["ci95_low"] <= 0 else "FAIL: positive edge on random data -> bug"
    print(f"  verdict: {verdict}")
    print("  exit reasons:", t["exit_reason"].value_counts().to_dict())
    return before, after


# ---------------------------------------------------------------------------
KEY_COLS = ["side", "bos_idx", "entry_idx", "exit_idx", "entry_price", "stop", "target",
            "exit_price", "exit_reason", "r_before_costs", "r_after_costs", "context_reason", "target_type"]

TRUNC_VARIANTS = {
    "jeafx": engine.jeafx_variant(),
    "close_2r_noctx": engine.jeafx_variant(bos_rule="close", target_mode="2r", use_htf_context=False),
    "1h_hh_be_sweep": engine.jeafx_variant(target_mode="1h_hh", use_breakeven=True, use_liquidity_sweep=True),
}


def truncation_test():
    rows = []
    for sym in config.INSTRUMENTS:
        full_df = data.load_symbol(sym)
        for frac in config.TRUNCATION_POINTS:
            cut = int(len(full_df) * frac)
            m_full = engine.Market(sym, full_df)
            m_cut = engine.Market(sym, full_df.iloc[:cut].copy())
            for name, v in TRUNC_VARIANTS.items():
                a, _ = engine.run(m_full, v, "realistic")
                b, _ = engine.run(m_cut, v, "realistic")
                a = a[a["exit_idx"] < cut - 1] if len(a) else a
                b = b[(b["exit_reason"] != "data_end") & (b["exit_idx"] < cut - 1)] if len(b) else b
                same = len(a) == len(b) and (len(a) == 0 or
                       a[KEY_COLS].reset_index(drop=True).equals(b[KEY_COLS].reset_index(drop=True)))
                rows.append({"symbol": sym, "variant": name, "cut_time": full_df["time"].iloc[cut],
                             "trades_full_before_cut": len(a), "trades_truncated": len(b), "identical": same})
    r = pd.DataFrame(rows)
    r.to_csv(os.path.join(config.RESULTS_DIR, "validation_truncation.csv"), index=False)
    print("\nTRUNCATION TEST  (cut each symbol at 50% of its data; compare trades closed before the cut)")
    print(r.groupby("variant").agg(symbols=("symbol", "count"), identical=("identical", "sum"),
                                   trades_compared=("trades_full_before_cut", "sum")).to_string())
    bad = r[~r["identical"]]
    print("  verdict:", "PASS (no future data leaks)" if bad.empty else "FAIL:\n" + bad.to_string(index=False))


if __name__ == "__main__":
    random_walk_test()
    truncation_test()
