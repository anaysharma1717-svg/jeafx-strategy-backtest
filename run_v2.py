"""Reversal shape v2: the single pre-registered run on histdata.com forex 2015-2023.
Rules: results/v2_PREREGISTRATION.md (written before this script was run). Nothing here is tuned.

Outputs: results/v2_trades.csv, v2_setups.csv, v2_summary.csv, v2_per_pair_year.csv, v2_flip_test.csv,
         v2_forward_test.csv, charts/v2_setups/*.png
A lock file (results/V2_RUN_DONE.txt) stops it from being re-run by accident.

Usage: py run_v2.py
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

import config
from jeafx import data, engine, plotting, stats
from jeafx.v2 import V2Planner

R = config.RESULTS_DIR
LOCK = os.path.join(R, "V2_RUN_DONE.txt")
V2 = engine.jeafx_variant(use_htf_context=False, target_mode="v2", max_wait=config.V2_MAX_WAIT,
                          cancel_on_target_touch=True)


def load(sym):
    df, _ = data.clean(pd.read_csv(os.path.join(config.V2_DATA_DIR, f"{sym}.csv")))
    return df


# ---------------------------------------------------------------------------
def simulate_exit(o, h, l, c, j, fill, stop, tgt, cost, realistic):
    """Same exit rules as the engine (stop first, only stop on the fill candle, 200-candle time exit),
    in a long-shaped price view. Returns (exit_idx, exit_price, reason)."""
    n = len(c)
    end = min(j + config.MAX_BARS_IN_TRADE, n - 1)
    if l[j] <= stop:
        return j, stop, "stop"
    seg = slice(j + 1, end + 1)
    s = np.nonzero(l[seg] <= stop)[0]
    t = np.nonzero(h[seg] >= tgt + (cost if realistic else 0.0))[0]
    s1 = j + 1 + s[0] if len(s) else None
    t1 = j + 1 + t[0] if len(t) else None
    if s1 is not None and (t1 is None or s1 <= t1):
        return s1, (o[s1] if o[s1] < stop else stop), "stop"
    if t1 is not None:
        return t1, (o[t1] if o[t1] >= tgt else tgt), "target"
    return end, c[end], ("time" if end == j + config.MAX_BARS_IN_TRADE else "data_end")


def flip_trades(df, tr, cost_mode):
    """Opposite trade at the same fill candle and price, stop/target distances mirrored."""
    o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
    views = {"long": (o, h, l, c), "short": (-o, -l, -h, -c)}
    out = []
    for t in tr.itertuples(index=False):
        side = "short" if t.side == "long" else "long"
        sg = 1.0 if side == "long" else -1.0
        fill = sg * t.entry_price
        risk = t.risk_price
        d_tgt = abs(t.target - t.entry_price)
        stop, tgt = fill - risk, fill + d_tgt          # in the flipped trade's own view
        vo, vh, vl, vc = views[side]
        k, px, why = simulate_exit(vo, vh, vl, vc, int(t.entry_idx), fill, stop, tgt, t.cost_per_side,
                                   cost_mode == "realistic")
        rb = (px - fill) / risk
        n_costs = 2 + (1 if (cost_mode == "realistic" and why == "stop") else 0)
        out.append({"symbol": t.symbol, "entry_idx": t.entry_idx, "real_R": t.r_after_costs,
                    "flipped_R": rb - n_costs * t.cost_per_side / risk, "flipped_exit": why})
    return pd.DataFrame(out)


def forward_returns(df, recs, rng, long_share):
    from jeafx.indicators import atr as atr_fn

    c = df["close"].to_numpy(float)
    a = atr_fn(df, config.ATR_PERIOD).to_numpy()
    n = len(c)
    sig, base = [], []
    for r in recs:
        i = r["bos_idx"]
        sg = 1.0 if r["side"] == "long" else -1.0
        sig.append({f"fwd_{k}": (sg * (c[i + k] - c[i]) / a[i]) if i + k < n else np.nan
                    for k in config.V2_FORWARD_HORIZONS})
    hmax = max(config.V2_FORWARD_HORIZONS)
    idx = rng.integers(config.ATR_PERIOD, n - hmax, size=config.V2_RANDOM_BASELINE_PER_PAIR)
    sides = np.where(rng.random(len(idx)) < long_share, 1.0, -1.0)
    for i, sg in zip(idx, sides):
        base.append({f"fwd_{k}": sg * (c[i + k] - c[i]) / a[i] for k in config.V2_FORWARD_HORIZONS})
    return pd.DataFrame(sig), pd.DataFrame(base)


# ---------------------------------------------------------------------------
def _worker(sym):
    df = load(sym)
    m = engine.Market(sym, df)
    trades, logs, recs, flips = [], [], None, []
    for c in config.COST_MODES:
        planner = V2Planner(m.df)
        tr, lg = engine.run(m, V2, c, planner=planner)
        lg["cost"] = c
        logs.append(lg)
        if len(tr):
            tr["cost"] = c
            trades.append(tr)
            f = flip_trades(m.df, tr, c)
            f["cost"] = c
            flips.append(f)
        if c == "realistic":
            recs = planner.records
            for r in recs:
                r["symbol"] = sym
    t = pd.concat(trades, ignore_index=True) if trades else pd.DataFrame()
    return sym, t, pd.concat(logs, ignore_index=True), recs, (pd.concat(flips, ignore_index=True) if flips else pd.DataFrame())


def setup_chart(df, rec, trade, title, path):
    i0 = min(x[0] for x in rec["trend_highs"] + rec["trend_lows"])
    i0 = min(i0, rec["arrival_swing_idx"])
    end_i = rec["bos_idx"] + config.V2_MAX_WAIT
    if trade is not None:
        end_i = max(end_i, int(trade["exit_idx"]))
    start, end = max(0, i0 - 10), min(len(df), end_i + 8)
    w = df.iloc[start:end].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(17, 8))
    plotting.candles(ax, w)
    X = lambda k: k - start
    # major zones
    for box, k0, col, lab in ((rec["arrival_zone"], rec["arrival_swing_idx"], "#8e24aa", "major zone (arrival)"),
                              (rec["target_zone"], rec["target_swing_idx"], "#2e7d32", "major zone (target)")):
        x0 = max(X(k0), -1)
        ax.add_patch(Rectangle((x0, box[0]), len(w) - x0, box[1] - box[0], color=col, alpha=0.15))
        ax.annotate(lab, (x0, box[1]), xytext=(2, 2), textcoords="offset points", fontsize=8, color=col)
    # trend swings
    for k, (idx, p) in enumerate(rec["trend_highs"]):
        ax.plot(X(idx), p, "v", color="navy", markersize=8)
        ax.annotate(f"H{k + 1}", (X(idx), p), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8, color="navy")
    for k, (idx, p) in enumerate(rec["trend_lows"]):
        ax.plot(X(idx), p, "^", color="navy", markersize=8)
        ax.annotate(f"L{k + 1}", (X(idx), p), xytext=(0, -13), textcoords="offset points", ha="center", fontsize=8, color="navy")
    # sweep
    ax.hlines(rec["swept_level"], X(rec["swept_idx"]), X(rec["bos_idx"]), colors="#f9a825", linestyles=":", linewidth=1.6)
    ax.annotate("swept level", (X(rec["swept_idx"]), rec["swept_level"]), xytext=(2, 3), textcoords="offset points",
                fontsize=8, color="#f57f17")
    # BoS
    ax.hlines(rec["level"], X(rec["level_idx"]), X(rec["bos_idx"]), colors="black", linewidth=1.8)
    ax.annotate("BoS", (X(rec["bos_idx"]), rec["level"]), xytext=(4, 4), textcoords="offset points", fontsize=9)
    ax.axvline(X(rec["bos_idx"]), color="black", alpha=0.2)
    # entry zone + imbalance
    zc = "#1565c0" if rec["side"] == "long" else "#e65100"
    xo = X(rec["origin_candle_idx"])
    ax.add_patch(Rectangle((xo - 0.4, rec["zone_bottom"]), X(rec["bos_idx"]) + config.V2_MAX_WAIT - xo,
                           rec["zone_top"] - rec["zone_bottom"], color=zc, alpha=0.3))
    if rec["has_imbalance"]:
        ax.add_patch(Rectangle((X(rec["fvg_k"]), rec["fvg_bottom"]), 2, rec["fvg_top"] - rec["fvg_bottom"],
                               fill=False, edgecolor="purple", hatch="///"))
    xe = X(int(trade["exit_idx"])) if trade is not None else X(rec["bos_idx"]) + config.V2_MAX_WAIT
    for y, col, lab in ((rec["entry"], "#1565c0", "entry"), (rec["stop"], "#c62828", "SL"), (rec["target"], "#2e7d32", "TP")):
        ax.hlines(y, X(rec["bos_idx"]), xe, colors=col, linestyles="--", linewidth=1.2)
        ax.annotate(f"{lab} {y:.5g}", (xe, y), xytext=(4, 0), textcoords="offset points", fontsize=8, color=col, va="center")
    if trade is not None:
        ax.plot(X(int(trade["entry_idx"])), trade["entry_price"], ">", color="#1565c0", markersize=11)
        ax.plot(X(int(trade["exit_idx"])), trade["exit_price"], "X", color="black", markersize=10)
    ys = [w["low"].min(), w["high"].max(), rec["stop"], rec["target"]]
    pad = (max(ys) - min(ys)) * 0.04
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_xlim(-1, len(w) + 8)
    plotting.date_ticks(ax, w["time"])
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"v2 already run once (see {LOCK}). Pre-registered as a single run.")
        return
    with ProcessPoolExecutor(max_workers=len(config.V2_PAIRS)) as ex:
        res = list(ex.map(_worker, config.V2_PAIRS))
    with open(LOCK, "w") as f:
        f.write("Reversal shape v2 run once on histdata 2015-2023, rules in v2_PREREGISTRATION.md\n")
    tr = pd.concat([r[1] for r in res if len(r[1])], ignore_index=True) if any(len(r[1]) for r in res) else pd.DataFrame()
    lg = pd.concat([r[2] for r in res], ignore_index=True)
    recs = [x for r in res for x in r[3]]
    flips = pd.concat([r[4] for r in res if len(r[4])], ignore_index=True) if any(len(r[4]) for r in res) else pd.DataFrame()
    tr.to_csv(os.path.join(R, "v2_trades.csv"), index=False)
    pd.DataFrame(recs).to_csv(os.path.join(R, "v2_setups.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)

    # funnel
    real_log = lg[lg["cost"] == "realistic"]
    f = real_log["status"].value_counts()
    print("V2 FUNNEL (realistic run, all 7 pairs, 2015-2023): what happened to every break of structure")
    print(f.to_string())

    if not len(tr):
        print("\nNo v2 trades at all.")
        return
    tr["year"] = pd.to_datetime(tr["entry_time"]).dt.year
    ppy = tr[tr["cost"] == "realistic"].pivot_table(index="symbol", columns="year", values="entry_idx",
                                                     aggfunc="count", fill_value=0, margins=True, margins_name="total")
    ppy.to_csv(os.path.join(R, "v2_per_pair_year.csv"))
    print("\nTRADES PER PAIR PER YEAR (realistic costs)")
    print(ppy.to_string())

    rows = []
    for c in config.COST_MODES:
        t = tr[tr["cost"] == c]
        rows.append({"group": "ALL", "cost": c, **stats.summary(t)})
        for sym, g in t.groupby("symbol"):
            rows.append({"group": sym, "cost": c, **stats.summary(g)})
        for side, g in t.groupby("side"):
            rows.append({"group": side, "cost": c, **stats.summary(g)})
    summ = pd.DataFrame(rows)
    summ.to_csv(os.path.join(R, "v2_summary.csv"), index=False)
    cols = ["group", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "ci_includes_0",
            "total_R", "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak", "avg_hold_hours"]
    print("\nRESULTS")
    print(summ[cols].to_string(index=False))

    real = tr[tr["cost"] == "realistic"]
    losers = real[real["r_after_costs"] < 0]
    if len(losers):
        print(f"\nMFE: losers that reached +1R first {100 * (losers['mfe_r'] >= 1).mean():.1f}%, "
              f"+0.5R first {100 * (losers['mfe_r'] >= 0.5).mean():.1f}%, avg MFE of losers {losers['mfe_r'].mean():.2f}R")

    # direction test 1: flip
    fl = flips
    frows = []
    for c in config.COST_MODES:
        x = fl[fl["cost"] == c]
        if not len(x):
            continue
        diff = x["real_R"] - x["flipped_R"]
        lo, hi = stats.bootstrap_ci(diff)
        frows.append({"cost": c, "trades": len(x), "avg_R_real": round(x["real_R"].mean(), 3),
                      "avg_R_flipped": round(x["flipped_R"].mean(), 3), "difference": round(diff.mean(), 3),
                      "diff_ci95": f"{lo:+.3f}..{hi:+.3f}", "diff_t": round(stats.t_stat(diff), 2),
                      "real_clearly_better": lo > 0})
    fdf = pd.DataFrame(frows)
    fdf.to_csv(os.path.join(R, "v2_flip_test.csv"), index=False)
    print("\nSIGNAL DIRECTION TEST 1: FLIP (same fill candle and price, opposite direction, mirrored stop/target)")
    print(fdf.to_string(index=False))

    # direction test 2: forward returns
    rng = np.random.default_rng(config.RANDOM_SEED)
    long_share = np.mean([r["side"] == "long" for r in recs]) if recs else 0.5
    sig_all, base_all = [], []
    for sym in config.V2_PAIRS:
        rs = [r for r in recs if r["symbol"] == sym]
        s_df, b_df = forward_returns(load(sym), rs, rng, long_share)
        sig_all.append(s_df)
        base_all.append(b_df)
    S = pd.concat(sig_all, ignore_index=True)
    B = pd.concat(base_all, ignore_index=True)
    wrows = []
    for k in config.V2_FORWARD_HORIZONS:
        col = f"fwd_{k}"
        s, b = S[col].dropna().to_numpy(), B[col].dropna().to_numpy()
        slo, shi = stats.bootstrap_ci(s)
        blo, bhi = stats.bootstrap_ci(b)
        rng2 = np.random.default_rng(config.RANDOM_SEED)
        d = np.array([rng2.choice(s, len(s)).mean() - rng2.choice(b, len(b)).mean() for _ in range(5000)])
        wrows.append({"horizon_candles": k, "setups": len(s), "signal_mean_ATR": round(s.mean(), 3),
                      "signal_ci95": f"{slo:+.3f}..{shi:+.3f}", "random_mean_ATR": round(b.mean(), 3),
                      "random_ci95": f"{blo:+.3f}..{bhi:+.3f}", "difference": round(s.mean() - b.mean(), 3),
                      "diff_ci95": f"{np.quantile(d, .025):+.3f}..{np.quantile(d, .975):+.3f}"})
    wdf = pd.DataFrame(wrows)
    wdf.to_csv(os.path.join(R, "v2_forward_test.csv"), index=False)
    print("\nSIGNAL DIRECTION TEST 2: FORWARD RETURNS after the BoS close, in the signal direction, ATR units")
    print(wdf.to_string(index=False))

    # charts of the first 20 setups (chronological)
    out = os.path.join(config.CHARTS_DIR, "v2_setups")
    os.makedirs(out, exist_ok=True)
    first = sorted(recs, key=lambda r: pd.Timestamp(r["bos_time"]))[:20]
    cache = {}
    for n, r in enumerate(first, 1):
        df = cache.setdefault(r["symbol"], load(r["symbol"]))
        t = real[(real["symbol"] == r["symbol"]) & (real["bos_idx"] == r["bos_idx"]) & (real["side"] == r["side"])]
        trade = t.iloc[0] if len(t) else None
        st = real_log[(real_log["symbol"] == r["symbol"]) & (real_log["bos_idx"] == r["bos_idx"])
                      & (real_log["side"] == r["side"])]["status"]
        status = st.iloc[0] if len(st) else "?"
        outcome = (f"{trade['exit_reason']} {trade['r_after_costs']:+.2f}R" if trade is not None else f"no trade ({status})")
        title = (f"v2 setup #{n}  {r['symbol']} {r['side']}  BoS {pd.Timestamp(r['bos_time']):%Y-%m-%d %H:%M} UTC  ->  {outcome}\n"
                 "H1-H3 / L1-L3 = trend swings, purple = major zone price arrived in, green = major target zone, "
                 "yellow dotted = swept level, black = BoS level, box = entry zone")
        name = r["symbol"].replace("=", "")
        setup_chart(df, r, trade, title, os.path.join(out, f"v2_{n:02d}_{name}_{r['side']}.png"))
    print(f"\nsaved {len(first)} setup charts in {out}")


if __name__ == "__main__":
    main()

