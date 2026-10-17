"""Running many versions over many symbols in parallel, and turning trades into tables."""
import itertools
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import config
from jeafx import data, engine, stats

KEEP = ["symbol", "side", "setup_type", "context_reason", "bos_idx", "bos_time", "entry_time", "exit_time",
        "exit_reason", "target_type", "r_before_costs", "r_after_costs", "bars_held", "swept", "mfe_r", "mae_r"]


def vname(v: dict) -> str:
    return (f"{v['bos_rule']}|imb{int(v['require_imbalance'])}|ctx{int(v['use_htf_context'])}|"
            f"{v['target_mode']}|sweep{int(v['use_liquidity_sweep'])}|be{int(v['use_breakeven'])}")


def full_grid(**base) -> list:
    keys = list(config.GRID)
    out = []
    for combo in itertools.product(*(config.GRID[k] for k in keys)):
        out.append(engine.jeafx_variant(**{**base, **dict(zip(keys, combo))}))
    return out


def split_df(df: pd.DataFrame, part: str) -> pd.DataFrame:
    cut = int(len(df) * config.DEV_FRACTION)
    if part == "dev":
        return df.iloc[:cut].copy()
    if part == "all":
        return df
    raise ValueError(part)


def _worker(args):
    sym, part, variants, costs, trade_from_frac, cost_bp = args
    df = data.load_symbol(sym)
    trade_from = None
    if part == "holdout":
        trade_from = df["time"].iloc[int(len(df) * config.DEV_FRACTION)]
        d = df
    else:
        d = split_df(df, part)
    m = engine.Market(sym, d)
    frames = []
    for v in variants:
        for c in costs:
            tr, _ = engine.run(m, v, c, trade_from=trade_from, cost_bp_override=cost_bp)
            if len(tr):
                t = tr[KEEP].copy()
                t["variant"], t["cost"] = v.get("name", vname(v)), c
                frames.append(t)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run_many(symbols, variants, costs=("zero", "realistic"), part="dev", cost_bp=None, workers=None):
    workers = workers or max(1, (os.cpu_count() or 2) - 2)
    jobs = [(s, part, variants, list(costs), None, cost_bp) for s in symbols]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        parts = list(ex.map(_worker, jobs))
    parts = [p for p in parts if len(p)]
    t = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=KEEP + ["variant", "cost"])
    t["asset_class"] = t["symbol"].map(lambda s: config.INSTRUMENTS[s]["asset_class"])
    return t


def session_of(ts) -> str:
    h = pd.to_datetime(ts).hour
    for name, (a, b) in config.SESSIONS_UTC.items():
        if a <= h < b:
            return name
    return "late"


def table(trades: pd.DataFrame, by: list, col: str = "r_after_costs") -> pd.DataFrame:
    rows = []
    for key, g in trades.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key)), **stats.summary(g, col)})
    return pd.DataFrame(rows)
