"""Rule changes requested after step 9, applied one on top of the other, on DEVELOPMENT data only.

  stage 0: original JeaFx version (with the gap-fill R fix)
  stage 1: + change 1  stale setups: cancel if target touched before fill; max wait 50 -> 20 candles
  stage 2: + change 2  skip fills whose candle opens beyond the zone's far edge; stop >= 1.0 x ATR
  stage 3: + change 3  stop buffer 0.5 x ATR beyond the zone (0.25 and 1.0 also tested)
  stage 4: + change 4  target 0.25 x ATR in front of the 4h level, capped at 4R (room check 1.5R)

Outputs: results/changes_summary.csv, results/changes_setup_status.csv, results/changes_trades.csv.gz,
         charts/trades_after/ (the same 20 setups as charts/trades/, under stage 4)

Usage: py run_changes.py
"""
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config
from jeafx import data, engine, grid, plotting, stats
from jeafx.structure import find_swings

R = config.RESULTS_DIR
C1 = dict(max_wait=config.CHANGE1_MAX_WAIT, cancel_on_target_touch=True)
C2 = dict(skip_gap_beyond_zone=True, min_stop_atr=config.CHANGE2_MIN_STOP_ATR)
C3 = dict(stop_buffer_atr=config.CHANGE3_STOP_BUFFER)
C4 = dict(target_buffer_atr=config.CHANGE4_TARGET_BUFFER, target_cap_r=config.CHANGE4_TARGET_CAP_R)

STAGES = {
    "0 original": {},
    "1 change 1": {**C1},
    "2 changes 1+2": {**C1, **C2},
    "3 changes 1+2+3": {**C1, **C2, **C3},
    "4 changes 1+2+3+4": {**C1, **C2, **C3, **C4},
}
BUFFER_TESTS = {}
for b in config.CHANGE3_TEST_BUFFERS:
    if b != config.CHANGE3_STOP_BUFFER:
        BUFFER_TESTS[f"3 changes 1+2+3, buffer {b}"] = {**C1, **C2, "stop_buffer_atr": b}
        BUFFER_TESTS[f"4 changes 1+2+3+4, buffer {b}"] = {**C1, **C2, **C4, "stop_buffer_atr": b}


def _worker(sym):
    m = engine.Market(sym, grid.split_df(data.load_symbol(sym), "dev"))
    trades, logs = [], []
    for name, ov in {**STAGES, **BUFFER_TESTS}.items():
        v = engine.jeafx_variant(**ov)
        for c in config.COST_MODES:
            tr, lg = engine.run(m, v, c)
            if len(tr):
                tr["stage"], tr["cost"] = name, c
                trades.append(tr)
            if len(lg):
                lg["stage"], lg["cost"] = name, c
                logs.append(lg)
    return pd.concat(trades, ignore_index=True), pd.concat(logs, ignore_index=True)


def mfe_report(t):
    losers = t[t["r_after_costs"] < 0]
    if not len(losers):
        return {}
    return {"losers": len(losers),
            "losers_hit_+1R_%": round(100 * (losers["mfe_r"] >= 1.0).mean(), 1),
            "losers_hit_+0.5R_%": round(100 * (losers["mfe_r"] >= 0.5).mean(), 1),
            "avg_MFE_losers_R": round(losers["mfe_r"].mean(), 2),
            "avg_MAE_winners_R": round(t[t["r_after_costs"] > 0]["mae_r"].mean(), 2),
            "stopped_on_fill_candle_%": round(100 * ((t["bars_held"] == 0) & (t["exit_reason"] == "stop")).mean(), 1)}


def main():
    syms = list(config.INSTRUMENTS)
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as ex:
        res = list(ex.map(_worker, syms))
    tr = pd.concat([r[0] for r in res], ignore_index=True)
    lg = pd.concat([r[1] for r in res], ignore_index=True)
    tr.to_csv(os.path.join(R, "changes_trades.csv.gz"), index=False)

    rows = []
    for name in list(STAGES) + list(BUFFER_TESTS):
        for c in config.COST_MODES:
            t = tr[(tr["stage"] == name) & (tr["cost"] == c)]
            per_sym = t.groupby("symbol")["r_after_costs"].mean()
            rows.append({"stage": name, "cost": c, **stats.summary(t), "symbols_positive": int((per_sym > 0).sum()),
                         **mfe_report(t)})
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(R, "changes_summary.csv"), index=False)

    pd.set_option("display.width", 260, "display.max_columns", 40)
    main_cols = ["stage", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "total_R",
                 "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak", "avg_hold_hours", "symbols_positive"]
    is_stage = summ["stage"].isin(STAGES)
    print("RULE CHANGES, ONE ON TOP OF THE OTHER (development data, 21 symbols pooled, R after costs)")
    print(summ[is_stage][main_cols].to_string(index=False))
    print("\nSTOP BUFFER TEST (development data only)")
    buf = summ[summ["stage"].str.startswith(("3", "4")) & (summ["cost"] == "realistic")]
    print(buf[main_cols].to_string(index=False))
    print("\nMFE / MAE (realistic costs): did losing trades go into profit first?")
    mcols = ["stage", "trades", "losers", "losers_hit_+1R_%", "losers_hit_+0.5R_%", "avg_MFE_losers_R",
             "avg_MAE_winners_R", "stopped_on_fill_candle_%"]
    print(summ[summ["cost"] == "realistic"][mcols].to_string(index=False))

    # setup outcomes per stage (realistic): what happened to every valid setup
    real_log = lg[(lg["cost"] == "realistic") & lg["stage"].isin(STAGES)]
    st = real_log[~real_log["status"].str.startswith("filtered:") | (real_log["status"] == "filtered:room")]
    status = st.pivot_table(index="status", columns="stage", values="bos_idx", aggfunc="count", fill_value=0)
    status.to_csv(os.path.join(R, "changes_setup_status.csv"))
    print("\nWHAT HAPPENED TO THE SETUPS THAT PASSED THE ENTRY FILTERS (realistic costs, counts)")
    print(status.to_string())
    s0, s1 = status.get("0 original"), status.get("1 change 1")
    if s0 is not None and s1 is not None:
        print(f"\nChange 1 cancelled {int(s1.get('target_before_fill', 0))} waiting setups because the target was "
              f"touched first (these also no longer show up as expired/replaced). "
              f"Trades: {int(s0.get('traded', 0))} -> {int(s1.get('traded', 0))} "
              f"({int(s0.get('traded', 0)) - int(s1.get('traded', 0))} fewer).")

    charts_after(tr, lg)


