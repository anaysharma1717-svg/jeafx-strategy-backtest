"""Run C of results/frozen_PREREGISTRATION.md: the brief's original JeaFx version + change 1 (stale-setup fix)
on the old holdout (last 40% of each Yahoo symbol). Run once.

Usage: py run_holdout_stale.py
"""
import os
import sys

import pandas as pd

import config
from jeafx import data, engine, grid, stats
from run_changes import C1

R = config.RESULTS_DIR
LOCK = os.path.join(R, "HOLDOUT_STALE_DONE.txt")


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Already run once (see {LOCK}).")
        return
    v = engine.jeafx_variant(**C1)
    trades = []
    for sym in config.INSTRUMENTS:
        df = data.load_symbol(sym)
        start = df["time"].iloc[int(len(df) * config.DEV_FRACTION)]
        m = engine.Market(sym, df)
        for c in config.COST_MODES:
            tr, _ = engine.run(m, v, c, trade_from=start)
            if len(tr):
                tr["cost"] = c
                trades.append(tr)
    with open(LOCK, "w") as f:
        f.write("Original version + change 1 run once on the Yahoo holdout (frozen_PREREGISTRATION.md, run C)\n")
    t = pd.concat(trades, ignore_index=True)
    t["asset_class"] = t["symbol"].map(lambda s: config.INSTRUMENTS[s]["asset_class"])
    t.to_csv(os.path.join(R, "holdout_stale_trades.csv"), index=False)
    rows = [{"cost": c, **stats.summary(t[t["cost"] == c])} for c in config.COST_MODES]
    s = pd.DataFrame(rows)
    s.to_csv(os.path.join(R, "holdout_stale_summary.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("C. ORIGINAL VERSION + STALE-SETUP FIX ON THE OLD HOLDOUT (last 40%, 21 Yahoo symbols)")
    print(s.to_string(index=False))
    real = t[t["cost"] == "realistic"]
    for by in ("asset_class", "symbol"):
        x = grid.table(real, [by])
        print(f"\nby {by} (realistic):")
        print(x[[by, "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "total_R"]].to_string(index=False))
    top = real.nlargest(3, "r_after_costs")
    print("\ntop 3 trades:", [(r.symbol, round(r.r_after_costs, 2)) for r in top.itertuples()],
          "| avg R without them:", round(real.drop(top.index)["r_after_costs"].mean(), 3))


if __name__ == "__main__":
    main()
