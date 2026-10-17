"""Volume and CVD filters for the crypto experiment (results/crypto_PREREGISTRATION.md).
Every value at candle i uses only candles up to i."""
import numpy as np
import pandas as pd

import config


def add_flow(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["delta"] = 2 * d["taker_buy_volume"] - d["volume"]          # > 0 = aggressive buying
    d["cvd"] = d["delta"].cumsum()
    d["vol_avg"] = d["volume"].shift(1).rolling(config.CRYPTO_VOL_LOOKBACK).mean()   # previous 20 candles
    return d


class FlowFilter:
    """setup_filter for engine.run: A = volume breakout on the BoS candle, B = CVD confirmation."""

    def __init__(self, df: pd.DataFrame, use_a: bool, use_b: bool, mult: float):
        self.use_a, self.use_b, self.mult = use_a, use_b, mult
        self.vol = df["volume"].to_numpy(float)
        self.avg = df["vol_avg"].to_numpy(float)
        self.delta = df["delta"].to_numpy(float)
        self.cum = np.r_[0.0, np.cumsum(self.delta)]                 # cum[k] = sum of delta[:k]

    def checks(self, s) -> dict:
        i, oc = int(s["bos_idx"]), int(s["origin_candle_idx"])
        sg = 1.0 if s["side"] == "long" else -1.0
        a_ok = bool(self.vol[i] >= self.mult * self.avg[i]) if not np.isnan(self.avg[i]) else False
        impulse = self.cum[i + 1] - self.cum[oc]                      # delta from origin candle to BoS, inclusive
        b_ok = bool(sg * self.delta[i] > 0 and sg * impulse > 0)
        return {"a": a_ok, "b": b_ok}

    def __call__(self, s) -> str:
        c = self.checks(s)
        if self.use_a and not c["a"]:
            return "volume"
        if self.use_b and not c["b"]:
            return "cvd"
        return ""
