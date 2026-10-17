"""Step 5: apply the 4h context rule and the 4h target to every valid 1h JeaFx setup.
No trades yet (that is step 6): this shows how many setups the context rule keeps, why,
and what kind of target each would get.

Usage: py run_context.py
"""
import os

import pandas as pd

import config
from jeafx import data, setups
from jeafx.context import HTF


def evaluate(sym):
    info = config.INSTRUMENTS[sym]
    df = data.load_symbol(sym)
    df4 = data.build_4h(df, info["session"])
    roll = data.flag_roll_gaps(df) if info["futures"] else None
    b = setups.find_breaks(df, roll=roll)
    htf = HTF(df, df4, futures=info["futures"])
    rows = []
    for _, s in b[b["valid"]].iterrows():          # time order
        ctx = htf.context(s)
        if ctx["context_reason"]:
            htf.claim(ctx["zone_id"])               # "this marks that 4h zone as used"
        entry, stop, risk = setups.order_levels(s)
        tgt, ttype = htf.target_4h(s["side"], entry, risk, int(s["bos_idx"]))
        room = abs(tgt - entry) / risk
        rows.append({**s.to_dict(), **ctx, "entry": entry, "stop": stop, "risk": risk,
                     "target": tgt, "target_type": ttype, "target_r": room})
    return pd.DataFrame(rows), htf


def main():
    out, all_rows = [], []
    for sym in config.INSTRUMENTS:
        r, htf = evaluate(sym)
        r["symbol"] = sym
        all_rows.append(r)
        ok = r[r["context_reason"] != ""]
        room_ok = ok[ok["target_r"] >= config.MIN_ROOM_R]
        out.append({
            "symbol": sym,
            "4h_zones": len(htf.zones),
            "valid_1h": len(r),
            "ctx_pass": len(ok),
            "trend_only": int((ok["context_reason"] == "trend").sum()),
            "zone_only": int((ok["context_reason"] == "htf_zone").sum()),
            "both": int((ok["context_reason"] == "both").sum()),
            "tgt_4h_zone": int(ok["target_type"].str.contains("supply|demand").sum()),
            "tgt_4h_swing": int((ok["target_type"] == "4h_swing").sum()),
            "tgt_fallback": int((ok["target_type"] == "fallback_2r").sum()),
            "median_target_R": round(ok["target_r"].median(), 2) if len(ok) else None,
            "room_ok(>=1.5R)": len(room_ok),
        })
    rep = pd.DataFrame(out)
    tot = rep.drop(columns=["symbol", "median_target_R"]).sum()
    rep = pd.concat([rep, pd.DataFrame([{"symbol": "TOTAL", **tot.to_dict()}])], ignore_index=True)
    rep.to_csv(os.path.join(config.RESULTS_DIR, "context_report.csv"), index=False)
    allr = pd.concat(all_rows, ignore_index=True)
    allr.to_csv(os.path.join(config.RESULTS_DIR, "setups_with_context.csv"), index=False)
    pd.set_option("display.width", 250)
    print("4h context and 4h targets on valid 1h JeaFx setups (before entry fills; all data)")
    print(rep.to_string(index=False))


if __name__ == "__main__":
    main()
