"""Step 3: ATR, zigzag swings and structure on 1h and 4h; save 3 check charts.

Usage: py run_structure.py
"""
import os

import pandas as pd

import config
from jeafx import data, plotting
from jeafx.structure import analyse

CHARTS = [  # (symbol, timeframe, number of most recent candles to draw)
    ("EURUSD=X", "1h", 300),
    ("GC=F", "4h", 250),
    ("NVDA", "1h", 250),
]


def load_both(sym):
    df1 = data.load_symbol(sym)
    df4 = data.build_4h(df1, config.INSTRUMENTS[sym]["session"])
    return df1, df4


def main():
    os.makedirs(config.CHARTS_DIR, exist_ok=True)
    rows = []
    for sym in config.INSTRUMENTS:
        df1, df4 = load_both(sym)
        for tf, d in (("1h", df1), ("4h", df4)):
            a, sw = analyse(d)
            share = a["structure"].value_counts(normalize=True)
            bars_between = sw["idx"].diff().mean()
            rows.append({"symbol": sym, "tf": tf, "candles": len(a), "swings": len(sw),
                         "avg_candles_between_swings": round(bars_between, 1),
                         "avg_confirm_delay": round((sw["confirm_idx"] - sw["idx"]).mean(), 1),
                         "bullish_%": round(100 * share.get("bullish", 0), 1),
                         "bearish_%": round(100 * share.get("bearish", 0), 1),
                         "ranging_%": round(100 * share.get("ranging", 0), 1)})
    rep = pd.DataFrame(rows)
    rep.to_csv(os.path.join(config.RESULTS_DIR, "structure_report.csv"), index=False)
    pd.set_option("display.width", 200)
    print(rep.to_string(index=False))

    for sym, tf, n in CHARTS:
        df1, df4 = load_both(sym)
        a, sw = analyse(df1 if tf == "1h" else df4)
        start = len(a) - n
        name = sym.replace("=", "").replace("^", "")
        path = os.path.join(config.CHARTS_DIR, f"step3_swings_{name}_{tf}.png")
        plotting.structure_chart(a, sw, start, len(a),
                                 f"{sym} {tf} zigzag {config.ZIGZAG_ATR_MULT} x ATR({config.ATR_PERIOD})", path)
        print("saved", path)


if __name__ == "__main__":
    main()
