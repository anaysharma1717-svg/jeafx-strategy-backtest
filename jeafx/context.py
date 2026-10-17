"""Higher timeframe (4h) context and targets  [BRIEF 5.8, 6, 7.3].

4h zones come from the same rules as 1h (5.2 to 5.6) run on 4h candles: strong-close BoS, zone size
check and an unfilled imbalance. A 4h zone is known once its 4h BoS candle has closed.

Zone life is tracked on the 1h candles that follow (finer timing, still only past candles):
  - used on its first touch (demand: 1h low <= top; supply: 1h high >= bottom)
  - deleted when a later 4h candle closes through it
  - deleted after ZONE_EXPIRY_4H 4h candles
Indices into the future (first touch, fail, expiry) are precomputed but only ever compared with the
current candle ("has it happened by candle i?"), so decisions never use future information.
"""
import numpy as np
import pandas as pd

import config
from jeafx import setups
from jeafx.fastsearch import first_index
from jeafx.structure import analyse

NEVER = np.iinfo(np.int64).max


class HTF:
    def __init__(self, df1h: pd.DataFrame, df4h: pd.DataFrame, futures: bool = False, params: dict = None):
        from jeafx.data import flag_roll_gaps

        self.d1 = df1h.reset_index(drop=True)
        self.d4 = df4h.reset_index(drop=True)
        p = {**setups.default_params(), **(params or {})}
        t1 = self.d1["time"].to_numpy()
        ct1 = self.d1["close_time"].to_numpy()
        self.h1, self.l1, self.c1 = (self.d1[x].to_numpy() for x in ("high", "low", "close"))
        ct4 = self.d4["close_time"].to_numpy()
        c4 = self.d4["close"].to_numpy()

        # first 1h candle whose close_time >= a 4h close_time: from that candle on, the 4h candle is known
        def known_at(close4):
            return np.searchsorted(ct1, close4, side="left")

        # ---- 4h structure and swing levels, mapped to each 1h candle --------------------------
        a4, _ = analyse(self.d4, p["zigzag"])
        self.a4 = a4
        k = np.searchsorted(ct4, ct1, side="right") - 1          # last 4h candle closed by each 1h close
        self.h4_row = k
        self.h4_structure = np.where(k >= 0, a4["structure"].to_numpy()[np.maximum(k, 0)], "ranging")

        # 1h index from which each 4h swing level became active (for "not closed beyond it since")
        sh, sl = a4["sh"].to_numpy(), a4["sl"].to_numpy()
        self.sh_since = self._since(sh, ct4, known_at)
        self.sl_since = self._since(sl, ct4, known_at)

        # ---- 4h zones -------------------------------------------------------------------------
        roll4 = flag_roll_gaps(self.d4).to_numpy() if futures else None
        b = setups.find_breaks(self.d4, "strong_close", p, roll=roll4)
        z = b[b["valid"]].copy() if len(b) else pd.DataFrame(columns=["side", "zone_top", "zone_bottom", "bos_idx"])
        rows = []
        for r in z.itertuples(index=False):
            close4 = ct4[r.bos_idx]
            known = known_at(close4)
            start = np.searchsorted(t1, close4, side="left")        # first 1h candle after the 4h close
            n1, n4 = len(self.l1), len(c4)
            if r.side == "long":
                hit = first_index(self.l1, start, "<=", r.zone_top)
                fl = first_index(c4, r.bos_idx + 1, "<", r.zone_bottom)
            else:
                hit = first_index(self.h1, start, ">=", r.zone_bottom)
                fl = first_index(c4, r.bos_idx + 1, ">", r.zone_top)
            touch = hit if hit < n1 else NEVER
            fail = known_at(ct4[fl]) if fl < n4 else NEVER
            exp_j = r.bos_idx + config.ZONE_EXPIRY_4H
            expire = known_at(ct4[exp_j]) if exp_j < len(ct4) else NEVER
            rows.append({"side": r.side, "top": r.zone_top, "bottom": r.zone_bottom, "bos4_idx": r.bos_idx,
                         "known": int(known), "touch": int(touch), "fail": int(fail), "expire": int(expire)})
        self.zones = pd.DataFrame(rows, columns=["side", "top", "bottom", "bos4_idx", "known", "touch", "fail", "expire"])
        # numpy copies for fast lookups
        self._zl = self.zones["side"].to_numpy() == "long"
        self._ztop = self.zones["top"].to_numpy(float)
        self._zbot = self.zones["bottom"].to_numpy(float)
        self._zknown, self._ztouch, self._zfail, self._zexp = (
            self.zones[c].to_numpy(np.int64) for c in ("known", "touch", "fail", "expire"))
        self._sh4, self._sl4 = self.a4["sh"].to_numpy(), self.a4["sl"].to_numpy()
        self.claimed = set()

    @staticmethod
    def _since(level, ct4, known_at):
        out = np.full(len(level), -1, dtype=np.int64)
        start = -1
        for j in range(len(level)):
            if j == 0 or not (level[j] == level[j - 1] or (np.isnan(level[j]) and np.isnan(level[j - 1]))):
                start = known_at(ct4[j]) if not np.isnan(level[j]) else -1
            out[j] = start
        return out

    # ------------------------------------------------------------------------------------------
    def _fresh(self, side: str, i: int) -> np.ndarray:
        """Indices of 4h zones of `side` that are known and still alive at 1h candle i (untouched up to i)."""
        same = self._zl if side == "long" else ~self._zl
        m = same & (self._zknown <= i) & (self._ztouch > i) & (self._zfail > i) & (self._zexp > i)
        return np.nonzero(m)[0]

    def context(self, s) -> dict:
        """Section 6 for one 1h setup row s (needs side, bos_idx, level_idx, origin_idx, origin_price).
        Returns trend_ok, zone_ok, zone_id, reason. Does not claim the zone (call claim())."""
        i = int(s["bos_idx"])
        want = "bullish" if s["side"] == "long" else "bearish"
        trend_ok = self.h4_structure[i] == want
        zone_id = None
        lo, org = int(s["level_idx"]), int(s["origin_idx"])
        same = self._zl if s["side"] == "long" else ~self._zl
        # the 4h zone's first touch happened on the leg into the origin, and the origin reached it
        m = (same & (self._ztouch >= lo) & (self._ztouch <= org) & (self._zknown <= self._ztouch)
             & (self._zfail > i) & (self._zexp > self._ztouch))
        if s["side"] == "long":
            m &= s["origin_price"] <= self._ztop
        else:
            m &= s["origin_price"] >= self._zbot
        cand = [int(k) for k in np.nonzero(m)[0] if int(k) not in self.claimed]
        if cand:
            zone_id = cand[-1]                 # most recent qualifying zone
        zone_ok = zone_id is not None
        reason = "both" if trend_ok and zone_ok else "trend" if trend_ok else "htf_zone" if zone_ok else ""
        return {"trend_ok": bool(trend_ok), "zone_ok": zone_ok, "zone_id": zone_id, "context_reason": reason,
                "h4_structure": self.h4_structure[i]}

    def claim(self, zone_id):
        if zone_id is not None:
            self.claimed.add(zone_id)

    def target_4h(self, side: str, entry: float, risk: float, i: int):
        """Section 7.3 JeaFx target, known at 1h candle i. Returns (price, target_type)."""
        cands = []
        if side == "long":
            b = self._zbot[self._fresh("short", i)]
            b = b[b > entry]
            if len(b):
                cands.append((float(b.min()), "4h_supply"))
            k = self.h4_row[i]
            if k >= 0:
                lvl, since = self._sh4[k], self.sh_since[k]
                if not np.isnan(lvl) and lvl > entry and since >= 0 and self.c1[since:i + 1].max() <= lvl:
                    cands.append((lvl, "4h_swing"))
            if cands:
                return min(cands)
            return entry + config.FALLBACK_TARGET_R * risk, "fallback_2r"
        t = self._ztop[self._fresh("long", i)]
        t = t[t < entry]
        if len(t):
            cands.append((float(t.max()), "4h_demand"))
        k = self.h4_row[i]
        if k >= 0:
            lvl, since = self._sl4[k], self.sl_since[k]
            if not np.isnan(lvl) and lvl < entry and since >= 0 and self.c1[since:i + 1].min() >= lvl:
                cands.append((lvl, "4h_swing"))
        if cands:
            return max(cands)
        return entry - config.FALLBACK_TARGET_R * risk, "fallback_2r"
