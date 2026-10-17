"""Amendment 1, counts-only step: number of v2 setups and filled trades per pair and year.
Shows NO win rate, R or P&L (the engine computes them internally; they are discarded here, never printed or saved).

Usage: py run_v2_counts.py [major_zigzag_atr]
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

import config
from jeafx import engine
from jeafx.v2 import V2Planner
from run_v2 import V2, load


def _worker(args):
    sym, major = args
    config.V2_MAJOR_ZIGZAG_ATR = major
    m = engine.Market(sym, load(sym))
    planner = V2Planner(m.df)
    tr, _ = engine.run(m, V2, "realistic", planner=planner)
    setups = pd.DataFrame({"symbol": sym, "year": [pd.Timestamp(r["bos_time"]).year for r in planner.records]})
    fills = pd.DataFrame({"symbol": sym, "year": pd.to_datetime(tr["entry_time"]).dt.year if len(tr) else []})
    return setups, fills           # only counts leave this function


def main():
    major = float(sys.argv[1]) if len(sys.argv) > 1 else config.V2_MAJOR_ZIGZAG_ATR
    with ProcessPoolExecutor(max_workers=len(config.V2_PAIRS)) as ex:
        res = list(ex.map(_worker, [(s, major) for s in config.V2_PAIRS]))
    S = pd.concat([r[0] for r in res], ignore_index=True)
    F = pd.concat([r[1] for r in res], ignore_index=True)
    years = list(range(config.V2_FIRST_YEAR, config.V2_LAST_YEAR + 1))

    def table(x):
        t = x.groupby(["symbol", "year"]).size().unstack(fill_value=0).reindex(index=config.V2_PAIRS, columns=years, fill_value=0)
        t["total"] = t.sum(axis=1)
        t.loc["TOTAL"] = t.sum()
        return t

    st, ft = table(S), table(F)
    tag = f"major{major:g}"
    st.to_csv(os.path.join(config.RESULTS_DIR, f"v2_counts_setups_{tag}.csv"))
    ft.to_csv(os.path.join(config.RESULTS_DIR, f"v2_counts_fills_{tag}.csv"))
    pd.set_option("display.width", 200)
    print(f"COUNTS ONLY  (major zigzag {major:g} x ATR, 3 rising swings; realistic fill rules)")
    print("\nv2 setups (passed every rule) per pair per year:")
    print(st.to_string())
    print("\nfilled trades per pair per year:")
    print(ft.to_string())
    print(f"\nTOTAL setups {int(st.loc['TOTAL', 'total'])}, filled trades {int(ft.loc['TOTAL', 'total'])}")


if __name__ == "__main__":
    main()
