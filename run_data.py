"""Step 2: download / load every symbol, build 4h candles and print the data report.

Usage:
    py run_data.py                 # use cached CSVs in data/ where present
    py run_data.py --refresh       # force a fresh Yahoo download
    py run_data.py --symbols EURUSD=X GC=F
    py run_data.py --histdata path\\to\\DAT_ASCII_EURUSD_M1_2020.csv --as EURUSD=X
"""
import argparse
import os

import pandas as pd

import config
from jeafx import data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download from Yahoo")
    ap.add_argument("--symbols", nargs="*", default=list(config.INSTRUMENTS))
    ap.add_argument("--histdata", help="histdata.com 1 minute file to convert to 1h")
    ap.add_argument("--as", dest="as_symbol", help="symbol name for the converted histdata file")
    args = ap.parse_args()

    if args.histdata:
        path = data.resample_histdata_1m(args.histdata, args.as_symbol)
        print(f"Saved 1h candles to {path}")
        return

    rows = []
    for sym in args.symbols:
        try:
            path = data.csv_path(sym)
            if args.refresh or not os.path.exists(path):
                data.load_symbol(sym, refresh=True)  # downloads and caches
            raw = pd.read_csv(path)
            df, counts = data.clean(raw)
            info = config.INSTRUMENTS[sym]
            df4 = data.build_4h(df, info["session"])
            n_roll = int(data.flag_roll_gaps(df).sum()) if info["futures"] else 0
            rows.append(data.report_symbol(sym, df, counts, len(df4), n_roll))
            print(f"ok   {sym:13s} {len(df):6d} x 1h  {len(df4):5d} x 4h")
        except Exception as e:  # keep going so one bad symbol does not stop the report
            print(f"FAIL {sym:13s} {e}")

    rep = pd.DataFrame(rows)
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    out = os.path.join(config.RESULTS_DIR, "data_report.csv")
    rep.to_csv(out, index=False)

    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 200)
    print("\nDATA REPORT")
    print(rep.drop(columns=["largest_gaps"]).to_string(index=False))
    print("\nLargest gaps between candles:")
    for r in rows:
        print(f"  {r['symbol']:13s} {r['largest_gaps']}")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
