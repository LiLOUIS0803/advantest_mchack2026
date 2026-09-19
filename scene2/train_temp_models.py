#!/usr/bin/env python3
"""
場景二：溫度感測器預測模型訓練腳本

用法:
    python train_temp_models.py --data ../data --out models/temp_models.pkl

做的事:
  1. 讀入所有 A12345_W*_RawResult.csv
  2. 對 6 個目標 (sensor1..6) 各訓練一個 Lasso 線性模型
     - 只用流程上「在該 sensor 之前」的欄位：Suite1~14、IDDQ_A1~A11、以及更早的 sensor
     - 不用 subflow 欄位（場景一的異常就注入在那裡，用了會被拖歪）
  3. 用 leave-wafer-out (5-fold, 每折 5 片) 評估，輸出 eval_report.json / eval_report.png
  4. 把模型存成「純 numpy 權重」的 pickle，推論端不需要 sklearn

pickle 內容 (dict):
  {
    "version": 1,
    "targets": {1: "100_Main.sensor1#CP", ...},
    "models": {
      1: {"features": [test_num, ...],          # 依流程順序
          "feature_names": [...],
          "median": np.array,                    # 缺值填補用
          "mean": np.array, "scale": np.array,   # 標準化
          "coef": np.array, "intercept": float,
          "limit_lo": float, "limit_hi": float},  # 該 sensor 的規格
      ...
    }
  }
"""
import argparse, glob, json, os, pickle, re, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------- 資料讀取
META = ["PID", "Lot", "Wafer", "Site", "X", "Y", "PF", "SBin", "HBin", "Test Time"]


def load_csv(path):
    """回傳 (df, limits)。df 每列一顆晶片；limits 是每個測項的 (lo, hi)。"""
    raw = pd.read_csv(path, header=None, dtype=str)
    cols = raw.iloc[0].tolist()
    # 前 5 列: 欄名 / Pin / Test Num / High Limit / Low Limit。原檔 High/Low 標籤寫反，這裡取 min/max
    l1 = pd.to_numeric(raw.iloc[3, 10:], errors="coerce").values
    l2 = pd.to_numeric(raw.iloc[4, 10:], errors="coerce").values
    limits = pd.DataFrame({"lo": np.fmin(l1, l2), "hi": np.fmax(l1, l2)}, index=cols[10:])
    df = raw.iloc[5:].copy()
    df.columns = cols
    df = df.apply(pd.to_numeric, errors="coerce")
    df["Lot"] = raw.iloc[5:, 1].values
    return df.reset_index(drop=True), limits


def load_all(data_dir):
    frames, limits = [], None
    for p in sorted(glob.glob(os.path.join(data_dir, "A12345_W*_RawResult.csv"))):
        w = int(re.search(r"W(\d+)", os.path.basename(p)).group(1))
        df, limits = load_csv(p)
        df["W"] = w
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    return full, limits


def test_num(col):
    return int(col.split("_")[0])


# ---------------------------------------------------------------- 特徵定義
def feature_plan(test_cols):
    """
    依流程順序決定每個 sensor 可用的特徵。
    CSV 欄位順序 = 流程執行順序，所以「sensor k 之前的欄位」就是它左邊的欄位。
    """
    sensors = [c for c in test_cols if "sensor" in c]
    assert len(sensors) == 6, sensors
    pre_sensor1 = test_cols[: test_cols.index(sensors[0])]
    base = [c for c in pre_sensor1 if "Suite13" not in c]  # 540_Main.Suite13 整欄常數 0，沒有資訊
    plan = {}
    for k in range(1, 7):
        plan[k] = {"target": sensors[k - 1], "features": base + sensors[: k - 1]}
    return plan


# ---------------------------------------------------------------- 模型
def fit_lasso(X, y):
    from sklearn.linear_model import LassoCV
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler().fit(X)
    m = LassoCV(cv=5, n_alphas=40, max_iter=50000, random_state=0).fit(sc.transform(X), y)
    return {
        "mean": sc.mean_.astype(float),
        "scale": sc.scale_.astype(float),
        "coef": m.coef_.astype(float),
        "intercept": float(m.intercept_),
        "alpha": float(m.alpha_),
    }


def predict_np(model, X):
    Z = (X - model["mean"]) / model["scale"]
    return Z @ model["coef"] + model["intercept"]


