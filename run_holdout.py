"""Step 9: settings check on development data, then ONE holdout run  [BRIEF section 11].

Selection rule (fixed before seeing results, copied from the brief):
  the setting with the highest average R (realistic costs) across all symbols pooled,
  with at least 100 trades, that is also positive on at least half of the symbols.
  If nothing qualifies, keep the defaults in the brief.
"Half of the symbols" = half of all 21 symbols; a symbol with no trades counts as not positive.

The holdout (last 40% of each symbol) is then run once with the chosen settings. Earlier data is
used only to warm up indicators, zones and swings; only setups whose BoS is in the holdout trade.
A lock file (results/HOLDOUT_DONE.txt) stops the holdout being re-run by accident.

Usage: py run_holdout.py
"""
import itertools
import os
import sys

import pandas as pd

import config
from jeafx import data, engine, grid, stats

R = config.RESULTS_DIR
LOCK = os.path.join(R, "HOLDOUT_DONE.txt")


def settings_search():
    syms = list(config.INSTRUMENTS)
    variants = []
    for z, br, ba, room in itertools.product(config.SEARCH_ZIGZAG_ATR, config.SEARCH_BODY_RANGE,
                                             config.SEARCH_BODY_AVG_MULT, config.SEARCH_MIN_ROOM_R):
        variants.append(engine.jeafx_variant(zigzag=z, body_range_min=br, body_avg_mult=ba, min_room_r=room,
                                             name=f"zz{z}|body{br}|avg{ba}|room{room}"))
    tr = grid.run_many(syms, variants, costs=("realistic",), part="dev")
    rows = []
    for v in variants:
        t = tr[tr["variant"] == v["name"]]
        per_sym = t.groupby("symbol")["r_after_costs"].mean()
        n_pos = int((per_sym > 0).sum())
        s = stats.summary(t)
        rows.append({"setting": v["name"], "zigzag": v["zigzag"], "body_range_min": v["body_range_min"],
                     "body_avg_mult": v["body_avg_mult"], "min_room_r": v["min_room_r"],
                     **s, "symbols_positive": n_pos,
                     "qualifies": s.get("trades", 0) >= config.SELECT_MIN_TRADES
                                  and n_pos >= config.SELECT_MIN_POSITIVE_SHARE * len(syms)})
    res = pd.DataFrame(rows).sort_values("avg_R", ascending=False)
    res.to_csv(os.path.join(R, "settings_search_dev.csv"), index=False)
    q = res[res["qualifies"]]
    default = engine.jeafx_variant()
    if len(q):
        best = q.iloc[0]
        chosen = engine.jeafx_variant(zigzag=best["zigzag"], body_range_min=best["body_range_min"],
                                      body_avg_mult=best["body_avg_mult"], min_room_r=best["min_room_r"])
        why = f"qualifying setting with the highest avg R: {best['setting']}"
    else:
        chosen, why = default, "no setting qualified -> keeping the brief's defaults"
    return res, chosen, why


def holdout(v):
    trades = []
    for sym in config.INSTRUMENTS:
        df = data.load_symbol(sym)
        start = df["time"].iloc[int(len(df) * config.DEV_FRACTION)]
        m = engine.Market(sym, df)
        for c in config.COST_MODES:
            tr, _ = engine.run(m, v, c, trade_from=start)
            if len(tr):
                tr["cost"] = c
                tr["holdout_start"] = start
                trades.append(tr)
    t = pd.concat(trades, ignore_index=True)
    t["asset_class"] = t["symbol"].map(lambda s: config.INSTRUMENTS[s]["asset_class"])
    return t


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Holdout already run (see {LOCK}). The brief says run it once. Use --force only if you really mean it.")
        return
    pd.set_option("display.width", 250, "display.max_columns", 30)
    res, chosen, why = settings_search()
    q = res[res["qualifies"]]
    cols = ["setting", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "symbols_positive", "qualifies"]
    print("SETTINGS CHECK ON DEVELOPMENT DATA (81 settings, JeaFx rules, realistic costs)")
    print(f"  settings with >= {config.SELECT_MIN_TRADES} trades: {int((res['trades'] >= config.SELECT_MIN_TRADES).sum())}/81")
    print(f"  settings positive on >= half the symbols: "
          f"{int((res['symbols_positive'] >= config.SELECT_MIN_POSITIVE_SHARE * len(config.INSTRUMENTS)).sum())}/81")
    print(f"  settings with avg R > 0: {int((res['avg_R'] > 0).sum())}/81   qualifying: {len(q)}/81")
    print("  top 5 by avg R (shown for transparency):")
    print(res[cols].head(5).to_string(index=False))
    print("  the brief's default (zz2.0|body0.6|avg1.5|room1.5):")
    print(res[res["setting"] == "zz2.0|body0.6|avg1.5|room1.5"][cols].to_string(index=False))
    print(f"\nCHOSEN: {why}")
    print(f"  zigzag {chosen['zigzag']} x ATR, body >= {chosen['body_range_min']:.0%} of range and "
          f">= {chosen['body_avg_mult']} x avg body, room check {chosen['min_room_r']}R")

    t = holdout(chosen)
    with open(LOCK, "w") as f:
        f.write(f"Holdout run once with: {why}\n{chosen}\n")
    t.to_csv(os.path.join(R, "holdout_trades.csv"), index=False)
    rows = [{"cost": c, **stats.summary(t[t["cost"] == c])} for c in config.COST_MODES]
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(R, "holdout_summary.csv"), index=False)
    print(f"\nHOLDOUT RESULT (last 40% of each symbol, run once, reported as it came out)")
    print(summ.to_string(index=False))
    real = t[t["cost"] == "realistic"]
    parts = []
    for by in ["asset_class", "symbol", "side", "setup_type", "context_reason"]:
        x = grid.table(real, [by]).rename(columns={by: "value"})
        x.insert(0, "group", by)
        parts.append(x)
    bd = pd.concat(parts, ignore_index=True)
    bd.to_csv(os.path.join(R, "holdout_breakdowns.csv"), index=False)
    print("\nHoldout breakdowns (realistic costs):")
    print(bd[["group", "value", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "total_R"]].to_string(index=False))


if __name__ == "__main__":
    main()
