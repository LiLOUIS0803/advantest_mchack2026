#!/usr/bin/env python3
"""
把 SmarTest 的 TestCase1_OfflineData.csv（Gemini prod_run 實際回放的資料，列=測項、欄=DUT）
轉成和訓練資料一樣的 *_RawResult.csv 格式（列=晶片、欄=測項），讓 replay_* 工具可以直接跑它。

    python convert_offline_data.py --src <...>/TestCase1_OfflineData.csv --ref ../data/A12345_W01_RawResult.csv --out ../data_gemini/B13456_W02_RawResult.csv

PF / SBin / HBin 在 offline 檔裡沒有，這裡用規格上下限自己判斷（有任一測項超限 -> PF=8, SBin=6）。
"""
import argparse, os, re
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--ref", default="../data/A12345_W01_RawResult.csv", help="拿它的表頭當欄位順序與 limit")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    ref = pd.read_csv(a.ref, header=None, dtype=str)
    cols = ref.iloc[0].tolist()
    test_cols = cols[10:]
    header_rows = ref.iloc[:5]                       # 欄名 / Pin / Test Num / High / Low
    lim1 = pd.to_numeric(ref.iloc[3, 10:], errors="coerce").values
    lim2 = pd.to_numeric(ref.iloc[4, 10:], errors="coerce").values
    lo, hi = np.fmin(lim1, lim2), np.fmax(lim1, lim2)

    # 訓練欄位: "220_Main.Suite1#CP" -> key "Main.Suite1#CP"，另外也建一個只用名稱的索引（給沒 pin 的列）
    by_full, by_core = {}, {}
    for c in test_cols:
        m = re.match(r"^\d+_(.*)$", c)
        core_pin = m.group(1)
        core = core_pin.split("#")[0]
        by_full[core_pin] = c
        by_core.setdefault(core, []).append(c)

    raw = pd.read_csv(a.src, header=0, index_col=0)
    meta = raw.iloc[:5]
    tests = raw.iloc[5:]
    dut_cols = [c for c in raw.columns if str(c).startswith("DUT")]
    vals = tests[dut_cols].apply(pd.to_numeric, errors="coerce")
    names = tests.index.astype(str)
    pins = tests["Pin"].fillna("").astype(str) if "Pin" in tests.columns else pd.Series([""] * len(tests), index=tests.index)

    out = pd.DataFrame(index=range(len(dut_cols)), columns=cols, dtype=object)
    lot = str(meta.loc["lot"].iloc[3]) if "lot" in meta.index else "UNKNOWN"
    wafer = str(meta.loc["wafer"].iloc[3]) if "wafer" in meta.index else "0"
    xs = meta.loc["x"][dut_cols].values if "x" in meta.index else [None] * len(dut_cols)
    ys = meta.loc["y"][dut_cols].values if "y" in meta.index else [None] * len(dut_cols)
    matched, unmatched = 0, []
    used = {}
    for n, p in zip(names, pins):
        key = f"{n}#{p}" if p else n
        col = by_full.get(key)
        if col is None:
            cands = by_core.get(n, [])
            i = used.get(n, 0)
            col = cands[i] if i < len(cands) else None   # 沒 pin 且同名多欄：依出現順序對應
            used[n] = i + 1
        if col is None:
            unmatched.append(key)
            continue
        out[col] = vals[names == n].iloc[used.get(n, 1) - 1 if key not in by_full else 0].values
        matched += 1

    X = out[test_cols].apply(pd.to_numeric, errors="coerce").values
    viol = ((X > hi) | (X < lo))
    viol = np.nan_to_num(viol, nan=False).any(axis=1)
    out["PID"] = np.arange(1, len(dut_cols) + 1)
    out["Lot"] = lot
    out["Wafer"] = wafer
    out["Site"] = (np.arange(len(dut_cols)) % 4) + 1
    out["X"] = xs
    out["Y"] = ys
    out["PF"] = np.where(viol, 8, 0)
    out["SBin"] = np.where(viol, 6, 1)
    out["HBin"] = np.where(viol, 6, 1)
    out["Test Time"] = 0

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="") as f:
        header_rows.to_csv(f, header=False, index=False)
        out.to_csv(f, header=False, index=False)
    print(f"對到 {matched} 個測項，未對到 {len(unmatched)}：{unmatched[:8]}")
    print(f"寫入 {a.out}: {len(out)} 顆, lot {lot} wafer {wafer}, 超限判 fail {int(viol.sum())} 顆")


if __name__ == "__main__":
    main()