def leave_wafer_out(full, feats, target, n_folds=5):
    wafers = sorted(full.W.unique())
    folds = [wafers[i::n_folds] for i in range(n_folds)]
    X_all = full[feats]
    y_all = full[target].values
    pred = np.full(len(full), np.nan)
    for f in folds:
        tr = ~full.W.isin(f).values
        te = ~tr
        med = X_all[tr].median()
        Xtr = X_all[tr].fillna(med).values
        Xte = X_all[te].fillna(med).values
        m = fit_lasso(Xtr, y_all[tr])
        pred[te] = predict_np(m, Xte)
    return pred


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="models/temp_models.pkl")
    ap.add_argument("--no-eval", action="store_true", help="跳過 leave-wafer-out 評估，只訓練")
    args = ap.parse_args()

    full, limits = load_all(args.data)
    test_cols = [c for c in full.columns if c not in META + ["W"]]
    plan = feature_plan(test_cols)
    print(f"載入 {full.W.nunique()} 片 wafer, {len(full)} 顆晶片, {len(test_cols)} 個測項")

    bundle = {"version": 1, "targets": {}, "models": {}}
    report = {}
    for k in range(1, 7):
        target, feats = plan[k]["target"], plan[k]["features"]
        X = full[feats]
        y = full[target].values
        med = X.median()
        model = fit_lasso(X.fillna(med).values, y)
        model.update(
            {
                "features": [test_num(c) for c in feats],
                "feature_names": feats,
                "median": med.values.astype(float),
                "limit_lo": float(limits.loc[target, "lo"]),
                "limit_hi": float(limits.loc[target, "hi"]),
            }
        )
        bundle["targets"][k] = target
        bundle["models"][k] = model
        n_used = int((np.abs(model["coef"]) > 1e-9).sum())
        line = f"sensor{k}: {len(feats):3d} 個可用特徵, Lasso 用到 {n_used:2d} 個, alpha={model['alpha']:.4g}"

        if not args.no_eval:
            p = leave_wafer_out(full, feats, target)
            err = np.abs(p - y)
            per_w = {int(w): float(err[full.W == w].mean()) for w in sorted(full.W.unique())}
            baseline = float(np.abs(y - y.mean()).mean())
            report[k] = {
                "target": target,
                "mae": float(err.mean()),
                "rmse": float(np.sqrt(np.mean((p - y) ** 2))),
                "max_abs_err": float(err.max()),
                "baseline_mae_predict_mean": baseline,
                "per_wafer_mae": per_w,
                "n_features_available": len(feats),
                "n_features_used": n_used,
            }
            full[f"pred_{k}"] = p
            line += f" | LWO MAE={err.mean():.4f} (猜平均={baseline:.3f}) 最大誤差={err.max():.3f}"
        print(line)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(bundle, f)
    print("模型已存到", args.out)

    if not args.no_eval:
        # 額外：sensor4 貼著上限 35，看預測能不能提前抓到超限
        t4, lim4 = plan[4]["target"], bundle["models"][4]["limit_hi"]
        actual = full[t4] > lim4
        predicted = full["pred_4"] > lim4
        report["sensor4_limit_alert"] = {
            "limit_hi": lim4,
            "n_actual_over": int(actual.sum()),
            "n_predicted_over": int(predicted.sum()),
            "hit": int((actual & predicted).sum()),
            "miss": int((actual & ~predicted).sum()),
            "false_alarm": int((~actual & predicted).sum()),
        }
        rep_path = os.path.join(os.path.dirname(args.out) or ".", "eval_report.json")
        with open(rep_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print("評估報告:", rep_path, "| sensor4 超限:", report["sensor4_limit_alert"])
        try:
            plot_eval(full, plan, os.path.join(os.path.dirname(args.out) or ".", "eval_report.png"))
        except Exception as e:  # 畫圖失敗不影響訓練
            print("畫圖略過:", e)


def plot_eval(full, plan, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for k, ax in zip(range(1, 7), axes.flat):
        y = full[plan[k]["target"]]
        p = full[f"pred_{k}"]
        ax.scatter(y, p, s=6, alpha=0.5, c=np.where(full.W.isin([1, 2]), "tab:orange", "tab:blue"))
        lo, hi = min(y.min(), p.min()), max(y.max(), p.max())
        ax.plot([lo, hi], [lo, hi], "k--", lw=1)
        mae = np.abs(p - y).mean()
        ax.set_title(f"sensor{k}  leave-wafer-out MAE={mae:.3f}")
        ax.set_xlabel("actual")
        ax.set_ylabel("predicted")
        ax.grid(alpha=0.3)
    fig.suptitle("Temperature prediction, hold-out by wafer (orange = W1/W2)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print("評估圖:", path)


if __name__ == "__main__":
    main()
