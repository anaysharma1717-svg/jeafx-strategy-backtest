"""Step 8: every version on development data (first 60% of each symbol), zero and realistic costs.

Outputs (results/):
  dev_trades.csv.gz        every trade of every version (compact columns)
  dev_grid_summary.csv     section 13 metrics for each of the 144 grid versions x 2 cost settings
  dev_one_change.csv       JeaFx version vs. changing one rule at a time
  dev_filters.csv          what each filter removed and how the removed trades did
  dev_breakdowns.csv       JeaFx version split by symbol, asset class, side, setup, context, session
  dev_india_cash.csv       Indian cash stocks at 13 bp per side
charts/step8_equity_dev.png

Usage: py run_dev.py
"""
import os
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config
from jeafx import engine, grid, stats

R = config.RESULTS_DIR
JEAFX = grid.vname(engine.jeafx_variant())

ONE_CHANGE = {  # label -> overrides from the JeaFx version
    "JeaFx version": {},
    "break = wick": {"bos_rule": "wick"},
    "break = close": {"bos_rule": "close"},
    "imbalance off": {"require_imbalance": False},
    "4h context off": {"use_htf_context": False},
    "target = fixed 2R": {"target_mode": "2r"},
    "target = 1h higher high": {"target_mode": "1h_hh"},
    "liquidity sweep on": {"use_liquidity_sweep": True},
    "breakeven at +2R on": {"use_breakeven": True},
}


def show(df, title, cols=None):
    print(f"\n{title}")
    print((df[cols] if cols else df).to_string(index=False))


