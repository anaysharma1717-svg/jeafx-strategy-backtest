"""Visual check  [BRIEF section 10]: candle charts of random JeaFx trades showing 1h swings,
BoS level, zone, imbalance, entry, stop, target and exit.

Usage: py run_trade_charts.py            (20 random trades, development data, realistic costs)
"""
import os

import numpy as np
import pandas as pd

import config
from jeafx import data, engine, grid, plotting
from jeafx.structure import find_swings


def main(n=config.N_VISUAL_TRADE_CHARTS):
    v = engine.jeafx_variant()
    out_dir = os.path.join(config.CHARTS_DIR, "trades")
    os.makedirs(out_dir, exist_ok=True)
    pool = []
    cache = {}
    for sym in config.INSTRUMENTS:
        df = grid.split_df(data.load_symbol(sym), "dev")
        m = engine.Market(sym, df)
        tr, _ = engine.run(m, v, "realistic")
        if len(tr):
            cache[sym] = (m, tr)
            pool += [(sym, k) for k in range(len(tr))]
    rng = np.random.default_rng(config.RANDOM_SEED)
    picks = [pool[k] for k in rng.choice(len(pool), size=min(n, len(pool)), replace=False)]
    rows = []
    for num, (sym, k) in enumerate(sorted(picks), 1):
        m, tr = cache[sym]
        t = tr.iloc[k]
        b = m.breaks(v)
        s = b[(b["bos_idx"] == t["bos_idx"]) & (b["side"] == t["side"])].iloc[0]
        sw = find_swings(m.df, v["zigzag"])
        name = sym.replace("=", "").replace("^", "")
        path = os.path.join(out_dir, f"trade_{num:02d}_{name}_{t['side']}.png")
        title = (f"#{num} {sym} {t['side']} {t['setup_type']} | entry {pd.Timestamp(t['entry_time']):%Y-%m-%d %H:%M} UTC | "
                 f"exit: {t['exit_reason']} | R after costs {t['r_after_costs']:+.2f} | held {t['bars_held']} candles\n"
                 "triangles = 1h swing highs/lows (resistance/support), black = broken level, box = zone, "
                 "purple = imbalance, dashed: blue entry / red SL / green TP, X = exit")
        plotting.trade_chart(m.df, sw, t, s, title, path)
        rows.append({"chart": os.path.basename(path), "symbol": sym, "side": t["side"], "entry_time": t["entry_time"],
                     "entry": t["entry_price"], "stop": t["stop"], "target": t["target"], "exit": t["exit_price"],
                     "exit_reason": t["exit_reason"], "R": round(t["r_after_costs"], 2), "bars_held": t["bars_held"]})
    idx = pd.DataFrame(rows)
    idx.to_csv(os.path.join(out_dir, "index.csv"), index=False)
    print(idx.to_string(index=False))
    print(f"\nsaved {len(idx)} charts in {out_dir}")


if __name__ == "__main__":
    main()