def charts_after(tr, lg, stage="4 changes 1+2+3+4"):
    """Same 20 setups as charts/trades (picked with the same seed from the original version)."""
    v0 = engine.jeafx_variant()
    v4 = engine.jeafx_variant(**STAGES[stage])
    pool, cache = [], {}
    for sym in config.INSTRUMENTS:
        m = engine.Market(sym, grid.split_df(data.load_symbol(sym), "dev"))
        t0, _ = engine.run(m, v0, "realistic")
        if len(t0):
            cache[sym] = (m, t0)
            pool += [(sym, k) for k in range(len(t0))]
    rng = np.random.default_rng(config.RANDOM_SEED)
    picks = [pool[k] for k in rng.choice(len(pool), size=min(config.N_VISUAL_TRADE_CHARTS, len(pool)), replace=False)]
    out = os.path.join(config.CHARTS_DIR, "trades_after")
    os.makedirs(out, exist_ok=True)
    rows = []
    for num, (sym, k) in enumerate(sorted(picks), 1):
        m, t0 = cache[sym]
        old = t0.iloc[k]
        b = m.breaks(v4)
        s = b[(b["bos_idx"] == old["bos_idx"]) & (b["side"] == old["side"])].iloc[0]
        t4, l4 = engine.run(m, v4, "realistic")
        hit = t4[(t4["bos_idx"] == old["bos_idx"]) & (t4["side"] == old["side"])] if len(t4) else t4
        sw = find_swings(m.df, v4["zigzag"])
        name = sym.replace("=", "").replace("^", "")
        path = os.path.join(out, f"trade_{num:02d}_{name}_{old['side']}.png")
        before = f"BEFORE: {old['exit_reason']} {old['r_after_costs']:+.2f}R"
        if len(hit):
            t = hit.iloc[0]
            title = (f"#{num} {sym} {t['side']} AFTER changes 1-4 | entry {pd.Timestamp(t['entry_time']):%Y-%m-%d %H:%M} | "
                     f"exit: {t['exit_reason']} | {t['r_after_costs']:+.2f}R | MFE {t['mfe_r']:.2f}R  ({before})")
            after = f"{t['exit_reason']} {t['r_after_costs']:+.2f}R"
            plotting.trade_chart(m.df, sw, t, s, title, path)
        else:
            rec = l4[(l4["bos_idx"] == old["bos_idx"]) & (l4["side"] == old["side"])].iloc[0]
            end = int(min(old["bos_idx"] + v4["max_wait"], len(m.df) - 1))
            pseudo = {"side": old["side"], "entry_idx": end, "exit_idx": end, "no_trade": True,
                      "entry_price": rec.get("plan_entry", np.nan), "stop": rec.get("plan_stop", np.nan),
                      "target": rec.get("plan_target", np.nan), "target_type": "planned", "exit_price": np.nan}
            title = (f"#{num} {sym} {old['side']} AFTER changes 1-4 | NO TRADE: {rec['status']} | "
                     f"dashed lines = planned entry/SL/TP  ({before})")
            after = f"no trade ({rec['status']})"
            plotting.trade_chart(m.df, sw, pseudo, s, title, path)
        rows.append({"chart": os.path.basename(path), "symbol": sym, "side": old["side"],
                     "before": f"{old['exit_reason']} {old['r_after_costs']:+.2f}R", "after": after})
    idx = pd.DataFrame(rows)
    idx.to_csv(os.path.join(out, "index.csv"), index=False)
    print("\nSAME 20 SETUPS, BEFORE vs AFTER changes 1-4 (realistic costs)")
    print(idx.to_string(index=False))
    print(f"saved charts in {out}")


if __name__ == "__main__":
    main()
