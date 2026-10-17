"""Summary statistics for a list of trades  [BRIEF section 13]."""
import numpy as np
import pandas as pd
from scipy import stats as sps

import config


def bootstrap_ci(r, n=None, level=None, seed=None):
    """95% bootstrap confidence interval of the mean R."""
    r = np.asarray(r, float)
    if len(r) < 2:
        return np.nan, np.nan
    n = n or config.BOOTSTRAP_SAMPLES
    level = level or config.CONFIDENCE_LEVEL
    rng = np.random.default_rng(config.RANDOM_SEED if seed is None else seed)
    means = r[rng.integers(0, len(r), size=(n, len(r)))].mean(axis=1)
    a = (1 - level) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))


def t_stat(r):
    r = np.asarray(r, float)
    if len(r) < 2 or r.std(ddof=1) == 0:
        return np.nan
    return float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))


def longest_losing_streak(r):
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def max_drawdown_r(r):
    eq = np.cumsum(np.r_[0.0, np.asarray(r, float)])
    return float((np.maximum.accumulate(eq) - eq).max())


def max_drawdown_pct(r, risk=None):
    risk = config.RISK_PER_TRADE if risk is None else risk
    eq = np.cumprod(np.r_[1.0, 1 + risk * np.asarray(r, float)])
    return float(100 * ((np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)).max())


def summary(trades: pd.DataFrame, col: str = "r_after_costs") -> dict:
    """Section 13 metrics. Trades are ordered by exit time for drawdown and streaks."""
    if trades is None or len(trades) == 0:
        return {"trades": 0}
    t = trades.sort_values("exit_time")
    r = t[col].to_numpy(float)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    lo, hi = bootstrap_ci(r)
    hold = (pd.to_datetime(t["exit_time"]) - pd.to_datetime(t["entry_time"])).dt.total_seconds() / 3600
    return {
        "trades": len(r),
        "win_rate_%": round(100 * (r > 0).mean(), 1),
        "avg_R": round(r.mean(), 3),
        "ci95_low": round(lo, 3),
        "ci95_high": round(hi, 3),
        "t_stat": round(t_stat(r), 2),
        "ci_includes_0": bool(lo <= 0 <= hi),
        "total_R": round(r.sum(), 1),
        "profit_factor": round(wins / losses, 2) if losses > 0 else np.inf,
        "max_dd_R": round(max_drawdown_r(r), 1),
        "max_dd_%": round(max_drawdown_pct(r), 1),
        "longest_losing_streak": longest_losing_streak(r),
        "avg_hold_hours": round(hold.mean(), 1),
    }
