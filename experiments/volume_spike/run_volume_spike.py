"""Volume spike continuation test (PREREGISTRATION.md). Run once; locked afterwards.

Usage: py run_volume_spike.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "data", "binance")       # Binance 1h files from download_binance.py
OUT = os.path.join(HERE, "results")
LOCK = os.path.join(OUT, "DONE.txt")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
START, END = pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2026-10-01", tz="UTC")
VOL_MULT, VOL_LOOKBACK = 2.0, 20      # event: volume >= 2.0 x mean of previous 20 candles
COOLDOWN = 50                         # ignore new events for 50 candles after an event
HORIZONS = [5, 10, 20, 50]            # forward-move horizons (candles)
N_RANDOM = 20                         # random baseline draws per event
HOLD = 20                             # simple trade: exit at the close of the 20th candle after entry
COST_PCT = 0.05                       # 5 bp per side
ATR_N = 14
SEED = 42
BOOT = 10_000
YEARS = [2023, 2024, 2025, 2026]


def boot_ci(x, seed=SEED):
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (BOOT, len(x)))].mean(axis=1)
    return np.quantile(m, 0.025), np.quantile(m, 0.975)


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan


def load(sym):
    d = pd.read_csv(os.path.join(DATA, f"{sym}.csv"))
    d["time"] = pd.to_datetime(d["time"], utc=True)
    d = d.dropna().sort_values("time").reset_index(drop=True)
    pc = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(), (d["low"] - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(ATR_N).mean()
    d["vol_avg"] = d["volume"].shift(1).rolling(VOL_LOOKBACK).mean()
    return d[d["time"] < END].reset_index(drop=True)


def symbol_events(sym, rng):
    d = load(sym)
    o, c, v, avg, a = (d[x].to_numpy(float) for x in ("open", "close", "volume", "vol_avg", "atr"))
    t = d["time"]
    n, hmax = len(d), max(HORIZONS)
    in_period = (t >= START).to_numpy()
    ok_fwd = np.arange(n) < n - hmax
    hours = t.dt.hour.to_numpy()
    pool = {h: np.nonzero(in_period & ok_fwd & (hours == h) & ~np.isnan(a))[0] for h in range(24)}
    rows, last = [], -10 ** 9
    for i in range(n):
        if not in_period[i] or np.isnan(avg[i]) or v[i] < VOL_MULT * avg[i]:
            continue
        sg = np.sign(c[i] - o[i])
        if sg == 0:
            continue
        if i - last <= COOLDOWN:
            continue
        last = i
        if not ok_fwd[i]:
            continue
        rnd = rng.choice(pool[hours[i]], N_RANDOM)
        r = {"symbol": sym, "time": t.iloc[i], "year": t.iloc[i].year, "direction": int(sg)}
        for k in HORIZONS:
            r[f"atr_{k}"] = sg * (c[i + k] - c[i]) / a[i]
            r[f"pct_{k}"] = sg * (c[i + k] / c[i] - 1) * 100
            ra = sg * (c[rnd + k] - c[rnd]) / a[rnd]
            rp = sg * (c[rnd + k] / c[rnd] - 1) * 100
            r[f"rand_atr_{k}"], r[f"rand_pct_{k}"] = ra.mean(), rp.mean()
            r[f"rand_pos_{k}"] = (ra > 0).mean()
        entry, exit_ = o[i + 1], c[i + HOLD]
        r["trade_net_pct"] = sg * (exit_ / entry - 1) * 100 - 2 * COST_PCT
        r["trade_year"] = t.iloc[i + 1].year
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Already run once (see {LOCK}).")
        return
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(SEED)
    ev = pd.concat([symbol_events(s, rng) for s in SYMBOLS], ignore_index=True)
    with open(LOCK, "w") as f:
        f.write("Volume spike continuation test run once (PREREGISTRATION.md)\n")
    ev.to_csv(os.path.join(OUT, "events.csv"), index=False)
    pd.set_option("display.width", 220, "display.max_columns", 30)

    print(f"VOLUME SPIKE CONTINUATION  Binance perps 2023-01 .. 2026-09, {len(ev)} non-overlapping events "
          f"({ev['symbol'].value_counts().to_dict()})")
    rows = []
    for k in HORIZONS:
        for unit in ("atr", "pct"):
            m, rb = ev[f"{unit}_{k}"], ev[f"rand_{unit}_{k}"]
            lo, hi = boot_ci(m - rb)
            rows.append({"horizon": k, "unit": "ATR" if unit == "atr" else "%", "events": len(m),
                         "avg_move": round(m.mean(), 4), "right_dir_%": round(100 * (m > 0).mean(), 1),
                         "random_avg": round(rb.mean(), 4), "random_right_dir_%": round(100 * ev[f"rand_pos_{k}"].mean(), 1),
                         "difference": round((m - rb).mean(), 4), "diff_ci95": f"{lo:+.4f}..{hi:+.4f}",
                         "ci_includes_0": lo <= 0 <= hi})
    fwd = pd.DataFrame(rows)
    fwd.to_csv(os.path.join(OUT, "forward_moves.csv"), index=False)
    print("\nFORWARD MOVE IN THE EVENT'S DIRECTION vs 20 random times per event (same symbol, same hour)")
    print(fwd.to_string(index=False))

    def summ(x):
        lo, hi = boot_ci(x) if len(x) > 1 else (np.nan, np.nan)
        return {"trades": len(x), "avg_net_%": round(x.mean(), 3), "ci95_low": round(lo, 3), "ci95_high": round(hi, 3),
                "t": round(tstat(x), 2), "win_rate_%": round(100 * (x > 0).mean(), 1)}

    tr = ev["trade_net_pct"]
    rows = [{"group": "ALL", **summ(tr)}]
    rows += [{"group": f"symbol={s}", **summ(g["trade_net_pct"])} for s, g in ev.groupby("symbol")]
    rows += [{"group": f"year={y}", **summ(ev[ev["trade_year"] == y]["trade_net_pct"])} for y in YEARS]
    ts = pd.DataFrame(rows)
    ts.to_csv(os.path.join(OUT, "trade_summary.csv"), index=False)
    print(f"\nSIMPLE TRADE: enter next open, exit at close of candle {HOLD}, 5 bp per side (net % per trade)")
    print(ts.to_string(index=False))

    all_ = ts.iloc[0]
    yrs_pos = int(sum(ev[ev["trade_year"] == y]["trade_net_pct"].mean() > 0 for y in YEARS))
    passed = all_["avg_net_%"] > 0 and all_["ci95_low"] > 0 and yrs_pos >= 3
    print(f"\nPASS MARK: avg net > 0: {all_['avg_net_%'] > 0}; CI low > 0: {all_['ci95_low'] > 0}; "
          f"positive years: {yrs_pos}/4 (need 3)  ->  {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()
