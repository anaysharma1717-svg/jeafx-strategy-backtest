"""Backtest engine  [BRIEF sections 5.7, 6, 7, 8].

Event driven: the engine jumps from one break of structure to the next and, in between, resolves
the waiting order and the open position with numpy searches over the candles that have happened.
Every search only looks at candles up to the one being decided, so there is no lookahead.

Shorts use the same code as longs on a "flipped" view of prices (x -> -x, high <-> low), which makes
them an exact mirror (section 8).

Every break is logged with what happened to it (traded, or which filter/condition stopped it),
so later steps can measure what each filter removed.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import config
from jeafx import data, setups
from jeafx.context import HTF


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------
def jeafx_variant(**overrides) -> dict:
    """The JeaFx faithful version (section 9) built from config, with optional overrides."""
    v = {
        "bos_rule": config.BOS_RULE,
        "require_imbalance": config.REQUIRE_IMBALANCE,
        "use_htf_context": config.USE_HTF_CONTEXT,
        "target_mode": config.TARGET_MODE,
        "use_liquidity_sweep": config.USE_LIQUIDITY_SWEEP,
        "use_breakeven": config.USE_BREAKEVEN,
        "zigzag": config.ZIGZAG_ATR_MULT,
        "body_range_min": config.BOS_BODY_RANGE_MIN,
        "body_avg_mult": config.BOS_BODY_AVG_MULT,
        "min_room_r": config.MIN_ROOM_R,
        "stop_buffer_atr": config.STOP_ATR_BUFFER,
        "max_wait": config.MAX_WAIT_1H,
        "cancel_on_target_touch": config.CANCEL_ON_TARGET_TOUCH,
        "skip_gap_beyond_zone": config.SKIP_GAP_BEYOND_ZONE,
        "min_stop_atr": config.MIN_STOP_ATR,
        "target_buffer_atr": config.TARGET_BUFFER_ATR,
        "target_cap_r": config.TARGET_CAP_R,
        "breakeven_trigger_r": config.BREAKEVEN_TRIGGER_R,
    }
    v.update(overrides)
    return v


def cost_per_side(symbol: str, price: float, mode: str, cost_bp_override: float = None) -> float:
    if mode == "zero":
        return 0.0
    info = config.instrument(symbol)
    if cost_bp_override is not None:
        return price * cost_bp_override / 1e4
    return info["cost"] if info["cost_type"] == "abs" else price * info["cost"] / 1e4


# ---------------------------------------------------------------------------
# Per-symbol prepared data (cached across variants)
# ---------------------------------------------------------------------------
@dataclass
class Market:
    symbol: str
    df: pd.DataFrame
    df4: pd.DataFrame = None
    roll: np.ndarray = None
    _breaks: dict = field(default_factory=dict)
    _htf: dict = field(default_factory=dict)

    def __post_init__(self):
        info = (config.INSTRUMENTS.get(self.symbol) or config.CRYPTO_INSTRUMENTS.get(self.symbol)
                or {"session": "24h", "futures": False})
        self.df = self.df.reset_index(drop=True)
        if "close_time" not in self.df.columns:
            self.df["close_time"] = self.df["time"] + pd.Timedelta(hours=1)
        if self.df4 is None:
            self.df4 = data.build_4h(self.df, info["session"])
        self.futures = info["futures"]
        self.roll = data.flag_roll_gaps(self.df).to_numpy() if self.futures else np.zeros(len(self.df), bool)

    def _pkey(self, v):
        return (v["zigzag"], v["body_range_min"], v["body_avg_mult"])

    def params(self, v):
        return {"zigzag": v["zigzag"], "body_range_min": v["body_range_min"], "body_avg_mult": v["body_avg_mult"]}

    def breaks(self, v):
        key = (v["bos_rule"],) + self._pkey(v)
        if key not in self._breaks:
            self._breaks[key] = setups.find_breaks(self.df, v["bos_rule"], self.params(v), roll=self.roll)
        return self._breaks[key]

    def htf(self, v):
        """A fresh HTF object (zone claims are per run), built from a cached template."""
        key = self._pkey(v)
        if key not in self._htf:
            self._htf[key] = HTF(self.df, self.df4, futures=self.futures, params=self.params(v))
        h = self._htf[key]
        h.claimed = set()
        return h


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class _View:
    """Prices as seen by one side. Long: real prices. Short: x -> -x with high/low swapped."""

    def __init__(self, df):
        o, h, l, c = (df[x].to_numpy(float) for x in ("open", "high", "low", "close"))
        self.long = (o, h, l, c)
        self.short = (-o, -l, -h, -c)

    def get(self, side):
        return self.long if side == "long" else self.short


def _sgn(side):
    return 1.0 if side == "long" else -1.0


def run(m: Market, v: dict, cost_mode: str = "realistic", trade_from=None, cost_bp_override=None, planner=None,
        setup_filter=None, session=None):
    """Backtest one symbol with one variant and one cost mode.
    trade_from: optional timestamp; breaks before it are used for zone/context bookkeeping but not traded.
    planner: optional object for a different setup (e.g. Reversal shape v2). After the BoS / zone / imbalance
             filters, planner.plan(s) returns either {"status": reason} (skip) or {"entry", "stop", "target",
             "target_type", "context_reason"} in real prices; planner.commit(plan) is called when the order is
             placed. Without a planner the frozen JeaFx logic below runs unchanged.
    setup_filter: optional callable(s) -> "" (keep) or a reason string (skip), applied after every frozen rule,
             just before the order is placed (crypto volume / CVD experiment).
    session: optional object with `in_session` (bool per candle) and `sess_end` (index of the session's last candle,
             -1 outside). Setups only if the BoS candle is in session; orders can fill only until the session's last
             candle (then cancelled, "session_end"); trades are closed at that candle's close ("session_close").
    Returns (trades DataFrame, setup log DataFrame)."""
    df = m.df
    n = len(df)
    times = df["time"].to_numpy()
    view = _View(df)
    b = m.breaks(v)
    htf = m.htf(v) if (v["use_htf_context"] or v["target_mode"] == "4h") else None
    realistic = cost_mode == "realistic"
    room_min = v["min_room_r"]

    trades, log = [], []
    pending = None    # dict describing the waiting limit order
    pos_until = -1    # candle index at which the open position exits (flat after it)

    def resolve(upto):
        """Advance the waiting order (and any trade it opens) through candles <= upto."""
        nonlocal pending, pos_until
        if pending is None:
            return
        p = pending
        o, h, l, c = view.get(p["side"])
        lim = p["entry_s"]
        window_end = p["bos_idx"] + v["max_wait"]              # touch allowed on the next max_wait candles
        by_session = False
        if session is not None and session.sess_end[p["bos_idx"]] < window_end:
            window_end, by_session = int(session.sess_end[p["bos_idx"]]), True
        first, last = p["bos_idx"] + 1, min(window_end, n - 1, upto)
        if first > last and by_session and last == window_end:
            p["log"]["status"] = "session_end"              # BoS on the session's last candle
            pending = None
            return
        if first > last:
            return
        hit = np.nonzero(l[first:last + 1] <= lim)[0]
        jf = first + int(hit[0]) if len(hit) else None
        if v["cancel_on_target_touch"] and p["tgt_s"] is not None:
            # stale setup: price reached the planned target on an earlier candle than the first touch
            th = np.nonzero(h[first:last + 1] >= p["tgt_s"])[0]
            jt = first + int(th[0]) if len(th) else None
            if jt is not None and (jf is None or jt < jf):
                p["log"]["status"] = "target_before_fill"
                pending = None
                return
        if jf is None:
            if last == min(window_end, n - 1):                 # window is over
                p["log"]["status"] = ("session_end" if by_session else "expired") if window_end <= n - 1 else "data_end"
                pending = None
            return
        j = jf                            # first touch: the zone is used whatever happens now
        pending = None
        cost = p["cost"]
        if v["skip_gap_beyond_zone"] and o[j] < p["far_s"]:
            p["log"]["status"] = "gap_beyond_zone"
            return
        if o[j] < lim:
            fill = o[j]
        elif l[j] <= lim - cost:
            fill = lim
        else:
            p["log"]["status"] = "touched_no_fill"
            return
        stop_s = p["stop_s"]
        if fill <= stop_s:
            p["log"]["status"] = "gap_through_stop"
            return
        # Planned risk: the position is sized when the order is placed (limit to stop). A better fill
        # (candle opening beyond the limit) just means a smaller loss, not a smaller R unit.
        risk = lim - stop_s
        # target
        if v["target_mode"] == "1h_hh":
            tgt = h[p["bos_idx"]:j].max()        # highest high from the BoS candle up to before the fill
            ttype = "1h_hh"
            if v["target_cap_r"] and tgt - lim > v["target_cap_r"] * risk:
                tgt, ttype = lim + v["target_cap_r"] * risk, "1h_hh_capped"
        else:                                    # 4h and fixed 2R targets are planned at the BoS
            tgt, ttype = p["tgt_s"], p["ttype"]
        if v["target_mode"] in ("4h", "1h_hh") and (tgt - fill) < room_min * risk:
            p["log"]["status"] = "room_at_fill"
            return
        _open_trade(p, j, fill, risk, tgt, ttype)

    def _open_trade(p, j, fill, risk, tgt, ttype):
        nonlocal pos_until
        o, h, l, c = view.get(p["side"])
        cost = p["cost"]
        stop = p["stop_s"]
        tgt_hit_lvl = tgt + (cost if realistic else 0.0)
        end = min(j + config.MAX_BARS_IN_TRADE, n - 1)
        sess_close = session is not None and 0 <= session.sess_end[j] < end
        if sess_close:
            end = int(session.sess_end[j])                     # flat at the session's last candle
        exit_idx, exit_px, why = None, None, None
        # fill candle: stop only
        if l[j] <= stop:
            exit_idx, exit_px, why = j, stop, "stop"
        else:
            seg = slice(j + 1, end + 1)
            s_hits = np.nonzero(l[seg] <= stop)[0]
            t_hits = np.nonzero(h[seg] >= tgt_hit_lvl)[0]
            s1 = j + 1 + s_hits[0] if len(s_hits) else None
            t1 = j + 1 + t_hits[0] if len(t_hits) else None
            if v["use_breakeven"]:
                be_hits = np.nonzero(h[seg] >= fill + v["breakeven_trigger_r"] * risk)[0]
                be = j + 1 + be_hits[0] if len(be_hits) else None
                first_exit = min(x for x in (s1, t1, end + 1) if x is not None)
                if be is not None and be < first_exit:
                    stop = fill                    # breakeven from the next candle on
                    seg2 = slice(be + 1, end + 1)
                    s2 = np.nonzero(l[seg2] <= stop)[0]
                    s1 = be + 1 + s2[0] if len(s2) else None
            if s1 is not None and (t1 is None or s1 <= t1):
                exit_idx, why = s1, "stop" if stop != fill else "breakeven"
                exit_px = o[s1] if o[s1] < stop else stop
            elif t1 is not None:
                exit_idx, why = t1, "target"
                exit_px = o[t1] if o[t1] >= tgt else tgt
            else:
                exit_idx, why = end, ("session_close" if sess_close else
                                      "time" if end == j + config.MAX_BARS_IN_TRADE else "data_end")
                exit_px = c[end]
        # MFE / MAE in planned R, counting only prices known to come after the fill and before the exit
        if exit_idx == j:
            mfe = 0.0
            adv = [l[j], exit_px]
        else:
            fav = [c[j], o[exit_idx]] + list(h[j + 1:exit_idx])
            adv = [l[j], o[exit_idx]] + list(l[j + 1:exit_idx])
            if why == "target":
                fav.append(exit_px)
            elif why in ("stop", "breakeven"):
                adv.append(exit_px)
            else:                                # time / data_end exit at the close: whole candle happened
                fav.append(h[exit_idx])
                adv.append(l[exit_idx])
            mfe = max(0.0, max(fav) - fill) / risk
        mae = max(0.0, fill - min(adv)) / risk
        sg = _sgn(p["side"])
        r_before = (exit_px - fill) / risk
        n_costs = 2 + (1 if (realistic and why in ("stop", "breakeven")) else 0)
        r_after = r_before - n_costs * cost / risk
        s = p["setup"]
        trades.append({
            "symbol": m.symbol, "side": p["side"], "setup_type": s["setup_type"],
            "context_reason": p["context_reason"], "bos_time": s["bos_time"], "bos_level": s["level"],
            "zone_top": s["zone_top"], "zone_bottom": s["zone_bottom"],
            "imbalance": (f"{s['fvg_bottom']:.6g}-{s['fvg_top']:.6g}" if s["has_imbalance"] else ""),
            "entry_time": times[j], "entry_price": sg * fill, "stop": sg * p["stop_s"],
            "target": sg * tgt, "target_type": ttype, "exit_time": times[exit_idx], "exit_price": sg * exit_px,
            "exit_reason": why, "r_before_costs": r_before, "r_after_costs": r_after,
            "bars_held": int(exit_idx - j), "cost_per_side": cost, "risk_price": risk,
            "swept": s["swept"], "bos_idx": int(s["bos_idx"]), "entry_idx": int(j), "exit_idx": int(exit_idx),
            "mfe_r": mfe, "mae_r": mae,
        })
        p["log"]["status"] = "traded"
        pos_until = exit_idx

    for s in (b.to_dict("records") if len(b) else []):
        i = int(s["bos_idx"])
        resolve(i)
        rec = {"symbol": m.symbol, "bos_idx": i, "bos_time": s["bos_time"], "side": s["side"],
               "setup_type": s["setup_type"], "status": ""}
        log.append(rec)
        # filters, in the order of the brief
        if s["reason"]:
            rec["status"] = "filtered:" + s["reason"]
            continue
        if v["require_imbalance"] and not s["has_imbalance"]:
            rec["status"] = "filtered:no_imbalance"
            continue
        if v["use_liquidity_sweep"] and not s["swept"]:
            rec["status"] = "filtered:no_sweep"
            continue
        reason = ""
        if planner is not None:
            plan = planner.plan(s)
            if "status" in plan:
                rec["status"] = plan["status"]
                continue
            sg = _sgn(s["side"])
            entry, stop = plan["entry"], plan["stop"]
            tgt_s, ttype, reason = sg * plan["target"], plan["target_type"], plan.get("context_reason", "")
            rec.update(plan_entry=entry, plan_stop=stop, plan_target=plan["target"])
            if trade_from is not None and s["bos_time"] < trade_from:
                rec["status"] = "before_trade_window"
                continue
            if pos_until > i:
                rec["status"] = "in_position"
                continue
            if pending is not None:
                pending["log"]["status"] = "replaced" if pending["side"] == s["side"] else "cancelled_opposite"
            planner.commit(plan)
            cost = cost_per_side(m.symbol, entry, cost_mode, cost_bp_override)
            rec["status"] = "waiting"
            pending = {"side": s["side"], "bos_idx": i, "entry_s": sg * entry, "stop_s": sg * stop,
                       "tgt_s": tgt_s, "ttype": ttype, "cost": cost, "setup": s, "log": rec,
                       "context_reason": reason,
                       "far_s": sg * (s["zone_bottom"] if s["side"] == "long" else s["zone_top"])}
            continue
        if htf is not None:
            ctx = htf.context(s)
            reason = ctx["context_reason"]
            rec["context_reason"] = reason
            if v["use_htf_context"]:
                if not reason:
                    rec["status"] = "filtered:context"
                    continue
                if ctx["zone_ok"]:
                    htf.claim(ctx["zone_id"])
        entry, stop, risk = setups.order_levels(s, v["stop_buffer_atr"], v["min_stop_atr"])
        sg = _sgn(s["side"])
        tgt_s, ttype = None, None
        if v["target_mode"] == "4h":
            tgt, ttype = htf.target_4h(s["side"], entry, risk, i)
            tgt_s = sg * tgt
            if ttype != "fallback_2r" and v["target_buffer_atr"]:
                tgt_s -= v["target_buffer_atr"] * s["atr"]     # in front of the 4h level
            if v["target_cap_r"] and tgt_s - sg * entry > v["target_cap_r"] * risk:
                tgt_s, ttype = sg * entry + v["target_cap_r"] * risk, ttype + "_capped"
            if (tgt_s - sg * entry) < room_min * risk:
                rec["status"] = "filtered:room"
                continue
        elif v["target_mode"] == "2r":
            tgt_s, ttype = sg * entry + config.FIXED_TARGET_R * risk, "fixed_2r"
        rec.update(plan_entry=entry, plan_stop=stop, plan_target=(sg * tgt_s if tgt_s is not None else np.nan))
        if setup_filter is not None:
            why = setup_filter(s)
            if why:
                rec["status"] = "filtered:" + why
                continue
        if session is not None and not session.in_session[i]:
            rec["status"] = "outside_session"
            continue
        if trade_from is not None and s["bos_time"] < trade_from:
            rec["status"] = "before_trade_window"
            continue
        if pos_until > i:                  # a trade that exits on this candle is flat by its close
            rec["status"] = "in_position"
            continue
        if pending is not None:            # newer valid BoS replaces (same side) or cancels (opposite)
            pending["log"]["status"] = "replaced" if pending["side"] == s["side"] else "cancelled_opposite"
        cost = cost_per_side(m.symbol, entry, cost_mode, cost_bp_override)
        rec["status"] = "waiting"
        pending = {"side": s["side"], "bos_idx": i, "entry_s": sg * entry, "stop_s": sg * stop,
                   "tgt_s": tgt_s, "ttype": ttype, "cost": cost, "setup": s, "log": rec,
                   "context_reason": reason,
                   "far_s": sg * (s["zone_bottom"] if s["side"] == "long" else s["zone_top"])}
    resolve(n - 1)
    if pending is not None:
        pending["log"]["status"] = "data_end"

    tr = pd.DataFrame(trades)
    if len(tr):
        eq = config.STARTING_EQUITY
        eqs = []
        for r in tr["r_after_costs"]:
            eq *= 1 + config.RISK_PER_TRADE * r
            eqs.append(eq)
        tr["equity_after"] = eqs
    return tr, pd.DataFrame(log)
