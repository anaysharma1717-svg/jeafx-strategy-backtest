"""Download histdata.com 1-minute ASCII data (yearly zips) for the 7 forex pairs, 2015-2023,
and turn each pair into one 1h UTC CSV in data/histdata/SYMBOL.csv.

histdata ASCII time is EST without daylight saving (UTC-5); the existing helper converts it.
Raw zips are kept in data/histdata/raw/ (downloaded data is only parsed as text, never executed).

Usage: py download_histdata.py
"""
import glob
import os
import time
import zipfile

import pandas as pd

import config
from jeafx import data

PAIRS = {"EURUSD=X": "eurusd", "GBPUSD=X": "gbpusd", "USDJPY=X": "usdjpy", "AUDUSD=X": "audusd",
         "USDCAD=X": "usdcad", "GBPJPY=X": "gbpjpy", "EURJPY=X": "eurjpy"}
YEARS = range(config.V2_FIRST_YEAR, config.V2_LAST_YEAR + 1)
RAW = os.path.join(config.V2_DATA_DIR, "raw")


def download():
    from histdata import download_hist_data as dl

    os.makedirs(RAW, exist_ok=True)
    for sym, code in PAIRS.items():
        for y in YEARS:
            if glob.glob(os.path.join(RAW, f"*{code.upper()}*{y}*.zip")):
                continue
            for attempt in range(3):
                try:
                    dl(year=str(y), month=None, pair=code, time_frame="M1", platform="ASCII",
                       output_directory=RAW, verbose=False)
                    print(f"downloaded {code} {y}", flush=True)
                    break
                except Exception as e:  # network hiccups: retry
                    print(f"retry {code} {y}: {e}", flush=True)
                    time.sleep(5)


def build():
    for sym, code in PAIRS.items():
        parts = []
        for y in YEARS:
            for z in glob.glob(os.path.join(RAW, f"*{code.upper()}*{y}*.zip")):
                with zipfile.ZipFile(z) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith(".csv"):
                            with zf.open(name) as f:
                                m = pd.read_csv(f, sep=";", header=None,
                                                names=["dt", "open", "high", "low", "close", "volume"])
                            parts.append(m)
        if not parts:
            print(f"no files for {sym}")
            continue
        m = pd.concat(parts, ignore_index=True)
        m["time"] = (pd.to_datetime(m["dt"], format="%Y%m%d %H%M%S") + pd.Timedelta(hours=5)).dt.tz_localize("UTC")
        h = (m.set_index("time").sort_index()
             .resample("1h", label="left", closed="left")
             .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
             .dropna().reset_index())
        path = os.path.join(config.V2_DATA_DIR, f"{sym}.csv")
        h[config.CSV_COLUMNS].to_csv(path, index=False)
        print(f"{sym}: {len(h)} hourly candles {h['time'].iloc[0]:%Y-%m-%d} .. {h['time'].iloc[-1]:%Y-%m-%d} -> {path}")


if __name__ == "__main__":
    download()
    build()
