"""Crypto volume / CVD experiment, test 5: the holdout (BoS on or after 2023-01-01), run ONCE for Base, A, B, A+B
with the volume multiple chosen on development data (results/crypto_choice.txt). Pass mark from
results/crypto_PREREGISTRATION.md.

Usage: py run_crypto_holdout.py
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

import config
from jeafx import stats
from run_crypto import HOLD, load, run_versions, versions

R = config.RESULTS_DIR
LOCK = os.path.join(R, "CRYPTO_HOLDOUT_DONE.txt")


def _worker(args):
    sym, mult = args
    _, tr, _ = run_versions(sym, load(sym, "all"), versions(mult), mult, trade_from=HOLD)
    return tr


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Holdout already run once (see {LOCK}).")
        return
    mult = float(open(os.path.join(R, "crypto_choice.txt")).read().strip())
    with ProcessPoolExecutor(max_workers=len(config.CRYPTO_SYMBOLS)) as ex:
        parts = list(ex.map(_worker, [(s, mult) for s in config.CRYPTO_SYMBOLS]))
    with open(LOCK, "w") as f:
        f.write(f"Crypto holdout run once with volume multiple {mult:g} (crypto_PREREGISTRATION.md)\n")
    tr = pd.concat([p for p in parts if len(p)], ignore_index=True)
    tr.to_csv(os.path.join(R, "crypto_holdout_trades.csv"), index=False)
    names = list(versions(mult))
    rows = [{"version": v, "cost": c, **stats.summary(tr[(tr["version"] == v) & (tr["cost"] == c)])}
            for v in names for c in config.COST_MODES]
    s = pd.DataFrame(rows)
    base_r = s[(s["version"] == "Base") & (s["cost"] == "realistic")]["avg_R"].iloc[0]
    s["PASS"] = ""
    for k, r in s.iterrows():
        if r["cost"] == "realistic" and r["version"] != "Base":
            ok = r["avg_R"] >= 0.10 and r["ci95_low"] > 0 and r["avg_R"] > base_r
            s.loc[k, "PASS"] = "PASS" if ok else "fail"
    s.to_csv(os.path.join(R, "crypto_holdout_summary.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)
    cols = ["version", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "total_R",
            "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak", "PASS"]
    print(f"TEST 5. HOLDOUT 2023-01 .. 2026-09, run once, volume multiple {mult:g}")
    print(s[cols].to_string(index=False))
    print("\nPass mark: realistic avg R >= +0.10, 95% CI low > 0, and above Base's avg R.")
    real = tr[tr["cost"] == "realistic"]
    bys = pd.DataFrame([{"version": v, "symbol": sym, **stats.summary(g)} for (v, sym), g in real.groupby(["version", "symbol"])])
    bys.to_csv(os.path.join(R, "crypto_holdout_by_symbol.csv"), index=False)
    print("\nby symbol (realistic):")
    print(bys[["version", "symbol", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "total_R"]].to_string(index=False))


if __name__ == "__main__":
    main()
