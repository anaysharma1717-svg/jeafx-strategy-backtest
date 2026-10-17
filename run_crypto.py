"""Crypto volume / CVD experiment, DEVELOPMENT part (2020-2022): tests 1-4 and the choice of the volume multiple.
Rules: results/crypto_PREREGISTRATION.md. The holdout is run separately (run_crypto_holdout.py).

Usage: py run_crypto.py
"""
import os
from concurrent.futures import ProcessPoolExecutor

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

import config
from jeafx import data, engine, plotting, stats
from jeafx.crypto import FlowFilter, add_flow
from jeafx.indicators import atr as atr_fn
from run_changes import C1, C2, C3
from run_v2 import flip_trades, forward_returns

R = config.RESULTS_DIR
FROZEN = engine.jeafx_variant(**C1, **C2, **C3)
H = config.V2_FORWARD_HORIZONS
HOLD = pd.Timestamp(config.CRYPTO_HOLDOUT_START, tz="UTC")


def load(sym, part="dev"):
    raw = pd.read_csv(os.path.join(config.CRYPTO_DATA_DIR, f"{sym}.csv"))
    df, _ = data.clean(raw)
    df = add_flow(df)
    if part == "dev":
        df = df[df["time"] < HOLD].reset_index(drop=True)
    return df


def versions(mult):
    """name -> (use_a, use_b)"""
    return {"Base": None, f"A (vol x{mult:g})": (True, False), "B (CVD)": (False, True),
            f"A+B (vol x{mult:g})": (True, True)}


def run_versions(sym, df, vers, mult, trade_from=None, costs=config.COST_MODES):
    m = engine.Market(sym, df)
    out_tr, out_lg = [], []
    for name, ab in vers.items():
        f = None if ab is None else FlowFilter(m.df, ab[0], ab[1], mult)
        for c in costs:
            tr, lg = engine.run(m, FROZEN, c, trade_from=trade_from, setup_filter=f)
            lg["version"], lg["cost"] = name, c
            out_lg.append(lg)
            if len(tr):
                tr["version"], tr["cost"] = name, c
                out_tr.append(tr)
    return m, (pd.concat(out_tr, ignore_index=True) if out_tr else pd.DataFrame()), pd.concat(out_lg, ignore_index=True)


# ---------------------------------------------------------------------------
# Test 1: indicator alone
def indicator_events(df):
    o, c, v, avg, d = (df[x].to_numpy(float) for x in ("open", "close", "volume", "vol_avg", "delta"))
    ev = {}
    body = np.sign(c - o)
    for mult in config.CRYPTO_VOL_MULTS:
        a_true = (v >= mult * avg) & (body != 0)
        ev[f"A vol x{mult:g}"] = (np.nonzero(a_true)[0], body)
    w = config.CRYPTO_B_ALONE_WINDOW
    s5 = pd.Series(d).rolling(w).sum().to_numpy()
    b_true = (np.sign(d) == np.sign(s5)) & (d != 0)
    ev["B alone (delta + 5-candle delta agree)"] = (np.nonzero(b_true)[0], np.sign(d))
    return ev


def indicator_test_symbol(sym):
    df = load(sym)
    c = df["close"].to_numpy(float)
    a = atr_fn(df, config.ATR_PERIOD).to_numpy()
    hours = df["time"].dt.hour.to_numpy()
    n, hmax = len(c), max(H)
    valid = (np.arange(n) >= config.ATR_PERIOD + config.CRYPTO_VOL_LOOKBACK) & (np.arange(n) < n - hmax)
    pools = {h: np.nonzero(valid & (hours == h))[0] for h in range(24)}
    rng = np.random.default_rng([config.RANDOM_SEED, config.CRYPTO_SYMBOLS.index(sym)])
    rows = []
    for name, (idx, direction) in indicator_events(df).items():
        idx = idx[valid[idx]]
        sg = direction[idx]
        rnd = np.stack([rng.choice(pools[h], config.CRYPTO_RANDOM_PER_EVENT) for h in hours[idx]]) if len(idx) else np.zeros((0, 1), int)
        rec = {"symbol": sym, "indicator": name, "n": len(idx)}
        res = {}
        for k in H:
            mv = sg * (c[idx + k] - c[idx]) / a[idx]
            rm = sg[:, None] * (c[rnd + k] - c[rnd]) / a[rnd]
            res[k] = (mv, rm.mean(axis=1), (rm > 0).mean(axis=1))
        rows.append((rec, res))
    return rows


