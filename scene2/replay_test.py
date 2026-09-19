#!/usr/bin/env python3
"""
用 CSV 模擬 Gemini 的串流回放，驗證 TempPredictor 整條路。

模擬方式：
  - 4 個 site 平行測試：PID 1~4 是同一個 touchdown，5~8 下一個，依此類推
  - 對每個 touchdown，按欄位順序（= 流程順序）一欄一欄餵入 4 個 site 的值
  - 走到 sensor k 的欄位「之前」就呼叫 predict(k)，模擬 receive_temp_predict_k
  - 然後才把 sensor k 的實際值餵進去（模擬機台真的量了）

輸出：每個 sensor 的串流 MAE、缺值統計、sensor4 超限預警表現，並和 eval_report.json 對照。
"""
import argparse, glob, json, os, re, sys, time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from temp_predictor import TempPredictor
from train_temp_models import load_csv, META


def replay_wafer(tp: TempPredictor, df: pd.DataFrame, test_cols, sensor_cols, verbose=False):
    rows = []
    t_pred = []
    df = df.sort_values("PID").reset_index(drop=True)
    X = df[test_cols].to_numpy(dtype=float)
    nums = [int(c.split("_")[0]) for c in test_cols]
    sensor_idx = {test_cols.index(c): i + 1 for i, c in enumerate(sensor_cols)}
    W, PID, SITE = df.W.to_numpy(), df.PID.to_numpy(), df.Site.to_numpy()
    for start in range(0, len(df), 4):
        idx = list(range(start, min(start + 4, len(df))))   # 一個 touchdown, 最多 4 顆
        tp.end_all()
        for j, col in enumerate(test_cols):
            if j in sensor_idx:
                k = sensor_idx[j]
                t0 = time.perf_counter()
                preds = {SITE[i]: tp.predict_site(k, SITE[i]) for i in idx}
                t_pred.append(time.perf_counter() - t0)
                for i in idx:
                    val, info = preds[SITE[i]]
                    a = X[i, j]
                    rows.append({"W": W[i], "PID": PID[i], "Site": SITE[i], "k": k,
                                 "actual": a, "pred": val,
                                 "n_missing": info["n_missing"], "over_limit_pred": info["over_limit"],
                                 "over_limit_actual": bool(a > info["limit_hi"] or a < info["limit_lo"])})
            # 餵入這一欄（sensor 欄也要餵，後面的模型會用到）；用完整欄名，pin 才不會丟掉
            for i in idx:
                tp.update(SITE[i], col, X[i, j])
    return rows, t_pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--model", default="models/temp_models.pkl")
    ap.add_argument("--wafers", default="", help="逗號分隔, 例如 2,14,25；空白=全部")
    args = ap.parse_args()

    tp = TempPredictor(args.model)
    paths = sorted(glob.glob(os.path.join(args.data, "A12345_W*_RawResult.csv")))
    want = {int(x) for x in args.wafers.split(",") if x.strip()}
    all_rows, all_t = [], []
    for p in paths:
        w = int(re.search(r"W(\d+)", os.path.basename(p)).group(1))
        if want and w not in want:
            continue
        df, _ = load_csv(p)
        df["W"] = w
        test_cols = [c for c in df.columns if c not in META + ["W"]]
        sensor_cols = [c for c in test_cols if "sensor" in c]
        rows, t = replay_wafer(tp, df, test_cols, sensor_cols)
        all_rows += rows
        all_t += t
    R = pd.DataFrame(all_rows)
    R["err"] = (R.pred - R.actual).abs()

    print(f"回放 {R.W.nunique()} 片, {len(R)} 次預測, 每次 predict 平均 {np.mean(all_t)*1e6:.0f} µs (4 site)")
    print("注意：這是用『訓練集』回放（in-sample），數字會比 leave-wafer-out 樂觀一些；目的是驗證串流路徑正確。")
    print()
    print("k  串流MAE   最大誤差  缺值次數")
    for k, g in R.groupby("k"):
        print(f"{k}  {g.err.mean():.4f}   {g.err.max():.3f}    {int((g.n_missing>0).sum())}")

    # 與離線評估對照
    rep = os.path.join(os.path.dirname(args.model) or ".", "eval_report.json")
    if os.path.exists(rep):
        er = json.load(open(rep))
        print("\n對照 leave-wafer-out MAE:", {k: round(er[k]["mae"], 4) for k in "123456" if k in er})

    g4 = R[R.k == 4]
    print("\nsensor4 超限預警 (limit 35):",
          f"實際超限 {int(g4.over_limit_actual.sum())} 顆, 預測超限 {int(g4.over_limit_pred.sum())} 顆,",
          f"命中 {int((g4.over_limit_actual & g4.over_limit_pred).sum())}, 漏報 {int((g4.over_limit_actual & ~g4.over_limit_pred).sum())},",
          f"誤報 {int((~g4.over_limit_actual & g4.over_limit_pred).sum())}")
    R.to_csv(os.path.join(os.path.dirname(args.model) or ".", "replay_predictions.csv"), index=False)
    print("逐筆結果:", os.path.join(os.path.dirname(args.model) or ".", "replay_predictions.csv"))


if __name__ == "__main__":
    main()
