"""Download Binance USD-M perpetual klines (monthly zips) from data.binance.vision and build one CSV per symbol
with time, open, high, low, close, volume, taker_buy_volume (UTC).
  -> data/binance/SYMBOL.csv
Downloaded zips go to <dir>/raw/ and are only parsed as text.

Usage: py download_binance.py [SYMBOL ...]    (1h; default: all crypto symbols in config)
"""
import io
import os
import sys
import urllib.error
import urllib.request
import zipfile

import pandas as pd

import config

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/{s}/{i}/{s}-{i}-{y}-{m:02d}.zip"
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
        "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def out_dir(interval):
    return config.CRYPTO_DATA_DIR


def months():
    y, m = config.CRYPTO_FIRST_MONTH
    while (y, m) <= config.CRYPTO_LAST_MONTH:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def download(sym, interval):
    raw = os.path.join(out_dir(interval), "raw")
    os.makedirs(raw, exist_ok=True)
    for y, m in months():
        path = os.path.join(raw, f"{sym}-{interval}-{y}-{m:02d}.zip")
        if os.path.exists(path):
            continue
        for attempt in range(5):
            try:
                with urllib.request.urlopen(BASE.format(s=sym, i=interval, y=y, m=m), timeout=120) as r:
                    blob = r.read()
                with open(path, "wb") as f:
                    f.write(blob)
                break
            except urllib.error.HTTPError as e:
                if e.code != 404:          # 404 = month before the symbol was listed
                    raise
                break
            except (TimeoutError, urllib.error.URLError, ConnectionError) as e:   # network hiccup: retry
                print(f"retry {sym} {y}-{m:02d}: {e}", flush=True)
        else:
            raise RuntimeError(f"could not download {sym} {y}-{m:02d}")


def build(sym, interval):
    raw = os.path.join(out_dir(interval), "raw")
    parts = []
    for y, m in months():
        path = os.path.join(raw, f"{sym}-{interval}-{y}-{m:02d}.zip")
        if not os.path.exists(path):
            continue
        with zipfile.ZipFile(path) as zf:
            name = [n for n in zf.namelist() if n.endswith(".csv")][0]
            text = zf.read(name).decode()
        df = pd.read_csv(io.StringIO(text), header=None, names=COLS, low_memory=False)
        df = df[pd.to_numeric(df["open_time"], errors="coerce").notna()]      # drop header row if present
        parts.append(df)
    d = pd.concat(parts, ignore_index=True)
    ot = pd.to_numeric(d["open_time"]).astype("int64")
    unit = "us" if ot.max() > 1e14 else "ms"
    out = pd.DataFrame({"time": pd.to_datetime(ot, unit=unit, utc=True)})
    for c in ["open", "high", "low", "close", "volume", "taker_buy_volume"]:
        out[c] = pd.to_numeric(d[c]).to_numpy()
    out = out.drop_duplicates("time").sort_values("time")
    path = os.path.join(out_dir(interval), f"{sym}.csv")
    out.to_csv(path, index=False)
    print(f"{sym} {interval}: {len(out)} candles {out['time'].iloc[0]:%Y-%m-%d} .. {out['time'].iloc[-1]:%Y-%m-%d}", flush=True)


if __name__ == "__main__":
    interval = "1h"
    syms = sys.argv[1:] or config.CRYPTO_SYMBOLS
    for s in syms:
        download(s, interval)
        build(s, interval)
