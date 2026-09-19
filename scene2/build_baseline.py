#!/usr/bin/env python3
"""
從訓練資料算 wafer 層級預警用的基準，輸出 models/baseline.json

對每個 sensor：
  mu0     : 正常 wafer 的「整片平均」的平均
  sd0     : 正常 wafer 的「整片平均」的標準差（wafer 之間的變異）
  within  : 片內每顆晶片的離散度（各 wafer 片內 std 的平均）
  limit_lo/hi : 規格上下限

預設把 W1、W2 排除在「正常」之外（它們的 sensor 分佈和其他 23 片明顯不同），
可用 --exclude 改。
"""
import argparse, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_temp_models import load_all, META


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="models/baseline.json")
    ap.add_argument("--exclude", default="1,2", help="不當作正常基準的 wafer，逗號分隔")
    args = ap.parse_args()
    excl = {int(x) for x in args.exclude.split(",") if x.strip()}

    full, limits = load_all(args.data)
    sensors = [c for c in full.columns if "sensor" in c]
    normal = full[~full.W.isin(excl)]
    out = {"excluded_wafers": sorted(excl), "n_normal_wafers": int(normal.W.nunique()), "sensors": {}}
    for k, s in enumerate(sensors, 1):
        wm = normal.groupby("W")[s].mean()
        ws = normal.groupby("W")[s].std()
        out["sensors"][str(k)] = {
            "name": s,
            "mu0": float(wm.mean()),
            "sd0": float(wm.std(ddof=1)),
            "within": float(ws.mean()),
            "limit_lo": float(limits.loc[s, "lo"]),
            "limit_hi": float(limits.loc[s, "hi"]),
        }
        print(f"sensor{k}: 整片平均 {wm.mean():.3f} ± {wm.std(ddof=1):.3f}, 片內離散 {ws.mean():.3f}, limit {limits.loc[s,'lo']}~{limits.loc[s,'hi']}")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=2)
    print("寫入", args.out)


if __name__ == "__main__":
    main()