def main():
    t0 = time.time()
    syms = list(config.INSTRUMENTS)
    variants = grid.full_grid()
    extra = [engine.jeafx_variant(min_room_r=0.0, name="JeaFx no room check")]
    print(f"Running {len(variants)} grid versions + {len(extra)} extra x 2 costs x {len(syms)} symbols on dev data ...")
    tr = grid.run_many(syms, variants + extra, part="dev")
    tr.to_csv(os.path.join(R, "dev_trades.csv.gz"), index=False)
    print(f"done in {time.time() - t0:.0f}s, {len(tr)} trades in total")

    # ---- grid summary -------------------------------------------------------------------------
    summ = grid.table(tr, ["variant", "cost"])
    pos_syms = (tr.groupby(["variant", "cost", "symbol"])["r_after_costs"].mean() > 0).groupby(["variant", "cost"]).sum()
    summ["symbols_positive"] = summ.apply(lambda r: int(pos_syms.get((r["variant"], r["cost"]), 0)), axis=1)
    summ.to_csv(os.path.join(R, "dev_grid_summary.csv"), index=False)

    pd.set_option("display.width", 260, "display.max_columns", 40)
    cols = ["version", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "ci_includes_0",
            "total_R", "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak", "avg_hold_hours", "symbols_positive"]

    # ---- one change at a time -----------------------------------------------------------------
    rows = []
    for label, ov in ONE_CHANGE.items():
        name = grid.vname(engine.jeafx_variant(**ov))
        for c in ("zero", "realistic"):
            r = summ[(summ["variant"] == name) & (summ["cost"] == c)]
            rows.append({"version": label, "cost": c, **(r.iloc[0].to_dict() if len(r) else {"trades": 0})})
    one = pd.DataFrame(rows)
    one.to_csv(os.path.join(R, "dev_one_change.csv"), index=False)
    show(one, "JEAFX VERSION vs. CHANGING ONE RULE (dev data, all symbols pooled, R after costs)", cols)

    # ---- grid overview ------------------------------------------------------------------------
    g = summ[summ["variant"].isin([grid.vname(v) for v in variants])]
    print("\nFULL GRID OVERVIEW (144 versions; comparison only, NOT a search for the best one)")
    for c in ("zero", "realistic"):
        x = g[g["cost"] == c]
        print(f"  {c:9s}: versions with avg R > 0: {int((x['avg_R'] > 0).sum())}/{len(x)}   "
              f"with 95% CI fully above 0: {int((x['ci95_low'] > 0).sum())}   "
              f"median avg R: {x['avg_R'].median():+.3f}   range: {x['avg_R'].min():+.3f} .. {x['avg_R'].max():+.3f}")

    # ---- filters: what they removed -----------------------------------------------------------
    base = engine.jeafx_variant()
    filt = {
        "strong close (vs close)": grid.vname({**base, "bos_rule": "close"}),
        "imbalance required": grid.vname({**base, "require_imbalance": False}),
        "4h context rule": grid.vname({**base, "use_htf_context": False}),
        "room check 1.5R": "JeaFx no room check",
    }
    rows = []
    real = tr[tr["cost"] == "realistic"]
    kept = real[real["variant"] == JEAFX]
    kept_keys = set(zip(kept["symbol"], kept["side"], kept["bos_idx"]))
    for label, without in filt.items():
        w = real[real["variant"] == without]
        is_removed = [k not in kept_keys for k in zip(w["symbol"], w["side"], w["bos_idx"])]
        rem = w[is_removed]
        rows.append({"filter": label, "trades_without_filter": len(w), "trades_with_filter": len(kept),
                     "removed": len(rem),
                     "avg_R_kept": round(kept["r_after_costs"].mean(), 3) if len(kept) else np.nan,
                     "avg_R_removed": round(rem["r_after_costs"].mean(), 3) if len(rem) else np.nan,
                     "removed_ci95": "%+.3f..%+.3f" % stats.bootstrap_ci(rem["r_after_costs"]) if len(rem) > 1 else "",
                     "helps?": (len(rem) > 0 and rem["r_after_costs"].mean() < kept["r_after_costs"].mean())})
    # the optional liquidity sweep filter removes trades from the JeaFx version
    sw = real[real["variant"] == grid.vname({**base, "use_liquidity_sweep": True})]
    sw_keys = set(zip(sw["symbol"], sw["side"], sw["bos_idx"]))
    rem = kept[[k not in sw_keys for k in zip(kept["symbol"], kept["side"], kept["bos_idx"])]]
    rows.append({"filter": "liquidity sweep (optional)", "trades_without_filter": len(kept), "trades_with_filter": len(sw),
                 "removed": len(rem), "avg_R_kept": round(sw["r_after_costs"].mean(), 3) if len(sw) else np.nan,
                 "avg_R_removed": round(rem["r_after_costs"].mean(), 3) if len(rem) else np.nan,
                 "removed_ci95": "%+.3f..%+.3f" % stats.bootstrap_ci(rem["r_after_costs"]) if len(rem) > 1 else "",
                 "helps?": (len(rem) > 0 and len(sw) > 0 and rem["r_after_costs"].mean() < sw["r_after_costs"].mean())})
    fl = pd.DataFrame(rows)
    fl.to_csv(os.path.join(R, "dev_filters.csv"), index=False)
    show(fl, "WHAT EACH FILTER REMOVED (realistic costs; 'removed' = trades that appear only without the filter)")

    # ---- breakdowns of the JeaFx version -----------------------------------------------------
    k = kept.copy()
    k["session"] = k["entry_time"].map(grid.session_of)
    bcols = ["group", "value", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "total_R", "profit_factor"]
    parts = []
    for by in ["asset_class", "symbol", "side", "setup_type", "context_reason", "session"]:
        t = grid.table(k, [by]).rename(columns={by: "value"})
        t.insert(0, "group", by)
        parts.append(t)
    bd = pd.concat(parts, ignore_index=True)
    bd.to_csv(os.path.join(R, "dev_breakdowns.csv"), index=False)
    show(bd, "JEAFX VERSION BREAKDOWNS (dev data, realistic costs)", bcols)

    # ---- Indian cash stocks at delivery cost -------------------------------------------------
    ic = grid.run_many(config.INDIA_CASH_SYMBOLS, [engine.jeafx_variant()], costs=("realistic",), part="dev",
                       cost_bp=config.INDIA_CASH_DELIVERY_COST_BP)
    fut = kept[kept["symbol"].isin(config.INDIA_CASH_SYMBOLS)]
    icr = pd.DataFrame([{"costing": "stock futures (5 bp)", **stats.summary(fut)},
                        {"costing": f"cash delivery ({config.INDIA_CASH_DELIVERY_COST_BP:g} bp)", **stats.summary(ic)}])
    icr.to_csv(os.path.join(R, "dev_india_cash.csv"), index=False)
    show(icr, "INDIAN STOCKS: FUTURES vs CASH DELIVERY COSTS (JeaFx version, dev)",
         ["costing", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "total_R"])

    # ---- equity curves -------------------------------------------------------------------------
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    main_versions = ["JeaFx version", "break = close", "4h context off", "target = fixed 2R"]
    colours = ["#1565c0", "#2e7d32", "#e65100", "#6a1b9a"]
    for label, col in zip(main_versions, colours):
        name = grid.vname(engine.jeafx_variant(**ONE_CHANGE[label]))
        for c, ls in (("zero", "--"), ("realistic", "-")):
            t = tr[(tr["variant"] == name) & (tr["cost"] == c)].sort_values("exit_time")
            if not len(t):
                continue
            x = pd.to_datetime(t["exit_time"])
            r = t["r_after_costs"].to_numpy()
            a1.plot(x, np.cumsum(r), ls, color=col, label=f"{label} ({c})", linewidth=1.3)
            a2.plot(x, 100 * (np.cumprod(1 + config.RISK_PER_TRADE * r) - 1), ls, color=col, linewidth=1.3)
    a1.axhline(0, color="grey", linewidth=0.8)
    a2.axhline(0, color="grey", linewidth=0.8)
    a1.set_ylabel("cumulative R")
    a2.set_ylabel("equity change % (0.5% risk/trade)")
    a1.set_title("Development data, all symbols pooled by exit time. Dashed = zero cost, solid = realistic cost")
    a1.legend(fontsize=8, ncol=2)
    a1.grid(alpha=0.3)
    a2.grid(alpha=0.3)
    fig.tight_layout()
    path = os.path.join(config.CHARTS_DIR, "step8_equity_dev.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    print(f"\nsaved {path}\ntotal time {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
