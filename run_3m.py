"""All tests on BTCUSDT 3-minute candles, New York session only (results/btc3m_PREREGISTRATION.md).

Usage: py run_3m.py report     data report + swing / zone charts
       py run_3m.py dev        development tests 1-8 and the pre-registered setting choices
       py run_3m.py holdout    the holdout, run once (locked)
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config
from jeafx import engine, grid, plotting, setups, stats
from jeafx.crypto import FlowFilter
from jeafx.indicators import atr as atr_fn
from jeafx.intraday import build_ctx, load_3m, ny_session
from jeafx.structure import analyse, find_swings
from run_changes import C1, C2, C3
from run_crypto import chart as flow_chart
from run_crypto import indicator_events
from run_dev import ONE_CHANGE
from run_v2 import flip_trades

SYM = "BTCUSDT"
R = config.RESULTS_DIR
OUT = os.path.join(R, "btc3m")
CH = os.path.join(config.CHARTS_DIR, "btc3m")
LOCK = os.path.join(R, "BTC3M_HOLDOUT_DONE.txt")
CHOICE = os.path.join(OUT, "choice.json")
H = config.V2_FORWARD_HORIZONS
WORKERS = 8
FROZEN = engine.jeafx_variant(**C1, **C2, **C3)
FROZEN_BE = engine.jeafx_variant(**C1, **C2, **C3, use_breakeven=True, breakeven_trigger_r=1.0)

_CACHE = {}


def full_df():
    if "df" not in _CACHE:
        _CACHE["df"], _CACHE["counts"] = load_3m(SYM)
    return _CACHE["df"]


def split_idx():
    return int(len(full_df()) * config.DEV_FRACTION)


def market(part):
    """Market + session for 'dev' (first 60%), 'half' (first 30%, truncation test) or 'full'."""
    if part not in _CACHE:
        df = full_df()
        d = {"dev": df.iloc[:split_idx()], "half": df.iloc[:split_idx() // 2], "full": df}[part].reset_index(drop=True)
        m = engine.Market(SYM, d, df4=build_ctx(d))
        _CACHE[part] = (m, ny_session(m.df))
    return _CACHE[part]


def _run(spec):
    """spec = (part, name, variant, cost, flow, trade_from) -> (trades, log)"""
    part, name, v, cost, flow, trade_from = spec
    m, sess = market(part)
    f = None if flow is None else FlowFilter(m.df, flow[0], flow[1], flow[2])
    tr, lg = engine.run(m, v, cost, trade_from=trade_from, setup_filter=f, session=sess)
    for x in (tr, lg):
        if len(x):
            x["version"], x["cost"] = name, cost
    return tr, lg


def run_specs(specs, workers=WORKERS):
    # keep specs with the same breaks/HTF settings in the same worker for cache reuse
    with ProcessPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_run, specs, chunksize=max(1, len(specs) // (workers * 2))))
    tr = pd.concat([r[0] for r in res if len(r[0])], ignore_index=True) if any(len(r[0]) for r in res) else pd.DataFrame()
    lg = pd.concat([r[1] for r in res if len(r[1])], ignore_index=True)
    return tr, lg


def taken(lg):
    """setups that passed every rule and were in session (an order was placed or blocked by a position)"""
    return lg[~lg["status"].str.startswith("filtered:") & (lg["status"] != "outside_session")]


def show(df, title, cols=None):
    print(f"\n{title}")
    print((df[cols] if cols else df).to_string(index=False))


# ---------------------------------------------------------------------------
def forward_vs_random(df, recs, rng, lo_idx, n_random=2000):
    c = df["close"].to_numpy(float)
    a = atr_fn(df, config.ATR_PERIOD).to_numpy()
    n, hmax = len(c), max(H)
    S = []
    for r in recs:
        i, sg = int(r["bos_idx"]), (1.0 if r["side"] == "long" else -1.0)
        if i + hmax < n:
            S.append([sg * (c[i + k] - c[i]) / a[i] for k in H])
    S = np.array(S)
    ls = np.mean([r["side"] == "long" for r in recs]) if recs else 0.5
    idx = rng.integers(max(lo_idx, config.ATR_PERIOD), n - hmax, n_random)
    sg = np.where(rng.random(n_random) < ls, 1.0, -1.0)
    B = np.array([[s_ * (c[i + k] - c[i]) / a[i] for k in H] for i, s_ in zip(idx, sg)])
    rows = []
    for j, k in enumerate(H):
        s_, b_ = S[:, j], B[:, j]
        r2 = np.random.default_rng(config.RANDOM_SEED)
        d = np.array([r2.choice(s_, len(s_)).mean() - r2.choice(b_, len(b_)).mean() for _ in range(3000)])
        rows.append({"horizon": k, "setups": len(s_), "signal_mean_ATR": round(s_.mean(), 3),
                     "random_mean_ATR": round(b_.mean(), 3), "difference": round(s_.mean() - b_.mean(), 3),
                     "diff_ci95": f"{np.quantile(d, .025):+.3f}..{np.quantile(d, .975):+.3f}"})
    return pd.DataFrame(rows)


def zone_touch(df, recs, rng, lo_idx, early=10, search=200, n_random=20):
    h, l, c = (df[x].to_numpy(float) for x in ("high", "low", "close"))
    a = atr_fn(df, config.ATR_PERIOD).to_numpy()
    hours = df["time"].dt.hour.to_numpy()
    n, hmax = len(c), max(H)
    ar = np.arange(n)
    pool = {hr: np.nonzero((hours == hr) & (ar >= max(lo_idx, config.ATR_PERIOD)) & (ar < n - hmax))[0] for hr in range(24)}
    rows, none = [], 0
    for r in recs:
        i, sg, e = int(r["bos_idx"]), (1.0 if r["side"] == "long" else -1.0), r["plan_entry"]
        seg = slice(i + 1, min(i + 1 + search, n))
        hit = np.nonzero((l[seg] <= e) if sg > 0 else (h[seg] >= e))[0]
        if not len(hit):
            none += 1
            continue
        t = i + 1 + int(hit[0])
        if t + hmax >= n:
            continue
        rnd = rng.choice(pool[hours[t]], n_random)
        row = {"delay": t - i}
        for k in H:
            row[f"m{k}"] = sg * (c[t + k] - c[t]) / a[t]
            rm = sg * (c[rnd + k] - c[rnd]) / a[rnd]
            row[f"r{k}"], row[f"p{k}"] = rm.mean(), (rm > 0).mean()
        rows.append(row)
    d = pd.DataFrame(rows)
    out = []
    for name, x in (("all", d), (f"touch <= {early}", d[d["delay"] <= early]), (f"touch > {early}", d[d["delay"] > early])):
        for k in H:
            if len(x) < 2:
                continue
            diff = x[f"m{k}"] - x[f"r{k}"]
            lo, hi = stats.bootstrap_ci(diff)
            out.append({"group": name, "horizon": k, "setups": len(x), "avg_move_ATR": round(x[f"m{k}"].mean(), 3),
                        "right_dir_%": round(100 * (x[f"m{k}"] > 0).mean(), 1), "random_avg_ATR": round(x[f"r{k}"].mean(), 3),
                        "random_right_dir_%": round(100 * x[f"p{k}"].mean(), 1), "difference": round(diff.mean(), 3),
                        "diff_ci95": f"{lo:+.3f}..{hi:+.3f}"})
    return pd.DataFrame(out), len(d), none


def flip_table(df, tr, sess_end):
    rows = []
    for (v, c), t in tr.groupby(["version", "cost"], sort=False):
        f = flip_trades(df, t, c, sess_end)
        d = f["real_R"] - f["flipped_R"]
        if len(d) < 2:
            continue
        lo, hi = stats.bootstrap_ci(d)
        rows.append({"version": v, "cost": c, "trades": len(f), "avg_R_real": round(f["real_R"].mean(), 3),
                     "avg_R_flipped": round(f["flipped_R"].mean(), 3), "difference": round(d.mean(), 3),
                     "diff_ci95": f"{lo:+.3f}..{hi:+.3f}"})
    return pd.DataFrame(rows)


def summary_table(tr, order, extra=None):
    rows = []
    for v in order:
        for c in config.COST_MODES:
            t = tr[(tr["version"] == v) & (tr["cost"] == c)] if len(tr) else tr
            rows.append({"version": v, "cost": c, **stats.summary(t), **(extra(t) if extra else {})})
    return pd.DataFrame(rows)


SUMCOLS = ["version", "cost", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "t_stat", "ci_includes_0",
           "total_R", "profit_factor", "max_dd_R", "max_dd_%", "longest_losing_streak", "avg_hold_hours"]


def losers_mfe(t):
    los = t[t["r_after_costs"] < 0] if len(t) else t
    if not len(los):
        return {}
    return {"losers_hit_+1R_%": round(100 * (los["mfe_r"] >= 1).mean(), 1),
            "losers_hit_+0.5R_%": round(100 * (los["mfe_r"] >= 0.5).mean(), 1),
            "avg_MFE_losers": round(los["mfe_r"].mean(), 2)}


# ---------------------------------------------------------------------------
def phase_report():
    df = full_df()
    c = _CACHE["counts"]
    sess = ny_session(df)
    gaps = df["time"].diff()
    missing = int(((gaps / pd.Timedelta(minutes=3)).fillna(1) - 1).clip(lower=0).sum())
    top = gaps.nlargest(3)
    cut = split_idx()
    print("DATA REPORT  BTCUSDT perpetual, 3-minute candles")
    print(f"  {df['time'].iloc[0]:%Y-%m-%d %H:%M} .. {df['time'].iloc[-1]:%Y-%m-%d %H:%M} UTC, {len(df)} candles, "
          f"missing 3m slots {missing}, dropped: {c['dropped_missing']} missing / {c['dropped_high_below_low']} high<low / "
          f"{c['dropped_zero_range']} zero-range")
    print("  largest gaps:", "; ".join(f"{df['time'].iloc[i - 1]:%Y-%m-%d %H:%M} -> {df['time'].iloc[i]:%H:%M} ({g})"
                                       for i, g in zip(top.index, top.values.astype('timedelta64[m]'))))
    print(f"  NY-session candles {int(sess.in_session.sum())} ({100 * sess.in_session.mean():.1f}%), "
          f"sessions {len(np.unique(sess.sess_end[sess.sess_end >= 0]))}")
    print(f"  development = first 60%: up to {df['time'].iloc[cut - 1]:%Y-%m-%d %H:%M}; "
          f"holdout from {df['time'].iloc[cut]:%Y-%m-%d %H:%M} UTC")
    os.makedirs(CH, exist_ok=True)
    m, s = market("dev")
    a1, sw1 = analyse(m.df)
    a4, sw4 = analyse(m.df4)
    day_end = int(np.nonzero(s.sess_end >= 0)[0][-1])
    for name, a, sw, end, n in (("3m", a1, sw1, day_end + 1, 200), ("15m", a4, sw4, len(a4), 200),
                                ("3m_week", a1, sw1, len(a1), 400)):
        p = os.path.join(CH, f"swings_{name}.png")
        plotting.structure_chart(a, sw, end - n, end, f"BTCUSDT {name} zigzag 2 x ATR(14)", p)
        print("saved", p)
    b = m.breaks(FROZEN)
    v = b[b["valid"] & s.in_session[b["bos_idx"].to_numpy()]]
    rng = np.random.default_rng(config.RANDOM_SEED)
    sw = find_swings(m.df)
    for k, j in enumerate(rng.choice(len(v), 5, replace=False), 1):
        st = v.iloc[j]
        d = m.df if st["side"] == "long" else setups.mirror(m.df)
        swx = find_swings(d)
        if st["side"] == "short":
            swx["price"] = -swx["price"]
            swx["kind"] = swx["kind"].map({"high": "low", "low": "high"})
        end, how = setups.zone_life(m.df, st["side"], st["zone_top"], st["zone_bottom"], int(st["bos_idx"]) + 1, 50)
        p = os.path.join(CH, f"zone_{k}_{st['side']}.png")
        plotting.setup_chart(m.df, swx, st, end, f"BTCUSDT 3m {st['side']} {st['setup_type']} BoS "
                             f"{st['bos_time']:%Y-%m-%d %H:%M} UTC, zone ended: {how}", p)
        print("saved", p)


# ---------------------------------------------------------------------------
def _rw(seed):
    m, sess = market("dev")
    d = m.df
    r = np.log(d["close"]).diff().dropna()
    sigma = float(r.std())
    rng = np.random.default_rng(seed)
    n, k = len(d), 12
    steps = rng.normal(0, sigma / np.sqrt(k), (n, k))
    path = float(d["close"].iloc[0]) * np.exp(np.cumsum(steps.ravel())).reshape(n, k)
    o = np.r_[path[0, 0], path[:-1, -1]]
    f = pd.DataFrame({"time": d["time"], "close_time": d["close_time"], "open": o,
                      "high": np.maximum(path.max(1), o), "low": np.minimum(path.min(1), o), "close": path[:, -1]})
    mk = engine.Market(SYM, f, df4=build_ctx(f))
    out = []
    for name, v in (("original", engine.jeafx_variant()), ("frozen", FROZEN)):
        tr, _ = engine.run(mk, v, "realistic", session=sess)
        if len(tr):
            tr["version"] = name
            out.append(tr)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def _trunc(item):
    name, v = item
    a, _ = _run(("dev", name, v, "realistic", None, None))
    b, _ = _run(("half", name, v, "realistic", None, None))
    cut = len(market("half")[0].df)
    cols = ["side", "bos_idx", "entry_idx", "exit_idx", "entry_price", "stop", "target", "exit_reason", "r_after_costs"]
    a = a[a["exit_idx"] < cut - 1] if len(a) else a
    b = b[(b["exit_reason"] != "data_end") & (b["exit_idx"] < cut - 1)] if len(b) else b
    same = len(a) == len(b) and (len(a) == 0 or a[cols].reset_index(drop=True).equals(b[cols].reset_index(drop=True)))
    return {"version": name, "trades_compared": len(a), "identical": same}


def phase_dev():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(CH, exist_ok=True)
    pd.set_option("display.width", 260, "display.max_columns", 40)
    m, sess = market("dev")
    df = m.df

    # 2. random walk + truncation
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        rw = pd.concat([x for x in ex.map(_rw, range(8)) if len(x)], ignore_index=True)
        tv = [("original", engine.jeafx_variant()),
              ("close_2r_noctx", engine.jeafx_variant(bos_rule="close", target_mode="2r", use_htf_context=False)),
              ("frozen", FROZEN)]
        trunc = pd.DataFrame(list(ex.map(_trunc, tv)))
    rows = []
    for v_, t in rw.groupby("version"):
        b_, a_ = stats.summary(t, "r_before_costs"), stats.summary(t)
        rows.append({"version": v_, "trades": len(t), "avg_R_before_costs": b_["avg_R"],
                     "ci95_before": f"{b_['ci95_low']:+.3f}..{b_['ci95_high']:+.3f}",
                     "avg_cost_R": round((t["r_before_costs"] - t["r_after_costs"]).mean(), 3),
                     "avg_R_after_costs": a_["avg_R"], "PASS (CI before costs not above 0)": b_["ci95_low"] <= 0})
    rwt = pd.DataFrame(rows)
    rwt.to_csv(os.path.join(OUT, "dev_random_walk.csv"), index=False)
    trunc.to_csv(os.path.join(OUT, "dev_truncation.csv"), index=False)
    show(rwt, "2a. RANDOM WALK (8 fake 3m series on the real development timestamps, NY session rules, realistic)")
    show(trunc, "2b. TRUNCATION TEST (development cut at 50%)")

    # 3. 144 grid (+ no-room-check) and 4. settings search
    variants = grid.full_grid()
    specs = [("dev", grid.vname(v), v, c, None, None) for v in variants for c in config.COST_MODES]
    specs += [("dev", "JeaFx no room check", engine.jeafx_variant(min_room_r=0.0), "realistic", None, None)]
    import itertools
    sv = {}
    for z, br, ba, room in itertools.product(config.SEARCH_ZIGZAG_ATR, config.SEARCH_BODY_RANGE,
                                             config.SEARCH_BODY_AVG_MULT, config.SEARCH_MIN_ROOM_R):
        name = f"zz{z}|body{br}|avg{ba}|room{room}"
        sv[name] = engine.jeafx_variant(zigzag=z, body_range_min=br, body_avg_mult=ba, min_room_r=room)
    specs += [("dev", "S:" + k, v, "realistic", None, None) for k, v in sv.items()]
    gtr, glg = run_specs(specs)
    print(f"\n(grid + settings runs: {len(specs)} backtests in {time.time() - t0:.0f}s)")
    gtr.to_csv(os.path.join(OUT, "dev_grid_trades.csv.gz"), index=False)
    gs = pd.DataFrame([{"variant": v, "cost": c, **stats.summary(t)} for (v, c), t in gtr.groupby(["version", "cost"])])
    gs.to_csv(os.path.join(OUT, "dev_grid_summary.csv"), index=False)
    one = []
    for label, ov in ONE_CHANGE.items():
        nm = grid.vname(engine.jeafx_variant(**ov))
        for c in config.COST_MODES:
            x = gs[(gs["variant"] == nm) & (gs["cost"] == c)]
            one.append({"version": label, "cost": c, **(x.iloc[0].to_dict() if len(x) else {"trades": 0})})
    one = pd.DataFrame(one)
    show(one, "3a. ORIGINAL VERSION vs CHANGING ONE RULE (development, R after costs)", SUMCOLS)
    gg = gs[gs["variant"].isin([grid.vname(v) for v in variants])]
    print("\n3b. FULL GRID (144 versions, comparison only)")
    for c in config.COST_MODES:
        x = gg[gg["cost"] == c]
        print(f"  {c:9s}: avg R > 0: {int((x['avg_R'] > 0).sum())}/{len(x)}, CI fully above 0: {int((x['ci95_low'] > 0).sum())}, "
              f"median {x['avg_R'].median():+.3f}, range {x['avg_R'].min():+.3f} .. {x['avg_R'].max():+.3f}")
    base = engine.jeafx_variant()
    real = gtr[gtr["cost"] == "realistic"]
    kept = real[real["version"] == grid.vname(base)]
    kk = set(zip(kept["side"], kept["bos_idx"]))
    frows = []
    for label, wo in {"strong close (vs close)": grid.vname({**base, "bos_rule": "close"}),
                      "imbalance required": grid.vname({**base, "require_imbalance": False}),
                      "4h(15m) context rule": grid.vname({**base, "use_htf_context": False}),
                      "room check 1.5R": "JeaFx no room check"}.items():
        w = real[real["version"] == wo]
        rem = w[[k not in kk for k in zip(w["side"], w["bos_idx"])]]
        frows.append({"filter": label, "without": len(w), "with": len(kept), "removed": len(rem),
                      "avg_R_kept": round(kept["r_after_costs"].mean(), 3) if len(kept) else np.nan,
                      "avg_R_removed": round(rem["r_after_costs"].mean(), 3) if len(rem) else np.nan,
                      "removed_ci95": "%+.3f..%+.3f" % stats.bootstrap_ci(rem["r_after_costs"]) if len(rem) > 1 else ""})
    show(pd.DataFrame(frows), "3c. WHAT EACH FILTER REMOVED (development, realistic)")

    ss = []
    for k in sv:
        t = real[real["version"] == "S:" + k]
        s_ = stats.summary(t)
        ss.append({"setting": k, **s_, "qualifies": s_.get("trades", 0) >= config.SELECT_MIN_TRADES and s_.get("avg_R", -9) > 0})
    ss = pd.DataFrame(ss).sort_values("avg_R", ascending=False)
    ss.to_csv(os.path.join(OUT, "dev_settings_search.csv"), index=False)
    q = ss[ss["qualifies"]]
    if len(q):
        best = q.iloc[0]["setting"]
        why = f"qualifying setting with the highest avg R: {best}"
    else:
        best, why = "zz2.0|body0.6|avg1.5|room1.5", "no setting qualified -> brief defaults"
    show(ss.head(5), "4. SETTINGS CHECK (top 5 by avg R; realistic; rule: >= 100 trades and positive)",
         ["setting", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high", "qualifies"])
    print(f"   settings with >= 100 trades: {int((ss['trades'] >= 100).sum())}/81, positive: {int((ss['avg_R'] > 0).sum())}/81 -> {why}")

    # 5-7. frozen, breakeven, volume / CVD versions
    vers = [("frozen", FROZEN, None), ("frozen + BE +1R", FROZEN_BE, None),
            ("B (CVD)", FROZEN, (False, True, 1.5))]
    for mlt in config.CRYPTO_VOL_MULTS:
        vers += [(f"A (vol x{mlt:g})", FROZEN, (True, False, mlt)), (f"A+B (vol x{mlt:g})", FROZEN, (True, True, mlt))]
    vtr, vlg = run_specs([("dev", n, v, c, f, None) for n, v, f in vers for c in config.COST_MODES], workers=7)
    vtr.to_csv(os.path.join(OUT, "dev_versions_trades.csv"), index=False)
    order = [n for n, _, _ in vers]
    vs = summary_table(vtr, order, losers_mfe)
    vs.to_csv(os.path.join(OUT, "dev_versions_summary.csv"), index=False)
    show(vs, "5/7. FROZEN, BREAKEVEN AND VOLUME / CVD VERSIONS (development)", SUMCOLS + ["losers_hit_+1R_%", "avg_MFE_losers"])
    vr = vtr[vtr["cost"] == "realistic"]
    a15, a20 = vr[vr["version"] == "A (vol x1.5)"], vr[vr["version"] == "A (vol x2)"]
    mult = 2.0 if (len(a20) >= config.CRYPTO_MIN_TRADES_FOR_CHOICE and
                   (not len(a15) or a20["r_after_costs"].mean() > a15["r_after_costs"].mean())) else 1.5
    print(f"   volume multiple rule: x1.5 {a15['r_after_costs'].mean():+.3f} ({len(a15)}), "
          f"x2.0 {a20['r_after_costs'].mean():+.3f} ({len(a20)}) -> {mult:g}")
    with open(CHOICE, "w") as f:
        json.dump({"original_settings": best, "volume_mult": mult, "why": why}, f)

    # 7. removed vs kept on frozen trades
    fz = vr[vr["version"] == "frozen"].copy()
    b = m.breaks(FROZEN).set_index(["bos_idx", "side"])
    rows = []
    for label, ua, ub, mlt in [("A x1.5", 1, 0, 1.5), ("A x2", 1, 0, 2.0), ("B (CVD)", 0, 1, 1.5), ("A+B x1.5", 1, 1, 1.5), ("A+B x2", 1, 1, 2.0)]:
        ff = FlowFilter(df, True, True, mlt)
        ok = []
        for r in fz.itertuples():
            c_ = ff.checks({**b.loc[(r.bos_idx, r.side)].to_dict(), "bos_idx": r.bos_idx, "side": r.side})
            ok.append((c_["a"] or not ua) and (c_["b"] or not ub))
        ok = np.array(ok, bool)
        k_, r_ = fz["r_after_costs"].to_numpy()[ok], fz["r_after_costs"].to_numpy()[~ok]
        lo, hi = stats.bootstrap_ci(k_ if len(k_) > 1 else np.r_[0, 0])
        rows.append({"filter": label, "kept": len(k_), "avg_R_kept": round(k_.mean(), 3) if len(k_) else np.nan,
                     "removed": len(r_), "avg_R_removed": round(r_.mean(), 3) if len(r_) else np.nan,
                     "kept_minus_removed": round(k_.mean() - r_.mean(), 3) if len(k_) and len(r_) else np.nan,
                     "removed_ci95": "%+.3f..%+.3f" % stats.bootstrap_ci(r_) if len(r_) > 1 else ""})
    show(pd.DataFrame(rows), "7a. FROZEN TRADES REMOVED vs KEPT BY EACH FLOW FILTER (development, realistic)")

    # 7b. indicator alone
    c = df["close"].to_numpy(float)
    a = atr_fn(df, config.ATR_PERIOD).to_numpy()
    hrs = df["time"].dt.hour.to_numpy()
    n, hmax = len(c), max(H)
    valid = (np.arange(n) >= 40) & (np.arange(n) < n - hmax)
    pools = {h_: np.nonzero(valid & (hrs == h_))[0] for h_ in range(24)}
    rng = np.random.default_rng(config.RANDOM_SEED)
    rows = []
    for name, (idx, direction) in indicator_events(df).items():
        idx = idx[valid[idx]]
        if len(idx) > 50_000:                     # sample for memory; events are pre-registered as "every candle"
            idx = np.sort(rng.choice(idx, 50_000, replace=False))
        sg = direction[idx]
        rnd = np.stack([rng.choice(pools[h_], 20) for h_ in hrs[idx]])
        for k in H:
            mv = sg * (c[idx + k] - c[idx]) / a[idx]
            rb = (sg[:, None] * (c[rnd + k] - c[rnd]) / a[rnd]).mean(1)
            lo, hi = stats.bootstrap_ci(mv - rb, n=2000)
            rows.append({"indicator": name, "horizon": k, "events": len(idx), "avg_move_ATR": round(mv.mean(), 4),
                         "right_dir_%": round(100 * (mv > 0).mean(), 1), "difference": round((mv - rb).mean(), 4),
                         "diff_ci95": f"{lo:+.4f}..{hi:+.4f}"})
    show(pd.DataFrame(rows), "7b. INDICATOR ALONE (development, all candles, overlapping events: CIs too narrow)")

    # 6. flip, forward, zone touch
    ft = flip_table(df, vtr, sess.sess_end)
    show(ft, "6a/7c. FLIP TEST (development)")
    lr = vlg[vlg["cost"] == "realistic"]
    fw = []
    for v_ in order:
        recs = taken(lr[lr["version"] == v_]).to_dict("records")
        if len(recs) > 5:
            t = forward_vs_random(df, recs, np.random.default_rng(config.RANDOM_SEED), 0)
            t.insert(0, "version", v_)
            fw.append(t)
    show(pd.concat(fw), "6b/7d. FORWARD RETURNS FROM THE BoS CLOSE vs random (development)")
    zt, nz, none = zone_touch(df, taken(lr[lr["version"] == "frozen"]).to_dict("records"),
                              np.random.default_rng(config.RANDOM_SEED), 0)
    zt.to_csv(os.path.join(OUT, "dev_zone_touch.csv"), index=False)
    show(zt, f"6c. ZONE-TOUCH TEST, frozen version (development): {nz} touched, {none} never within 200 candles")

    # 8. charts
    rng = np.random.default_rng(config.RANDOM_SEED)
    sw = find_swings(df)
    fzc = vr[vr["version"] == "frozen"]
    bb = m.breaks(FROZEN)
    os.makedirs(os.path.join(CH, "trades"), exist_ok=True)
    for k, j in enumerate(rng.choice(len(fzc), min(20, len(fzc)), replace=False), 1):
        t = fzc.iloc[j]
        s_ = bb[(bb["bos_idx"] == t["bos_idx"]) & (bb["side"] == t["side"])].iloc[0]
        plotting.trade_chart(df, sw, t, s_, f"#{k} BTCUSDT 3m frozen {t['side']} {pd.Timestamp(t['entry_time']):%Y-%m-%d %H:%M} UTC "
                             f"exit {t['exit_reason']} {t['r_after_costs']:+.2f}R", os.path.join(CH, "trades", f"trade_{k:02d}.png"))
    os.makedirs(os.path.join(CH, "flow"), exist_ok=True)
    for v_, _, fl in vers[2:]:
        if fl is not None and fl[2] != mult and fl[0]:
            continue
        x = vr[vr["version"] == v_]
        for k, j in enumerate(rng.choice(len(x), min(config.CRYPTO_N_CHARTS, len(x)), replace=False), 1):
            t = x.iloc[j]
            s_ = bb[(bb["bos_idx"] == t["bos_idx"]) & (bb["side"] == t["side"])].iloc[0]
            safe = v_.replace(" ", "_").replace("(", "").replace(")", "").replace("+", "plus").replace(".", "")
            flow_chart(df, t, s_, FlowFilter(df, True, True, fl[2]), f"{v_} #{k} BTCUSDT 3m {t['side']} "
                       f"{pd.Timestamp(t['entry_time']):%Y-%m-%d %H:%M} UTC exit {t['exit_reason']} {t['r_after_costs']:+.2f}R",
                       os.path.join(CH, "flow", f"{safe}_{k:02d}.png"))
    print(f"\nsaved charts in {CH}; choices in {CHOICE}; total {time.time() - t0:.0f}s")


# ---------------------------------------------------------------------------
def phase_holdout():
    if os.path.exists(LOCK) and "--force" not in sys.argv:
        print(f"Holdout already run once (see {LOCK}).")
        return
    ch = json.load(open(CHOICE))
    mult = ch["volume_mult"]
    zz, br, ba, rm = [float(p[len(k):]) for p, k in zip(ch["original_settings"].split("|"), ("zz", "body", "avg", "room"))]
    orig = engine.jeafx_variant(zigzag=zz, body_range_min=br, body_avg_mult=ba, min_room_r=rm)
    m, sess = market("full")
    start = m.df["time"].iloc[split_idx()]
    vers = [("original (chosen settings)", orig, None), ("frozen", FROZEN, None), ("frozen + BE +1R", FROZEN_BE, None),
            (f"A (vol x{mult:g})", FROZEN, (True, False, mult)), ("B (CVD)", FROZEN, (False, True, mult)),
            (f"A+B (vol x{mult:g})", FROZEN, (True, True, mult))]
    tr, lg = run_specs([("full", n, v, c, f, start) for n, v, f in vers for c in config.COST_MODES], workers=6)
    with open(LOCK, "w") as f:
        f.write(f"BTCUSDT 3m NY-session holdout run once (btc3m_PREREGISTRATION.md), choices {ch}\n")
    tr.to_csv(os.path.join(OUT, "holdout_trades.csv"), index=False)
    order = [n for n, _, _ in vers]
    s = summary_table(tr, order, losers_mfe)
    base = s[(s["version"] == "frozen") & (s["cost"] == "realistic")]["avg_R"].iloc[0]
    s["pass_mark"] = ""
    for k, r in s.iterrows():
        if r["cost"] == "realistic" and r.get("trades", 0):
            ok = r["avg_R"] >= 0.10 and r["ci95_low"] > 0
            if r["version"].startswith(("A", "B")):
                ok = ok and r["avg_R"] > base
            s.loc[k, "pass_mark"] = "PASS" if ok else "fail"
    s.to_csv(os.path.join(OUT, "holdout_summary.csv"), index=False)
    pd.set_option("display.width", 260, "display.max_columns", 40)
    print(f"HOLDOUT (from {start:%Y-%m-%d %H:%M} UTC), run once. Original settings: {ch['original_settings']}; volume x{mult:g}")
    print(s[SUMCOLS + ["losers_hit_+1R_%", "pass_mark"]].to_string(index=False))
    real = tr[tr["cost"] == "realistic"]
    if len(real):
        real = real.assign(year=pd.to_datetime(real["entry_time"]).dt.year)
        by = pd.DataFrame([{"version": v, "year": y, **stats.summary(g)} for (v, y), g in real.groupby(["version", "year"])])
        by.to_csv(os.path.join(OUT, "holdout_by_year.csv"), index=False)
        print("\nby year (realistic):")
        print(by[["version", "year", "trades", "win_rate_%", "avg_R", "ci95_low", "ci95_high"]].to_string(index=False))
    df = m.df
    fz = tr[tr["version"] == "frozen"]
    print("\nFLIP TEST (frozen, holdout)")
    print(flip_table(df, fz, sess.sess_end).to_string(index=False))
    recs = taken(lg[(lg["version"] == "frozen") & (lg["cost"] == "realistic")]).to_dict("records")
    recs = [r for r in recs if r["bos_time"] >= start]
    if len(recs) > 5:
        lo = split_idx()
        print("\nFORWARD RETURNS (frozen, holdout)")
        print(forward_vs_random(df, recs, np.random.default_rng(config.RANDOM_SEED), lo).to_string(index=False))
        zt, nz, none = zone_touch(df, recs, np.random.default_rng(config.RANDOM_SEED), lo)
        print(f"\nZONE-TOUCH (frozen, holdout): {nz} touched, {none} never")
        print(zt.to_string(index=False))


if __name__ == "__main__":
    {"report": phase_report, "dev": phase_dev, "holdout": phase_holdout}[sys.argv[1]]()
