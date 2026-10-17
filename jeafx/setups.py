"""Imbalances, break of structure and zones  [BRIEF 5.4, 5.5, 5.6, 5.7].

Shorts are produced by running the long logic on a mirrored price series (prices multiplied by -1,
high and low swapped) and mirroring the answer back. This makes shorts the exact mirror of longs
by construction (section 8).

Every break is recorded, including the ones that are skipped, with the reason, so later steps can
show how many setups each filter removed and how those would have done.
"""
import numpy as np
import pandas as pd

import config
from jeafx.fastsearch import first_index
from jeafx.structure import analyse


# ---------------------------------------------------------------------------
# Mirroring
# ---------------------------------------------------------------------------
def mirror(df: pd.DataFrame) -> pd.DataFrame:
    m = df.copy()
    m["open"], m["close"] = -df["open"], -df["close"]
    m["high"], m["low"] = -df["low"], -df["high"]
    return m


# ---------------------------------------------------------------------------
# Imbalances (fair value gaps)  [5.5]
# ---------------------------------------------------------------------------
def bullish_fvgs(df: pd.DataFrame) -> pd.DataFrame:
    """Bullish imbalances: low[k+2] > high[k]. Gap = high[k] .. low[k+2].
    form_idx = k+2 (known at its close). fill_idx = first later candle whose low trades back
    through the whole gap (low <= gap bottom); len(df) if never. fill_idx is only ever compared
    with the current candle (fill_idx > i means 'still unfilled at candle i'), so no lookahead."""
    hi, lo = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(df)
    rows = []
    for k in range(n - 2):
        if lo[k + 2] > hi[k]:
            bottom, top = hi[k], lo[k + 2]
            fill = first_index(lo, k + 3, "<=", bottom)
            rows.append((k, k + 2, bottom, top, fill))
    return pd.DataFrame(rows, columns=["k", "form_idx", "bottom", "top", "fill_idx"])


# ---------------------------------------------------------------------------
# Break of structure + demand zone (long side)  [5.4, 5.6]
# ---------------------------------------------------------------------------
def _strong(o, c, h, l, prev_bodies, p):
    body = c - o
    rng = h - l
    if body <= 0 or rng <= 0 or len(prev_bodies) < p["body_lookback"]:
        return False
    return body >= p["body_range_min"] * rng and body >= p["body_avg_mult"] * prev_bodies.mean()


def _long_breaks(a: pd.DataFrame, fvg: pd.DataFrame, rule: str, p: dict, roll: np.ndarray) -> list:
    """a = analysed 1h frame (from structure.analyse). Returns one dict per break of an active
    swing high. Prices are in the frame's own (possibly mirrored) units."""
    o, h, l, c = (a[x].to_numpy() for x in ("open", "high", "low", "close"))
    sh, sh_idx = a["sh"].to_numpy(), a["sh_idx"].to_numpy()
    sl = a["sl"].to_numpy()
    struct = a["structure"].to_numpy()
    atr = a["atr"].to_numpy()
    bodies = np.abs(c - o)
    used = set()
    out = []
    for i in range(1, len(a)):
        lvl, lvl_idx = sh[i - 1], sh_idx[i - 1]   # active level known before candle i opened
        if np.isnan(lvl) or lvl_idx in used:
            continue
        crossed = h[i] > lvl if rule == "wick" else c[i] > lvl
        if not crossed:
            continue
        used.add(lvl_idx)                          # each swing level can be broken only once
        lvl_idx = int(lvl_idx)
        rec = {"bos_idx": i, "level": lvl, "level_idx": lvl_idx,
               "setup_type": "continuation" if struct[i - 1] == "bullish" else "reversal",
               "atr": atr[i], "reason": ""}

        if rule == "strong_close":
            lb = p["body_lookback"]
            if not _strong(o[i], c[i], h[i], l[i], bodies[max(0, i - lb):i], p):
                rec["reason"] = "weak_close"
        if roll[i] and o[i] > lvl:                 # gap alone jumped over the level (futures roll)
            rec["reason"] = rec["reason"] or "roll_gap"

        # origin low: lowest low from the broken swing candle to the BoS candle
        seg = l[lvl_idx:i + 1]
        org = lvl_idx + int(np.argmin(seg))
        rec["origin_idx"], rec["origin_low"] = org, l[org]
        # origin candle: last bearish candle at the origin or up to N candles before it
        oc = org
        for j in range(org, max(org - p["origin_lookback"], 0) - 1, -1):
            if c[j] < o[j]:
                oc = j
                break
        rec["origin_candle_idx"] = oc
        bottom, top = l[org], h[oc]
        adjusted = False
        if np.isnan(atr[i]):
            rec["reason"] = rec["reason"] or "no_atr"
        elif top - bottom > p["zone_max_atr"] * atr[i]:
            top = max(o[oc], c[oc])                # body top of the origin candle
            adjusted = True
            if top - bottom > p["zone_max_atr"] * atr[i]:
                rec["reason"] = rec["reason"] or "zone_too_big"
        rec.update(zone_bottom=bottom, zone_top=top, zone_body_top=adjusted)

        # imbalance: bullish FVG fully inside [origin candle, BoS candle], unfilled at BoS close
        ok = fvg[(fvg["k"] >= oc) & (fvg["form_idx"] <= i) & (fvg["fill_idx"] > i)]
        rec["has_imbalance"] = len(ok) > 0
        if len(ok):
            f = ok.iloc[0]
            rec.update(fvg_k=int(f.k), fvg_bottom=f.bottom, fvg_top=f.top)
        else:
            rec.update(fvg_k=np.nan, fvg_bottom=np.nan, fvg_top=np.nan)

        # liquidity sweep: origin low took out the swing low that was active before it formed
        prior_sl = sl[org - 1] if org >= 1 else np.nan
        rec["prior_swing_low"] = prior_sl
        rec["swept"] = bool(not np.isnan(prior_sl) and l[org] < prior_sl)
        out.append(rec)
    return out


