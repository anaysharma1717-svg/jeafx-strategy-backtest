"""Candle charts. x axis is the candle number (no gaps for weekends); dates shown as labels."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

STATE_COLOURS = {"bullish": "#d8f0d8", "bearish": "#f6d6d6", "ranging": "#ffffff"}


def candles(ax, df, x0=0):
    """Draw candles of df on ax at x = x0, x0+1, ..."""
    for k, r in enumerate(df.itertuples(index=False)):
        x = x0 + k
        up = r.close >= r.open
        col = "#2e7d32" if up else "#c62828"
        ax.vlines(x, r.low, r.high, color=col, linewidth=0.7)
        lo, hi = min(r.open, r.close), max(r.open, r.close)
        ax.add_patch(Rectangle((x - 0.35, lo), 0.7, max(hi - lo, 1e-12), color=col))


def date_ticks(ax, times, n=8):
    step = max(len(times) // n, 1)
    pos = list(range(0, len(times), step))
    ax.set_xticks(pos)
    ax.set_xticklabels([times.iloc[p].strftime("%m-%d %H:%M") for p in pos], rotation=30, fontsize=8)


def setup_chart(df, swings, setup, zone_end, title, path, before=25, after=35):
    """One break of structure: swings, broken level, BoS candle, zone box (until its first touch /
    deletion), and the imbalance box."""
    s = setup
    start = max(0, min(int(s["level_idx"]), int(s["origin_candle_idx"])) - before)
    end = min(len(df), max(int(s["bos_idx"]), zone_end) + after)
    w = df.iloc[start:end].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(15, 7))
    candles(ax, w)
    sw = swings[(swings["idx"] >= start) & (swings["idx"] < end)]
    for r in sw.itertuples(index=False):
        ax.plot(r.idx - start, r.price, marker="v" if r.kind == "high" else "^", color="navy", markersize=8)
    x_lvl, x_bos = s["level_idx"] - start, s["bos_idx"] - start
    ax.hlines(s["level"], x_lvl, x_bos, colors="black", linewidth=1.5)
    ax.annotate("BoS", (x_bos, s["level"]), xytext=(5, 10), textcoords="offset points", fontsize=9)
    ax.axvline(x_bos, color="black", alpha=0.25)
    zc = "#1565c0" if s["side"] == "long" else "#e65100"
    x_oc = s["origin_candle_idx"] - start
    ax.add_patch(Rectangle((x_oc - 0.4, s["zone_bottom"]), zone_end - start - x_oc + 0.4,
                           s["zone_top"] - s["zone_bottom"], color=zc, alpha=0.25))
    if s["has_imbalance"]:
        xk = s["fvg_k"] - start
        ax.add_patch(Rectangle((xk, s["fvg_bottom"]), 2, s["fvg_top"] - s["fvg_bottom"],
                               fill=False, edgecolor="purple", hatch="///", linewidth=1))
    ax.set_title(title + "\n(black line = broken swing level, blue/orange box = demand/supply zone "
                 "until first touch, purple hatched = imbalance)", fontsize=10)
    date_ticks(ax, w["time"])
    ax.set_xlim(-1, len(w))
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def trade_chart(df, swings, t, s, title, path, before=20, after=12):
    """One trade: 1h swings (support/resistance), broken level, zone, imbalance, entry, SL, TP, exit.
    t = trade row, s = its setup (break) row."""
    i0 = int(min(s["level_idx"], s["origin_candle_idx"]))
    start = max(0, i0 - before)
    end = min(len(df), int(t["exit_idx"]) + after)
    w = df.iloc[start:end].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(16, 8))
    candles(ax, w)
    sw = swings[(swings["idx"] >= start) & (swings["idx"] < end)]
    for r in sw.itertuples(index=False):
        hi = r.kind == "high"
        ax.plot(r.idx - start, r.price, marker="v" if hi else "^", color="navy", markersize=8)
        ax.annotate("SH" if hi else "SL(swing)", (r.idx - start, r.price), xytext=(0, 8 if hi else -14),
                    textcoords="offset points", fontsize=7, ha="center", color="navy")
    xb, xe, xx = s["bos_idx"] - start, t["entry_idx"] - start, t["exit_idx"] - start
    ax.hlines(s["level"], s["level_idx"] - start, xb, colors="black", linewidth=1.8)
    ax.annotate("BoS level", (xb, s["level"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    zc = "#1565c0" if t["side"] == "long" else "#e65100"
    xo = s["origin_candle_idx"] - start
    ax.add_patch(Rectangle((xo - 0.4, s["zone_bottom"]), xe - xo + 0.4, s["zone_top"] - s["zone_bottom"],
                           color=zc, alpha=0.22))
    ax.annotate("zone", (xo, s["zone_top"]), xytext=(0, 3), textcoords="offset points", fontsize=8, color=zc)
    if s["has_imbalance"]:
        ax.add_patch(Rectangle((s["fvg_k"] - start, s["fvg_bottom"]), 2, s["fvg_top"] - s["fvg_bottom"],
                               fill=False, edgecolor="purple", hatch="///"))
    for y, col, lab in ((t["entry_price"], "#1565c0", "entry"), (t["stop"], "#c62828", "SL"),
                        (t["target"], "#2e7d32", f"TP ({t['target_type']})")):
        if y is None or np.isnan(y):
            continue
        ax.hlines(y, xb, xx, colors=col, linestyles="--", linewidth=1.3)
        ax.annotate(f"{lab} {y:.5g}", (xx, y), xytext=(4, 0), textcoords="offset points", fontsize=8,
                    color=col, va="center")
    if not t.get("no_trade", False):
        ax.plot(xe, t["entry_price"], marker=">", color="#1565c0", markersize=11)
        ax.plot(xx, t["exit_price"], marker="X", color="black", markersize=10)
    ax.axvline(xb, color="black", alpha=0.2)
    ax.set_title(title, fontsize=10)
    date_ticks(ax, w["time"])
    ax.set_xlim(-1, len(w) + 6)
    levels = [y for y in (t["stop"], t["target"]) if y is not None and not np.isnan(y)]
    lo = min([w["low"].min()] + levels)
    hi = max([w["high"].max()] + levels)
    pad = (hi - lo) * 0.04
    ax.set_ylim(lo - pad, hi + pad)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=105)
    plt.close(fig)


def structure_chart(df, swings, start, end, title, path):
    """Candles + swings (triangle at the swing candle, dotted line to its confirmation candle)
    + background coloured by the structure state known at each candle."""
    w = df.iloc[start:end].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(16, 7))
    for k, s in enumerate(w["structure"]):
        ax.axvspan(k - 0.5, k + 0.5, color=STATE_COLOURS[s], linewidth=0)
    candles(ax, w)
    sw = swings[(swings["idx"] >= start) & (swings["idx"] < end)]
    for s in sw.itertuples(index=False):
        x = s.idx - start
        xc = min(s.confirm_idx, end - 1) - start
        is_high = s.kind == "high"
        ax.plot(x, s.price, marker="v" if is_high else "^", color="navy", markersize=9)
        ax.hlines(s.price, x, xc, colors="navy", linestyles=":", linewidth=1)
        ax.plot(xc, s.price, marker="|", color="navy", markersize=12)
    ax.set_title(title + "\n(triangle = swing candle, dotted line ends at confirmation candle; "
                 "background green = bullish, red = bearish, white = ranging)", fontsize=10)
    date_ticks(ax, w["time"])
    ax.set_xlim(-1, len(w))
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
