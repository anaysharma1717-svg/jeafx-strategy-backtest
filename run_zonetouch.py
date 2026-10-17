"""Zone-touch forward test (results/zonetouch_PREREGISTRATION.md). Run once.

Usage: py run_zonetouch.py
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config
from jeafx import engine, stats
from jeafx.indicators import atr as atr_fn
from run_frozen import VERSIONS
from run_v2 import load

R = config.RESULTS_DIR
LOCK = os.path.join(R, "ZONETOUCH_DONE.txt")
H = config.V2_FORWARD_HORIZONS
SEARCH = config.MAX_BARS_IN_TRADE
N_RANDOM = 20
EARLY = 10


def _worker(sym):
    df = load(sym)
    m = engine.Market(sym, df)
    _, lg = engine.run(m, VERSIONS["frozen"], "realistic")
    ok = lg[~lg["status"].str.startswith("filtered:")]
    h, l, c = (m.df[x].to_numpy(float) for x in ("high", "low", "close"))
    a = atr_fn(m.df, config.ATR_PERIOD).to_numpy()
    hours = m.df["time"].dt.hour.to_numpy()
    n = len(c)
    hmax = max(H)
    pool = {hr: np.nonzero((hours == hr) & (np.arange(n) >= config.ATR_PERIOD) & (np.arange(n) < n - hmax))[0]
            for hr in range(24)}
    rng = np.random.default_rng([config.RANDOM_SEED, config.V2_PAIRS.index(sym)])
    rows, no_touch = [], 0
    for r in ok.itertuples():
        i, sg, entry = int(r.bos_idx), (1.0 if r.side == "long" else -1.0), r.plan_entry
        seg = slice(i + 1, min(i + 1 + SEARCH, n))
        hit = np.nonzero((l[seg] <= entry) if sg > 0 else (h[seg] >= entry))[0]
        if not len(hit):
            no_touch += 1
            continue
        t = i + 1 + int(hit[0])
        rnd = rng.choice(pool[hours[t]], N_RANDOM)
        row = {"symbol": sym, "side": r.side, "bos_idx": i, "touch_idx": t, "delay": t - i}
        for k in H:
            row[f"move_{k}"] = sg * (c[t + k] - c[t]) / a[t] if t + k < n else np.nan
            rm = sg * (c[rnd + k] - c[rnd]) / a[rnd]
            row[f"rand_{k}"] = rm.mean()
            row[f"rand_pos_{k}"] = (rm > 0).mean()
        rows.append(row)
    return pd.DataFrame(rows), no_touch, len(ok)


def table(d):
    out = []
    for k in H:
        x = d.dropna(subset=[f"move_{k}"])
        diff = x[f"move_{k}"] - x[f"rand_{k}"]
        lo, hi = stats.bootstrap_ci(diff)
        out.append({"horizon": k, "setups": len(x),
                    "avg_move_ATR": round(x[f"move_{k}"].mean(), 3),
                    "right_dir_%": round(100 * (x[f"move_{k}"] > 0).mean(), 1),
                    "random_avg_ATR": round(x[f"rand_{k}"].mean(), 3),
                    "random_right_dir_%": round(100 * x[f"rand_pos_{k}"].mean(), 1),
                    "difference": round(diff.mean(), 3), "diff_ci95": f"{lo:+.3f}..{hi:+.3f}",
                    "ci_includes_0": lo <= 0 <= hi})
    return pd.DataFrame(out)


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Already run once (see {LOCK}).")
        return
    with ProcessPoolExecutor(max_workers=len(config.V2_PAIRS)) as ex:
        res = list(ex.map(_worker, config.V2_PAIRS))
    with open(LOCK, "w") as f:
        f.write("Zone-touch forward test run once (zonetouch_PREREGISTRATION.md)\n")
    d = pd.concat([r[0] for r in res], ignore_index=True)
    total, no_touch = sum(r[2] for r in res), sum(r[1] for r in res)
    d.to_csv(os.path.join(R, "zonetouch_setups.csv"), index=False)
    pd.set_option("display.width", 220)
    print(f"ZONE-TOUCH FORWARD TEST  frozen version setups, histdata 2015-2023, 7 pairs")
    print(f"setups {total}, touched within {SEARCH} candles {len(d)}, never touched {no_touch}; "
          f"touch within {EARLY} candles: {int((d['delay'] <= EARLY).sum())}, later: {int((d['delay'] > EARLY).sum())}")
    parts = []
    for name, x in (("all", d), (f"touch <= {EARLY} candles after BoS", d[d["delay"] <= EARLY]),
                    (f"touch > {EARLY} candles after BoS", d[d["delay"] > EARLY])):
        t = table(x)
        t.insert(0, "group", name)
        parts.append(t)
        print(f"\n{name}")
        print(t.drop(columns="group").to_string(index=False))
    pd.concat(parts).to_csv(os.path.join(R, "zonetouch_summary.csv"), index=False)


if __name__ == "__main__":
    main()