def default_params() -> dict:
    return {
        "body_range_min": config.BOS_BODY_RANGE_MIN,
        "body_avg_mult": config.BOS_BODY_AVG_MULT,
        "body_lookback": config.BOS_BODY_AVG_LOOKBACK,
        "origin_lookback": config.ORIGIN_CANDLE_LOOKBACK,
        "zone_max_atr": config.ZONE_MAX_ATR_MULT,
        "zigzag": config.ZIGZAG_ATR_MULT,
    }


def find_breaks(df: pd.DataFrame, rule: str = None, params: dict = None, roll=None) -> pd.DataFrame:
    """All long and short breaks of structure on one timeframe, with zones and skip reasons.
    `reason` is empty for a break that passes strong-close / zone-size / roll checks.
    Imbalance and sweep are columns (has_imbalance, swept) so they can be switched on/off later.
    Output prices are real prices: for shorts, zone_top/zone_bottom are the supply zone edges."""
    rule = rule or config.BOS_RULE
    p = {**default_params(), **(params or {})}
    roll = np.zeros(len(df), bool) if roll is None else np.asarray(roll, bool)
    frames = []
    for side, d in (("long", df), ("short", mirror(df))):
        a, _ = analyse(d, p["zigzag"])
        recs = _long_breaks(a, bullish_fvgs(a), rule, p, roll)
        r = pd.DataFrame(recs)
        if r.empty:
            continue
        r["side"] = side
        if side == "short":   # mirror prices back; top/bottom swap
            r["level"] = -r["level"]
            r["origin_low"] = -r["origin_low"]
            r["prior_swing_low"] = -r["prior_swing_low"]
            r["zone_top"], r["zone_bottom"] = -r["zone_bottom"], -r["zone_top"]
            r["fvg_top"], r["fvg_bottom"] = -r["fvg_bottom"], -r["fvg_top"]
        frames.append(r)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).rename(columns={"origin_low": "origin_price",
                                                               "prior_swing_low": "prior_swing"})
    out["bos_time"] = df["time"].to_numpy()[out["bos_idx"]]
    out["valid"] = (out["reason"] == "") & out["has_imbalance"]   # JeaFx default filters
    return out.sort_values(["bos_idx", "side"]).reset_index(drop=True)


def order_levels(s, buffer_atr: float = None, min_stop_atr: float = 0.0) -> tuple:
    """Section 7.1/7.2: limit price and stop for a setup. Long: buy at zone top, stop below zone bottom.
    Short: sell at zone bottom, stop above zone top. Returns (entry, stop, risk).
    buffer_atr: stop distance beyond the zone edge in ATR(1h) (brief: 0.1).
    min_stop_atr: if > 0, the stop is moved out so it is at least this many ATR from entry."""
    buf = (config.STOP_ATR_BUFFER if buffer_atr is None else buffer_atr) * s["atr"]
    min_d = min_stop_atr * s["atr"]
    if s["side"] == "long":
        entry, stop = s["zone_top"], s["zone_bottom"] - buf
        stop = min(stop, entry - min_d) if min_d > 0 else stop
    else:
        entry, stop = s["zone_bottom"], s["zone_top"] + buf
        stop = max(stop, entry + min_d) if min_d > 0 else stop
    return entry, stop, abs(entry - stop)


# ---------------------------------------------------------------------------
# Zone life  [5.7 / 5.8]
# ---------------------------------------------------------------------------
def zone_life(df: pd.DataFrame, side: str, top: float, bottom: float, start: int, expiry: int):
    """Walk forward from candle `start` (first candle after the zone exists).
    Returns (end_idx, how): 'touch' first touch, 'failed' close through the far edge,
    'expired' after `expiry` candles without a touch, 'data_end'."""
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    last = min(start + expiry, len(df))
    for j in range(start, last):
        if side == "long":
            if l[j] <= top:
                return j, "touch"
            if c[j] < bottom:
                return j, "failed"
        else:
            if h[j] >= bottom:
                return j, "touch"
            if c[j] > top:
                return j, "failed"
    return (last - 1, "expired") if last < len(df) else (len(df) - 1, "data_end")
