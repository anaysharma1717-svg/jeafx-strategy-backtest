"""Reversal shape v2  (pre-registered: results/v2_PREREGISTRATION.md).

The rules are coded once in the LONG shape (prior downtrend, final low into a major demand zone, sweep of the
previous swing low, strong close above the last lower high). Shorts use the same code on the mirrored price
series (x -> -x, high <-> low), exactly like the frozen engine, so they are the exact mirror of the short rules
written in the pre-registration.

All checks only use candles up to the BoS candle. Precomputed "first touch" / "close-through" indices point into
the future but are only compared with the BoS candle ("has it happened by now?").
"""
import numpy as np
import pandas as pd

import config
from jeafx import setups
from jeafx.indicators import atr as atr_fn
from jeafx.structure import find_swings

NEVER = np.iinfo(np.int64).max
DAY = np.timedelta64(1, "D")


def _first_after(mask: np.ndarray, start: int) -> int:
    hit = np.nonzero(mask[start:])[0]
    return start + int(hit[0]) if len(hit) else NEVER


class _SidePlanner:
    """Long-shaped v2 logic on one price view (real prices for longs, mirrored prices for shorts)."""

    def __init__(self, d: pd.DataFrame):
        self.o, self.h, self.l, self.c = (d[x].to_numpy(float) for x in ("open", "high", "low", "close"))
        self.t = d["time"].to_numpy()
        self.atr = atr_fn(d, config.ATR_PERIOD).to_numpy()
        self.sw = find_swings(d, config.ZIGZAG_ATR_MULT)                    # normal 2 x ATR swings
        major = find_swings(d, config.V2_MAJOR_ZIGZAG_ATR)                  # major 5 x ATR swings
        n = len(d)
        dem, sup = [], []
        for s in major.itertuples(index=False):
            a = self.atr[s.idx]
            if np.isnan(a):
                continue
            k, cf = int(s.idx), int(s.confirm_idx)
            if s.kind == "low":       # demand: swing low up to the body edge nearest the low
                bottom = s.price
                top = min(min(self.o[k], self.c[k]), bottom + config.V2_MAJOR_ZONE_MAX_ATR * a)
                touch = _first_after(self.l <= top, cf + 1)
                through = _first_after(self.c < bottom, cf + 1)
                dem.append((k, cf, bottom, top, touch, through))
            else:                     # supply: body edge nearest the high up to the swing high
                top = s.price
                bottom = max(max(self.o[k], self.c[k]), top - config.V2_MAJOR_ZONE_MAX_ATR * a)
                touch = _first_after(self.h >= bottom, cf + 1)
                through = _first_after(self.c > top, cf + 1)
                sup.append((k, cf, bottom, top, touch, through))
        cols = ["swing_idx", "confirm_idx", "bottom", "top", "touch", "through"]
        self.demand = pd.DataFrame(dem, columns=cols)
        self.supply = pd.DataFrame(sup, columns=cols)
        self.used = set()
        self.n = n

    def _age_ok(self, swing_idx, at_idx):
        return (self.t[at_idx] - self.t[swing_idx]) <= config.V2_MAJOR_ZONE_MAX_AGE_DAYS * DAY

    def plan(self, s_view: dict) -> dict:
        """s_view: the break in this view's prices (long-shaped). Returns a plan or {"status": reason}."""
        i = int(s_view["bos_idx"])
        a = self.atr[i]
        h3_idx = int(s_view["level_idx"])
        sw = self.sw[self.sw["confirm_idx"] <= i - 1]
        highs = sw[(sw["kind"] == "high") & (sw["idx"] <= h3_idx)].tail(config.V2_TREND_SWINGS)
        lows = sw[(sw["kind"] == "low") & (sw["idx"] < h3_idx)].tail(config.V2_TREND_SWINGS - 1)
        if len(highs) < config.V2_TREND_SWINGS or len(lows) < config.V2_TREND_SWINGS - 1 or highs["idx"].iloc[-1] != h3_idx:
            return {"status": "v2:no_trend"}
        # final low L3 = lowest low between H3 and the BoS candle (the break's origin low)
        l3_idx = int(s_view["origin_idx"])
        l3 = self.l[l3_idx]
        H = highs["price"].to_numpy()
        Hi = highs["idx"].to_numpy()
        L = np.r_[lows["price"].to_numpy(), l3]
        Li = np.r_[lows["idx"].to_numpy(), l3_idx]
        # alternate H0 < L0 < H1 < L1 < H2 < L2 < H3 < L3 in time
        order = np.ravel(np.column_stack([Hi, Li]))
        if not (np.all(np.diff(order) > 0)):
            return {"status": "v2:no_trend"}
        if not (np.all(np.diff(H) < 0) and np.all(np.diff(L) < 0)):
            return {"status": "v2:no_trend"}
        if H[0] - l3 < config.V2_TREND_MIN_RALLY_ATR * a:
            return {"status": "v2:trend_too_small"}

        # arrival: the final low reached an untouched, valid major demand zone during the final leg
        z = self.demand
        ok = ((z["confirm_idx"] < z["touch"]) & (z["touch"] >= h3_idx) & (z["touch"] <= l3_idx)
              & (l3 <= z["top"]) & (z["through"] > i))
        cand = z[ok]
        cand = cand[[self._age_ok(int(k), l3_idx) and (int(idx) not in self.used)
                     for idx, k in zip(cand.index, cand["swing_idx"])]]
        if not len(cand):
            return {"status": "v2:no_arrival"}
        arr_id = int(cand.index[-1])

        # sweep: L3 below L2, and no close more than 0.5 ATR below L2 from the first candle under L2 to the BoS
        l2, l2_idx = L[-2], int(Li[-2])
        first_under = _first_after(self.l < l2, l2_idx + 1)
        if first_under > i or not (l3 < l2):
            return {"status": "v2:no_sweep"}
        if self.c[first_under:i + 1].min() < l2 - config.V2_SWEEP_MAX_CLOSE_ATR * a:
            return {"status": "v2:no_sweep"}

        # entry / stop
        entry = s_view["zone_top"]
        stop = min(l3 - config.V2_STOP_BUFFER_ATR * a, entry - config.V2_MIN_STOP_ATR * a)
        risk = entry - stop
        # target: nearest untouched valid major supply zone above entry, its bottom edge
        zs = self.supply
        okt = ((zs["confirm_idx"] <= i) & (zs["touch"] > i) & (zs["through"] > i) & (zs["bottom"] > entry))
        tc = zs[okt]
        tc = tc[[self._age_ok(int(k), i) for k in tc["swing_idx"]]]
        if not len(tc):
            return {"status": "v2:no_target"}
        tgt_row = tc.loc[tc["bottom"].idxmin()]
        target = float(tgt_row["bottom"])
        if target - entry < config.V2_MIN_TARGET_R * risk:
            return {"status": "v2:target_lt_2R"}
        return {"entry": entry, "stop": stop, "target": target, "target_type": "major_zone",
                "context_reason": "v2", "arrival_id": arr_id,
                "detail": {"H": H, "Hi": Hi, "L": L, "Li": Li, "l2": l2, "l2_idx": l2_idx,
                           "arrival": z.loc[arr_id].to_dict(), "target_zone": tgt_row.to_dict(), "atr": a}}


