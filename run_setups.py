"""Step 4: imbalances, breaks of structure and zones on 1h. Prints a funnel per symbol and
saves 5 example charts of valid JeaFx setups (strong close, zone size ok, imbalanced).

Usage: py run_setups.py
"""
import os

import numpy as np
import pandas as pd

import config
from jeafx import data, plotting, setups
from jeafx.structure import find_swings

CHART_PICKS = [("EURUSD=X", "long"), ("GBPUSD=X", "short"), ("GC=F", "long"), ("NQ=F", "short"), ("AAPL", "long")]


def main():
    rows = []
    all_breaks = {}
    for sym, info in config.INSTRUMENTS.items():
        df = data.load_symbol(sym)
        roll = data.flag_roll_gaps(df) if info["futures"] else None
        b = setups.find_breaks(df, roll=roll)
        all_breaks[sym] = (df, b)
        close_breaks = len(setups.find_breaks(df, rule="close", roll=roll))
        wick_breaks = len(setups.find_breaks(df, rule="wick", roll=roll))
        rows.append({
            "symbol": sym,
            "wick_breaks": wick_breaks,
            "close_breaks": close_breaks,
            "strong_close": int((b["reason"] != "weak_close").sum()),
            "minus_roll_gap": int((~b["reason"].isin(["weak_close", "roll_gap"])).sum()),
            "zone_size_ok": int((b["reason"] == "").sum()),
            "imbalanced(valid)": int(b["valid"].sum()),
            "valid_long": int((b["valid"] & (b["side"] == "long")).sum()),
            "valid_short": int((b["valid"] & (b["side"] == "short")).sum()),
            "reversal_%": round(100 * (b[b["valid"]]["setup_type"] == "reversal").mean(), 1),
            "swept_%": round(100 * b[b["valid"]]["swept"].mean(), 1),
            "body_top_zones": int(b[b["valid"]]["zone_body_top"].sum()),
        })
        b.to_csv(os.path.join(config.RESULTS_DIR, f"breaks_{sym.replace('=', '').replace('^', '')}.csv"), index=False)
    rep = pd.DataFrame(rows)
    total = rep.drop(columns=["symbol", "reversal_%", "swept_%"]).sum()
    rep = pd.concat([rep, pd.DataFrame([{"symbol": "TOTAL", **total.to_dict()}])], ignore_index=True)
    rep.to_csv(os.path.join(config.RESULTS_DIR, "setup_funnel.csv"), index=False)
    pd.set_option("display.width", 250)
    print("Funnel: each column keeps the setups that pass one more JeaFx rule (1h, all data)")
    print(rep.to_string(index=False))

    rng = np.random.default_rng(config.RANDOM_SEED)
    for n, (sym, side) in enumerate(CHART_PICKS, 1):
        df, b = all_breaks[sym]
        cand = b[b["valid"] & (b["side"] == side)]
        s = cand.iloc[rng.integers(len(cand))]
        end, how = setups.zone_life(df, side, s["zone_top"], s["zone_bottom"], int(s["bos_idx"]) + 1,
                                    config.ZONE_EXPIRY_1H)
        d = df if side == "long" else setups.mirror(df)
        sw = find_swings(d)
        if side == "short":
            sw["price"] = -sw["price"]
            sw["kind"] = sw["kind"].map({"high": "low", "low": "high"})
        name = sym.replace("=", "").replace("^", "")
        path = os.path.join(config.CHARTS_DIR, f"step4_zone_{n}_{name}_{side}.png")
        title = (f"{sym} 1h {side} {s['setup_type']}  BoS {s['bos_time']:%Y-%m-%d %H:%M} UTC  "
                 f"zone {s['zone_bottom']:.5g}-{s['zone_top']:.5g}  zone ended: {how}  swept: {s['swept']}")
        plotting.setup_chart(df, sw, s, end, title, path)
        print("saved", path)


if __name__ == "__main__":
    main()
