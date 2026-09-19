"""
待辦 2：依第 5.1 節的時序限制，把 25 片 wafer 的資料切分成 6 組 feature set
（sensor1~sensor6 各一組），分別訓練 6 個「階段性」溫度預測模型。

關鍵：CSV 的欄位順序 = SmarTest 實際執行順序（不是 test number 大小順序！）
已驗證：Suite1~14 → IDDQ_flow → sensor1 → subflow1 → sensor2 → subflow2 → ...
所以「第 k 階段可用的 feature」= 該 wafer test_cols 中，排在 sensorK 欄位「之前」的所有欄位。
這樣切出來的 feature set 精確對應 md 第 5.1 節表格，不會有 data leakage。

每個階段訓練一個 HistGradientBoostingRegressor（原生支援 NaN，不用額外補值），
用 GroupKFold（group=wafer_id）做交叉驗證，確保驗證時同一片 wafer 不會同時出現在
train/valid，避免同片內裝置高度相關造成的樂觀偏誤。
"""

from __future__ import annotations

import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold

from data_loader import SENSOR_HI_LIMIT_C, find_sensor_col, load_all_wafers

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"

EXTRA_META_FEATURES = ["Site", "X", "Y"]  # 這些在任何時間點都已知，可以放進所有階段


def build_stage_datasets(wafers) -> dict[int, dict]:
    """回傳 {stage: {"X": DataFrame, "y": Series, "groups": array, "feature_cols": [...]}}"""
    # 用第一片 wafer 的欄位順序當作 schema（所有 wafer 欄位順序理論上一致）
    schema_cols = wafers[0].test_cols
    sensor_pos = {}
    for k in range(1, 7):
        col = find_sensor_col(wafers[0], k)
        sensor_pos[k] = schema_cols.index(col)

    stage_frames = {k: [] for k in range(1, 7)}
    stage_targets = {k: [] for k in range(1, 7)}
    stage_groups = {k: [] for k in range(1, 7)}

    for wd in wafers:
        cols = wd.test_cols
        cmap = wd.canonical_map  # 原始欄名 -> "<test_num>#<pin>"，runtime 也用這個 key 對齊
        for k in range(1, 7):
            pos = sensor_pos[k]
            feature_cols = cols[:pos]  # 嚴格只用 sensorK 之前的欄位
            target_col = cols[pos]
            X = wd.df[EXTRA_META_FEATURES + feature_cols].copy()
            X = X.rename(columns=cmap)
            y = wd.df[target_col].copy()
            valid = y.notna()
            stage_frames[k].append(X[valid])
            stage_targets[k].append(y[valid])
            stage_groups[k].append(np.full(valid.sum(), wd.wafer_id))

    out = {}
    for k in range(1, 7):
        X = pd.concat(stage_frames[k], axis=0, ignore_index=True)
        y = pd.concat(stage_targets[k], axis=0, ignore_index=True)
        groups = np.concatenate(stage_groups[k])
        out[k] = {"X": X, "y": y, "groups": groups, "feature_cols": list(X.columns)}
    return out


def train_and_eval(stage: int, data: dict) -> tuple[HistGradientBoostingRegressor, dict]:
    X, y, groups = data["X"], data["y"], data["groups"]
    gkf = GroupKFold(n_splits=5)
    fold_mae = []
    fold_within_spec_acc = []  # 預測值與真值是否落在同一側規格內/外的一致率（實務意義）
    for train_idx, valid_idx in gkf.split(X, y, groups):
        model = HistGradientBoostingRegressor(
            max_depth=6, learning_rate=0.08, max_iter=300, l2_regularization=1.0, random_state=0
        )
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        pred = model.predict(X.iloc[valid_idx])
        mae = mean_absolute_error(y.iloc[valid_idx], pred)
        fold_mae.append(mae)
        true_oos = (y.iloc[valid_idx] > SENSOR_HI_LIMIT_C).to_numpy()
        pred_oos = pred > SENSOR_HI_LIMIT_C
        fold_within_spec_acc.append((true_oos == pred_oos).mean())

    # 最終模型：用全部資料重新訓練，部署用這個
    final_model = HistGradientBoostingRegressor(
        max_depth=6, learning_rate=0.08, max_iter=300, l2_regularization=1.0, random_state=0
    )
    final_model.fit(X, y)

    metrics = {
        "stage": stage,
        "n_samples": len(X),
        "n_features": X.shape[1],
        "cv_mae_mean": float(np.mean(fold_mae)),
        "cv_mae_std": float(np.std(fold_mae)),
        "cv_oos_flag_acc_mean": float(np.mean(fold_within_spec_acc)),
    }
    return final_model, metrics


def main():
    wafers = load_all_wafers()
    print(f"loaded {len(wafers)} wafers")

    datasets = build_stage_datasets(wafers)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    all_metrics = []
    for k in range(1, 7):
        data = datasets[k]
        print(f"\n--- stage sensor{k}: n_samples={len(data['X'])}, n_features={data['X'].shape[1]} ---")
        model, metrics = train_and_eval(k, data)
        print(
            f"  CV MAE = {metrics['cv_mae_mean']:.4f} +/- {metrics['cv_mae_std']:.4f} (degC)  "
            f"| OOS-flag agreement = {metrics['cv_oos_flag_acc_mean']*100:.1f}%"
        )
        joblib.dump(
            {"model": model, "feature_cols": data["feature_cols"], "meta_cols": EXTRA_META_FEATURES},
            MODELS_DIR / f"sensor{k}_model.joblib",
        )
        all_metrics.append(metrics)

    metrics_df = pd.DataFrame(all_metrics)
    metrics_df.to_csv(REPORTS_DIR / "sensor_model_metrics.csv", index=False)
    print("\n" + metrics_df.to_string(index=False))
    print(f"\nsaved models to {MODELS_DIR}, metrics to {REPORTS_DIR / 'sensor_model_metrics.csv'}")


if __name__ == "__main__":
    main()