class V2Planner:
    """Planner for engine.run(): one long-shaped planner per side; records every setup that passes all rules."""

    def __init__(self, df: pd.DataFrame):
        self.sides = {"long": _SidePlanner(df), "short": _SidePlanner(setups.mirror(df))}
        self.records = []

    @staticmethod
    def _to_view(s, side):
        if side == "long":
            return s
        v = dict(s)
        v["zone_top"], v["zone_bottom"] = -s["zone_bottom"], -s["zone_top"]
        v["level"] = -s["level"]
        return v

    def plan(self, s) -> dict:
        side = s["side"]
        p = self.sides[side].plan(self._to_view(s, side))
        if "status" in p:
            return p
        sg = 1.0 if side == "long" else -1.0
        out = dict(p)
        out["side"] = side
        out["entry"], out["stop"], out["target"] = sg * p["entry"], sg * p["stop"], sg * p["target"]
        det = p["detail"]
        # real-price drawing info: for a short the view's highs are real lows and vice versa
        if side == "long":
            highs, lows = (det["H"], det["Hi"]), (det["L"], det["Li"])
            arr, tz = det["arrival"], det["target_zone"]
            arr_box = (arr["bottom"], arr["top"])
            tgt_box = (tz["bottom"], tz["top"])
            swept = det["l2"]
        else:
            highs, lows = (-det["L"], det["Li"]), (-det["H"], det["Hi"])
            arr, tz = det["arrival"], det["target_zone"]
            arr_box = (-arr["top"], -arr["bottom"])
            tgt_box = (-tz["top"], -tz["bottom"])
            swept = -det["l2"]
        self.records.append({
            "side": side, "bos_idx": int(s["bos_idx"]), "bos_time": s["bos_time"], "level": s["level"],
            "level_idx": int(s["level_idx"]), "zone_top": s["zone_top"], "zone_bottom": s["zone_bottom"],
            "origin_candle_idx": int(s["origin_candle_idx"]), "has_imbalance": s["has_imbalance"],
            "fvg_k": s["fvg_k"], "fvg_top": s["fvg_top"], "fvg_bottom": s["fvg_bottom"],
            "entry": out["entry"], "stop": out["stop"], "target": out["target"], "atr": det["atr"],
            "trend_highs": list(zip(highs[1].tolist(), highs[0].tolist())),
            "trend_lows": list(zip(lows[1].tolist(), lows[0].tolist())),
            "swept_level": swept, "swept_idx": det["l2_idx"],
            "arrival_zone": arr_box, "arrival_swing_idx": int(arr["swing_idx"]),
            "target_zone": tgt_box, "target_swing_idx": int(tz["swing_idx"]),
        })
        out["record"] = len(self.records) - 1
        return out

    def commit(self, plan):
        self.sides[plan["side"]].used.add(plan["arrival_id"])