# ---------------------------------------------------------------------------
def _dev_worker(sym):
    df = load(sym)
    out_tr, out_lg, flips = [], [], []
    mk = engine.Market(sym, df)
    for name, ab, mult in _all_versions():
        f = None if ab is None else FlowFilter(mk.df, ab[0], ab[1], mult)
        for c in config.COST_MODES:
            t, lgx = engine.run(mk, FROZEN, c, setup_filter=f)
            lgx["version"], lgx["cost"] = name, c
            out_lg.append(lgx)
            if len(t):
                t["version"], t["cost"] = name, c
                out_tr.append(t)
                fl = flip_trades(mk.df, t, c)
                fl["version"], fl["cost"] = name, c
                flips.append(fl)
    tr = pd.concat(out_tr, ignore_index=True)
    lg = pd.concat(out_lg, ignore_index=True)
    # test 3: classify Base trades (realistic) by each filter
    base = tr[(tr["version"] == "Base") & (tr["cost"] == "realistic")].copy()
    b = mk.breaks(FROZEN).set_index(["bos_idx", "side"])
    for mult in config.CRYPTO_VOL_MULTS:
        ff = FlowFilter(mk.df, True, True, mult)
        chk = [ff.checks({**b.loc[(r.bos_idx, r.side)].to_dict(), "bos_idx": r.bos_idx, "side": r.side})
               for r in base.itertuples()]
        base[f"pass_A_{mult:g}"] = [x["a"] for x in chk]
        base["pass_B"] = [x["b"] for x in chk]
        base[f"pass_AB_{mult:g}"] = [x["a"] and x["b"] for x in chk]
    return sym, tr, lg, pd.concat(flips, ignore_index=True), base


def _all_versions():
    out = [("Base", None, None), ("B (CVD)", (False, True), config.CRYPTO_VOL_DEFAULT)]
    for mult in config.CRYPTO_VOL_MULTS:
        out += [(f"A (vol x{mult:g})", (True, False), mult), (f"A+B (vol x{mult:g})", (True, True), mult)]
    return out


def diff_ci(a, b, n=5000):
    rng = np.random.default_rng(config.RANDOM_SEED)
    d = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(n)])
    return np.quantile(d, 0.025), np.quantile(d, 0.975)


