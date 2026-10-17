"""Run A + B of results/frozen_PREREGISTRATION.md: the frozen version (changes 1+2+3) and its breakeven-at-+1R
variant on histdata.com 2015-2023 (7 pairs), plus the flip and forward-return tests. Run once.

Usage: py run_frozen.py
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
from jeafx import engine, stats
from run_changes import C1, C2, C3
from run_v2 import flip_trades, forward_returns, load

R = config.RESULTS_DIR
LOCK = os.path.join(R, "FROZEN_RUN_DONE.txt")
VERSIONS = {
    "frozen": engine.jeafx_variant(**C1, **C2, **C3),
    "frozen + breakeven at +1R": engine.jeafx_variant(**C1, **C2, **C3, use_breakeven=True, breakeven_trigger_r=1.0),
}


def _worker(sym):
    m = engine.Market(sym, load(sym))
    trades, setups_, flips = [], [], []
    for name, v in VERSIONS.items():
        for c in config.COST_MODES:
            tr, lg = engine.run(m, v, c)
            if len(tr):
                tr["version"], tr["cost"] = name, c
                trades.append(tr)
                if name == "frozen":
                    f = flip_trades(m.df, tr, c)
                    f["cost"] = c
                    flips.append(f)
            if name == "frozen" and c == "realistic":
                ok = lg[~lg["status"].str.startswith("filtered:")]
                setups_ = [{"symbol": sym, "bos_idx": int(r.bos_idx), "side": r.side} for r in ok.itertuples()]
    return (pd.concat(trades, ignore_index=True) if trades else pd.DataFrame(), setups_,
            pd.concat(flips, ignore_index=True) if flips else pd.DataFrame())


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Already run once (see {LOCK}).")
        return
    with ProcessPoolExecutor(max_workers=len(config.V2_PAIRS)) as ex:
        res = list(ex.map(_worker, config.V2_PAIRS))
    with open(LOCK, "w") as f:
        f.write("Frozen version + breakeven variant run once on histdata 2015-2023 (frozen_PREREGISTRATION.md)\n")
    tr = pd.concat([r[0] for r in res if len(r[0])], ignore_index=True)
    recs = [x for r in res for x in r[1]]
    flips = pd.concat([r[2] for r in res if len(r[2])], ignore_index=True)
    tr["year"] = pd.to_datetime(tr["entry_time"]).dt.year
    tr.to_csv(os.path.join(R, "frozen_hist_trades.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)
    cols = ["version", "cost", "group", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat",
            "ci_includes_0", "total_R", "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak"]

    rows = []
    for (ver, c), t in tr.groupby(["version", "cost"], sort=False):
        rows.append({"version": ver, "cost": c, "group": "ALL", **stats.summary(t)})
        for key in ("symbol", "year"):
            for g, x in t.groupby(key):
                rows.append({"version": ver, "cost": c, "group": f"{key}={g}", **stats.summary(x)})
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(R, "frozen_hist_summary.csv"), index=False)
    print("A. FROZEN VERSION ON HISTDATA 2015-2023 (7 pairs), pooled")
    print(summ[summ["group"] == "ALL"][cols].to_string(index=False))
    for ver in VERSIONS:
        x = summ[(summ["version"] == ver) & (summ["cost"] == "realistic") & (summ["group"] != "ALL")]
        print(f"\n{ver}, realistic costs, by pair and by year")
        print(x[cols[2:]].to_string(index=False))
    for ver in VERSIONS:
        t = tr[(tr["version"] == ver) & (tr["cost"] == "realistic")]
        los = t[t["r_after_costs"] < 0]
        print(f"\n{ver}: exits {t['exit_reason'].value_counts().to_dict()}; losers reaching +1R first "
              f"{100 * (los['mfe_r'] >= 1).mean():.1f}%, +0.5R {100 * (los['mfe_r'] >= 0.5).mean():.1f}%, "
              f"avg MFE of losers {los['mfe_r'].mean():.2f}R")

    # B1 flip
    frows = []
    for c in config.COST_MODES:
        x = flips[flips["cost"] == c]
        d = x["real_R"] - x["flipped_R"]
        lo, hi = stats.bootstrap_ci(d)
        frows.append({"cost": c, "trades": len(x), "avg_R_real": round(x["real_R"].mean(), 3),
                      "avg_R_flipped": round(x["flipped_R"].mean(), 3), "difference": round(d.mean(), 3),
                      "diff_ci95": f"{lo:+.3f}..{hi:+.3f}", "diff_t": round(stats.t_stat(d), 2),
                      "real_clearly_better": lo > 0, "flipped_clearly_better": hi < 0})
    fdf = pd.DataFrame(frows)
    fdf.to_csv(os.path.join(R, "frozen_hist_flip_test.csv"), index=False)
    print("\nB1. FLIP TEST (frozen version, same fill candle and price, opposite direction)")
    print(fdf.to_string(index=False))

    # B2 forward returns
    rng = np.random.default_rng(config.RANDOM_SEED)
    long_share = np.mean([r["side"] == "long" for r in recs])
    S, B = [], []
    for sym in config.V2_PAIRS:
        s, b = forward_returns(load(sym), [r for r in recs if r["symbol"] == sym], rng, long_share)
        S.append(s)
        B.append(b)
    S, B = pd.concat(S, ignore_index=True), pd.concat(B, ignore_index=True)
    wrows = []
    rng2 = np.random.default_rng(config.RANDOM_SEED)
    for k in config.V2_FORWARD_HORIZONS:
        s, b = S[f"fwd_{k}"].dropna().to_numpy(), B[f"fwd_{k}"].dropna().to_numpy()
        d = np.array([rng2.choice(s, len(s)).mean() - rng2.choice(b, len(b)).mean() for _ in range(5000)])
        slo, shi = stats.bootstrap_ci(s)
        wrows.append({"horizon_candles": k, "setups": len(s), "signal_mean_ATR": round(s.mean(), 3),
                      "signal_ci95": f"{slo:+.3f}..{shi:+.3f}", "random_mean_ATR": round(b.mean(), 3),
                      "difference": round(s.mean() - b.mean(), 3),
                      "diff_ci95": f"{np.quantile(d, .025):+.3f}..{np.quantile(d, .975):+.3f}"})
    wdf = pd.DataFrame(wrows)
    wdf.to_csv(os.path.join(R, "frozen_hist_forward_test.csv"), index=False)
    print("\nB2. FORWARD RETURNS after the BoS close, signal direction, ATR units (all setups that passed the rules)")
    print(wdf.to_string(index=False))

    # equity chart
    fig, ax = plt.subplots(figsize=(13, 6))
    for (ver, c), t in tr.groupby(["version", "cost"], sort=False):
        t = t.sort_values("exit_time")
        ax.plot(pd.to_datetime(t["exit_time"]), np.cumsum(t["r_after_costs"]), "--" if c == "zero" else "-",
                label=f"{ver} ({c})")
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_ylabel("cumulative R")
    ax.set_title("Frozen version on histdata 2015-2023, 7 forex pairs pooled (dashed = zero cost)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(config.CHARTS_DIR, "frozen_hist_equity.png"), dpi=110)
    print("\nsaved charts/frozen_hist_equity.png")


if __name__ == "__main__":
    main()
