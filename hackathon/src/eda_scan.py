"""
待辦 1：系統性掃描全部 25 片 wafer 的 ~3000 個測項欄位，
找出「Site unbalance / Low yield / Mean Trend Up-Down / Stdev Trend Up-Down」
這幾種 wafer 級異常各自對應到哪些欄位的統計特徵。

對每一片 wafer、每一個測項欄位，計算四個統計量（皆已用 overall std 正規化，
所以可以跨欄位、跨 wafer 比較大小）：

  site_unbalance : 4 個 site 平均值的離散程度 / 整片 overall std
  mean_trend     : 數值 vs. PID（測試時間序）的 Pearson 相關係數，
                    捕捉「整片測到後面數值系統性往上/下飄」
  stdev_trend    : 後 1/3 筆 std 除以 前 1/3 筆 std（log ratio），
                    捕捉「測到後面變異數變大/變小」
  oos_rate       : 超出真實規格上下限（已修正表頭陷阱）的比例

再用 25 片 wafer 的分布，對每個已知異常 wafer 算出它在每個統計量上
相對其餘 24 片（或相對已知 Normal 集合）的 z-score，取 |z| 最大的欄位，
就是該異常類型最相關的測項。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from data_loader import META_COLS, WAFER_STATUS, load_all_wafers

TOP_N = 25
TOP_N_CONFIG = 30  # 匯出給 app 用的偵測欄位數（每類別）
Z_THRESHOLD = 3.0
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def compute_wafer_col_stats(wd) -> pd.DataFrame:
    """回傳 index=test_cols 的 DataFrame，欄位為四個統計量。"""
    df = wd.df
    test_cols = wd.test_cols
    X = df[test_cols].to_numpy(dtype=float)  # n_rows x n_cols
    n_rows, n_cols = X.shape

    overall_std = np.nanstd(X, axis=0)
    overall_std_safe = np.where(overall_std == 0, np.nan, overall_std)

    # --- site unbalance ---
    site = df["Site"].to_numpy()
    sites = np.unique(site[~np.isnan(site)])
    site_means = np.array([np.nanmean(X[site == s], axis=0) for s in sites])  # n_sites x n_cols
    site_unbalance = np.nanstd(site_means, axis=0) / overall_std_safe

    # --- mean trend (correlation with PID / test order) ---
    pid = df["PID"].to_numpy(dtype=float)
    pid_c = pid - np.nanmean(pid)
    pid_std = np.nanstd(pid)
    Xc = X - np.nanmean(X, axis=0)
    # covariance(col, pid) / (std_col * std_pid), ignoring NaN via nan-safe ops
    cov = np.nanmean(Xc * pid_c[:, None], axis=0)
    mean_trend = cov / (overall_std_safe * pid_std)

    # --- stdev trend (variance change over test order) ---
    order = np.argsort(pid)
    third = n_rows // 3
    first_idx = order[:third]
    last_idx = order[-third:]
    std_first = np.nanstd(X[first_idx], axis=0)
    std_last = np.nanstd(X[last_idx], axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        stdev_trend = np.log((std_last + 1e-9) / (std_first + 1e-9))

    # --- out-of-spec rate using corrected real limits ---
    lo = np.array([wd.lo_limit.get(c, np.nan) for c in test_cols])
    hi = np.array([wd.hi_limit.get(c, np.nan) for c in test_cols])
    oos = (X < lo[None, :]) | (X > hi[None, :])
    oos_rate = np.nanmean(oos.astype(float), axis=0)

    stats = pd.DataFrame(
        {
            "site_unbalance": site_unbalance,
            "mean_trend": mean_trend,
            "stdev_trend": stdev_trend,
            "oos_rate": oos_rate,
        },
        index=test_cols,
    )
    # index 改成 canonical key（"<test_num>#<pin>"），跟 runtime app 收到的事件對齊
    return stats.rename(index=wd.canonical_map)


def main():
    wafers = load_all_wafers()
    print(f"loaded {len(wafers)} wafers")

    stats_by_wafer = {}
    for wd in wafers:
        stats_by_wafer[wd.wafer_id] = compute_wafer_col_stats(wd)
        print(f"  wafer {wd.wafer_id:2d} [{wd.status:16s}] stats computed, cols={len(wd.test_cols)}")

    # 存成一張大表：MultiIndex (wafer_id, col) -> 統計量，方便之後重複使用
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    all_stats = pd.concat(stats_by_wafer, names=["wafer_id"])
    all_stats.to_pickle(REPORTS_DIR / "wafer_col_stats.pkl")
    print("saved", REPORTS_DIR / "wafer_col_stats.pkl", all_stats.shape)

    normal_ids = [w for w, s in WAFER_STATUS.items() if s == "Normal"]
    # canonical key -> 人類可讀原始欄名（給文字報告用；所有 wafer schema 相同，取第一片即可）
    label_map = {v: k for k, v in wafers[0].canonical_map.items()}
    # canonical key -> 真實規格上下限（已修正表頭陷阱），runtime 算 oos_rate 要用
    lo_limit_map = {wafers[0].canonical_map[c]: wafers[0].lo_limit.get(c) for c in wafers[0].test_cols}
    hi_limit_map = {wafers[0].canonical_map[c]: wafers[0].hi_limit.get(c) for c in wafers[0].test_cols}

    def baseline(metric: str) -> tuple[pd.Series, pd.Series]:
        mat = pd.concat({w: stats_by_wafer[w][metric] for w in normal_ids}, axis=1)
        return mat.mean(axis=1), mat.std(axis=1).replace(0, np.nan)

    # 每個類別可能有多片範例 wafer；分類器設定檔會把多片的「重要欄位」聯集起來
    categories = {
        "site_unbalance": {"metric": "site_unbalance", "example_wafers": [1]},
        "low_yield": {"metric": "oos_rate", "example_wafers": [3, 9]},
        "mean_trend_up": {"metric": "mean_trend", "example_wafers": [14]},
        "mean_trend_down": {"metric": "mean_trend", "example_wafers": [18]},
        "stdev_trend_up": {"metric": "stdev_trend", "example_wafers": [23]},
        "stdev_trend_down": {"metric": "stdev_trend", "example_wafers": [25]},
    }

    lines = []
    detector_config = {"z_threshold": Z_THRESHOLD, "top_n": TOP_N_CONFIG, "categories": {}}

    for cat_name, cfg in categories.items():
        metric = cfg["metric"]
        mu, sigma = baseline(metric)

        # 聯集：每片範例 wafer 各取 |z| 最大的 TOP_N_CONFIG 欄，再依「各欄在所有範例中的最大 |z|」排序
        z_by_example = {w: (stats_by_wafer[w][metric] - mu) / sigma for w in cfg["example_wafers"]}
        max_abs_z = pd.concat(z_by_example, axis=1).abs().max(axis=1)
        top_cols = max_abs_z.sort_values(ascending=False).head(TOP_N_CONFIG).index

        lines.append(f"\n=== {cat_name} — example wafers {cfg['example_wafers']} — metric '{metric}' ===")
        col_entries = []
        for col in top_cols:
            # 方向：取範例中 |z| 最大的那次的正負號，當作「異常時預期偏移方向」
            zvals = {w: z_by_example[w][col] for w in cfg["example_wafers"]}
            best_w = max(zvals, key=lambda w: abs(zvals[w]))
            direction = 1 if zvals[best_w] > 0 else -1
            lo = lo_limit_map.get(col)
            hi = hi_limit_map.get(col)
            col_entries.append(
                {
                    "key": col,
                    "label": label_map.get(col, col),
                    "mu": None if pd.isna(mu[col]) else float(mu[col]),
                    "sigma": None if pd.isna(sigma[col]) else float(sigma[col]),
                    "direction": direction,
                    "lo_limit": None if lo is None or pd.isna(lo) else float(lo),
                    "hi_limit": None if hi is None or pd.isna(hi) else float(hi),
                    "example_z": {int(w): float(v) for w, v in zvals.items()},
                }
            )
            lines.append(
                f"  z={zvals[best_w]:+7.2f} (wafer {best_w})  base_mu={mu[col]:+8.4f}  "
                f"base_sigma={sigma[col]:8.4f}  key={col}  label={label_map.get(col, col)}"
            )
        detector_config["categories"][cat_name] = {
            "metric": metric,
            "example_wafers": cfg["example_wafers"],
            "columns": col_entries,
        }

    report = "\n".join(lines)
    print(report)
    out_path = REPORTS_DIR / "eda_scan_top_columns.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nsaved {out_path}")

    config_path = REPORTS_DIR / "anomaly_detector_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(detector_config, f, ensure_ascii=False, indent=2)
    print(f"saved {config_path}")


if __name__ == "__main__":
    main()