def chart(df, t, s, flt, title, path):
    i0 = max(0, int(min(s["level_idx"], s["origin_candle_idx"])) - 25)
    i1 = min(len(df), int(t["exit_idx"]) + 12)
    w = df.iloc[i0:i1].reset_index(drop=True)
    X = lambda k: k - i0
    fig, (ax, av, ac) = plt.subplots(3, 1, figsize=(15, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
    plotting.candles(ax, w)
    ax.hlines(s["level"], X(s["level_idx"]), X(s["bos_idx"]), colors="black", lw=1.8)
    ax.annotate("BoS", (X(s["bos_idx"]), s["level"]), xytext=(4, 4), textcoords="offset points", fontsize=9)
    zc = "#1565c0" if t["side"] == "long" else "#e65100"
    xo = X(s["origin_candle_idx"])
    ax.add_patch(Rectangle((xo - 0.4, s["zone_bottom"]), X(t["entry_idx"]) - xo + 0.4,
                           s["zone_top"] - s["zone_bottom"], color=zc, alpha=0.22))
    for y, col, lab in ((t["entry_price"], "#1565c0", "entry"), (t["stop"], "#c62828", "SL"), (t["target"], "#2e7d32", "TP")):
        ax.hlines(y, X(s["bos_idx"]), X(t["exit_idx"]), colors=col, linestyles="--", lw=1.2)
        ax.annotate(f"{lab} {y:.5g}", (X(t["exit_idx"]), y), xytext=(4, 0), textcoords="offset points", fontsize=8, color=col, va="center")
    ax.plot(X(t["entry_idx"]), t["entry_price"], ">", color="#1565c0", ms=10)
    ax.plot(X(t["exit_idx"]), t["exit_price"], "X", color="black", ms=10)
    for a_ in (ax, av, ac):
        a_.axvline(X(s["bos_idx"]), color="black", alpha=0.25)
        a_.axvspan(xo - 0.5, X(s["bos_idx"]) + 0.5, color="gold", alpha=0.08)
    up = (w["close"] >= w["open"]).to_numpy()
    av.bar(range(len(w)), w["volume"], color=np.where(up, "#2e7d32", "#c62828"), width=0.8)
    if flt is not None:
        av.plot(range(len(w)), flt.mult * w["vol_avg"], color="black", lw=1, label=f"{flt.mult:g} x avg volume (prev 20)")
        av.legend(fontsize=8, loc="upper left")
    av.set_ylabel("volume")
    ac.plot(range(len(w)), w["cvd"] - w["cvd"].iloc[0], color="#6a1b9a", lw=1.4)
    ac.set_ylabel("CVD (window)")
    ax.set_title(title, fontsize=10)
    plotting.date_ticks(ac, w["time"])
    for a_ in (ax, av, ac):
        a_.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=95)
    plt.close(fig)


def main():
    syms = config.CRYPTO_SYMBOLS
    with ProcessPoolExecutor(max_workers=len(syms)) as ex:
        dev = list(ex.map(_dev_worker, syms))
        ind = list(ex.map(indicator_test_symbol, syms))
    tr = pd.concat([d[1] for d in dev], ignore_index=True)
    lg = pd.concat([d[2] for d in dev], ignore_index=True)
    flips = pd.concat([d[3] for d in dev], ignore_index=True)
    base = pd.concat([d[4] for d in dev], ignore_index=True)
    tr.to_csv(os.path.join(R, "crypto_dev_trades.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 40)

    # ---- setting choice (pre-registered rule) ----
    real = tr[tr["cost"] == "realistic"]
    a15, a20 = real[real["version"] == "A (vol x1.5)"], real[real["version"] == "A (vol x2)"]
    pick = 2.0 if (len(a20) >= config.CRYPTO_MIN_TRADES_FOR_CHOICE and len(a20) and
                   (not len(a15) or a20["r_after_costs"].mean() > a15["r_after_costs"].mean())) else config.CRYPTO_VOL_DEFAULT
    with open(os.path.join(R, "crypto_choice.txt"), "w") as f:
        f.write(f"{pick}\n")

    # ---- test 1 ----
    rows = []
    names = sorted({r[0]["indicator"] for sym_rows in ind for r in sym_rows})
    for name in names:
        parts = [res for sym_rows in ind for rec, res in sym_rows if rec["indicator"] == name]
        for k in H:
            mv = np.concatenate([p[k][0] for p in parts])
            rb = np.concatenate([p[k][1] for p in parts])
            rp = np.concatenate([p[k][2] for p in parts])
            lo, hi = stats.bootstrap_ci(mv - rb, n=2000)
            rows.append({"indicator": name, "horizon": k, "events": len(mv), "avg_move_ATR": round(mv.mean(), 4),
                         "right_dir_%": round(100 * (mv > 0).mean(), 1), "random_avg_ATR": round(rb.mean(), 4),
                         "random_right_dir_%": round(100 * rp.mean(), 1), "difference": round((mv - rb).mean(), 4),
                         "diff_ci95": f"{lo:+.4f}..{hi:+.4f}", "ci_includes_0": lo <= 0 <= hi})
    t1 = pd.DataFrame(rows)
    t1.to_csv(os.path.join(R, "crypto_test1_indicator.csv"), index=False)
    print("TEST 1. INDICATOR ALONE (development 2020-2022, 5 perps, no zones), move in ATR units")
    print(t1.to_string(index=False))

    # ---- test 2 ----
    cols = ["version", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "ci_includes_0",
            "total_R", "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak"]
    order = [v for v, _, _ in _all_versions()]
    t2 = pd.DataFrame([{"version": v, "cost": c, **stats.summary(tr[(tr["version"] == v) & (tr["cost"] == c)])}
                       for v in order for c in config.COST_MODES])
    t2.to_csv(os.path.join(R, "crypto_test2_dev_backtests.csv"), index=False)
    print("\nTEST 2. BACKTESTS ON DEVELOPMENT DATA (frozen version + filter)")
    print(t2[cols].to_string(index=False))
    print(f"\nSETTING CHOICE (pre-registered rule, version A, realistic): x1.5 avg R "
          f"{a15['r_after_costs'].mean():+.3f} ({len(a15)} trades), x2.0 avg R {a20['r_after_costs'].mean():+.3f} "
          f"({len(a20)} trades) -> volume multiple = {pick:g}")
    by_sym = pd.DataFrame([{"version": v, "symbol": s, **stats.summary(g)}
                           for (v, s), g in real.groupby(["version", "symbol"])])
    by_sym.to_csv(os.path.join(R, "crypto_dev_by_symbol.csv"), index=False)

    # ---- test 3 ----
    rows = []
    for label, col in [(f"A (vol x{m:g})", f"pass_A_{m:g}") for m in config.CRYPTO_VOL_MULTS] + [("B (CVD)", "pass_B")] + \
                      [(f"A+B (vol x{m:g})", f"pass_AB_{m:g}") for m in config.CRYPTO_VOL_MULTS]:
        kept, rem = base[base[col]]["r_after_costs"].to_numpy(), base[~base[col]]["r_after_costs"].to_numpy()
        klo, khi = stats.bootstrap_ci(kept) if len(kept) > 1 else (np.nan, np.nan)
        rlo, rhi = stats.bootstrap_ci(rem) if len(rem) > 1 else (np.nan, np.nan)
        dlo, dhi = diff_ci(kept, rem) if len(kept) > 1 and len(rem) > 1 else (np.nan, np.nan)
        rows.append({"filter": label, "base_trades": len(base), "kept": len(kept), "removed": len(rem),
                     "avg_R_kept": round(kept.mean(), 3) if len(kept) else np.nan, "kept_ci95": f"{klo:+.3f}..{khi:+.3f}",
                     "avg_R_removed": round(rem.mean(), 3) if len(rem) else np.nan, "removed_ci95": f"{rlo:+.3f}..{rhi:+.3f}",
                     "kept_minus_removed": round(kept.mean() - rem.mean(), 3) if len(kept) and len(rem) else np.nan,
                     "diff_ci95": f"{dlo:+.3f}..{dhi:+.3f}"})
    t3 = pd.DataFrame(rows)
    t3.to_csv(os.path.join(R, "crypto_test3_removed_vs_kept.csv"), index=False)
    print("\nTEST 3. BASE TRADES REMOVED vs KEPT BY EACH FILTER (development, realistic)")
    print(t3.to_string(index=False))

    # ---- test 4 ----
    frow = []
    for v in order:
        for c in config.COST_MODES:
            x = flips[(flips["version"] == v) & (flips["cost"] == c)]
            if len(x) < 2:
                continue
            d = x["real_R"] - x["flipped_R"]
            lo, hi = stats.bootstrap_ci(d)
            frow.append({"version": v, "cost": c, "trades": len(x), "avg_R_real": round(x["real_R"].mean(), 3),
                         "avg_R_flipped": round(x["flipped_R"].mean(), 3), "difference": round(d.mean(), 3),
                         "diff_ci95": f"{lo:+.3f}..{hi:+.3f}"})
    t4f = pd.DataFrame(frow)
    rng = np.random.default_rng(config.RANDOM_SEED)
    wrow = []
    rl = lg[(lg["cost"] == "realistic") & ~lg["status"].str.startswith("filtered:")]
    for v in order:
        recs = [{"symbol": r.symbol, "bos_idx": int(r.bos_idx), "side": r.side} for r in rl[rl["version"] == v].itertuples()]
        if not recs:
            continue
        ls = np.mean([r["side"] == "long" for r in recs])
        S, B = [], []
        for sym in syms:
            s_, b_ = forward_returns(load(sym), [r for r in recs if r["symbol"] == sym], rng, ls)
            S.append(s_)
            B.append(b_)
        S, B = pd.concat(S, ignore_index=True), pd.concat(B, ignore_index=True)
        for k in H:
            s_, b_ = S[f"fwd_{k}"].dropna().to_numpy(), B[f"fwd_{k}"].dropna().to_numpy()
            lo, hi = diff_ci(s_, b_, 2000)
            wrow.append({"version": v, "horizon": k, "setups": len(s_), "signal_mean_ATR": round(s_.mean(), 3),
                         "random_mean_ATR": round(b_.mean(), 3), "difference": round(s_.mean() - b_.mean(), 3),
                         "diff_ci95": f"{lo:+.3f}..{hi:+.3f}"})
    t4w = pd.DataFrame(wrow)
    t4f.to_csv(os.path.join(R, "crypto_test4_flip.csv"), index=False)
    t4w.to_csv(os.path.join(R, "crypto_test4_forward.csv"), index=False)
    print("\nTEST 4a. FLIP TEST (development)")
    print(t4f.to_string(index=False))
    print("\nTEST 4b. FORWARD RETURNS FROM THE BoS CLOSE, signal direction vs random (development)")
    print(t4w.to_string(index=False))

    # ---- charts: 10 random traded setups per version (chosen multiple), development, realistic ----
    out = os.path.join(config.CHARTS_DIR, "crypto_setups")
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(config.RANDOM_SEED)
    cache = {}
    for v, ab, mult in _all_versions():
        if mult not in (None, pick) and ab != (False, True):
            continue
        x = real[real["version"] == v]
        for n, k in enumerate(rng.choice(len(x), min(config.CRYPTO_N_CHARTS, len(x)), replace=False), 1):
            t = x.iloc[k]
            df = cache.setdefault(t["symbol"], load(t["symbol"]))
            mk = engine.Market(t["symbol"], df)
            b = mk.breaks(FROZEN)
            s = b[(b["bos_idx"] == t["bos_idx"]) & (b["side"] == t["side"])].iloc[0]
            flt = FlowFilter(mk.df, True, True, mult or pick)     # only used to draw the volume threshold line
            title = (f"{v} #{n}  {t['symbol']} {t['side']} entry {pd.Timestamp(t['entry_time']):%Y-%m-%d %H:%M} UTC  "
                     f"exit {t['exit_reason']} {t['r_after_costs']:+.2f}R\nshaded = origin candle to BoS (impulse); "
                     "middle = volume (black line = multiple x previous-20 average), bottom = CVD")
            safe = v.replace(" ", "_").replace("(", "").replace(")", "").replace("+", "plus").replace(".", "")
            chart(mk.df, t, s, flt, title, os.path.join(out, f"{safe}_{n:02d}_{t['symbol']}.png"))
    print(f"\nsaved charts in {out}")


if __name__ == "__main__":
    main()
