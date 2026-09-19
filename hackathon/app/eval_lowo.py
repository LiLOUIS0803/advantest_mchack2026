"""
留一片 wafer 交叉驗證（Leave-One-Wafer-Out）— 場景一三層式診斷。

每一折：把 1 片 wafer 完全拿掉，
  * die 層級的正常基準（median/scale）只用「其餘 Normal wafer」重建
  * wafer 統計偵測器的關鍵測項 / baseline / 方向，只用「其餘 wafer」重新選出
    （被拿掉的若是某異常類型的唯一範例，那個類型就完全沒有範例可學）
再判斷被拿掉的那片，才是真正沒看過的資料上的成績。

⚠️ 仍然沒有涵蓋的部分：K_EXC / Z_OUT / MIN_EXC_DICE 等門檻是人工設定、
看過全部 25 片才定的，交叉驗證沒有辦法把這部分「還原成沒看過」。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from anomaly_detector import AnomalyDetector  # noqa: E402
from data_loader import WAFER_STATUS, load_all_wafers  # noqa: E402
from eval_hierarchical import TRUE_TO_CAUSE, run_wafer  # noqa: E402
from hierarchical import DieBaseline, HierarchicalAnalyzer  # noqa: E402

CATEGORIES = {
    "site_unbalance": ("site_unbalance", [1]),
    "low_yield": ("oos_rate", [3, 9]),
    "mean_trend_up": ("mean_trend", [14]),
    "mean_trend_down": ("mean_trend", [18]),
    "stdev_trend_up": ("stdev_trend", [23]),
    "stdev_trend_down": ("stdev_trend", [25]),
}
TOP_N = 30
Z_THRESHOLD = 3.0


def build_stats_config(all_stats, wafers, exclude: int) -> dict:
    """跟 src/eda_scan.py 同樣的流程，但排除 exclude 那片（同時從 Normal 基準與異常範例移除）。"""
    normal_ids = [w for w, s in WAFER_STATUS.items() if s == "Normal" and w != exclude]
    w0 = wafers[0]
    lo_map = {w0.canonical_map[c]: w0.lo_limit.get(c) for c in w0.test_cols}
    hi_map = {w0.canonical_map[c]: w0.hi_limit.get(c) for c in w0.test_cols}
    label_map = {v: k for k, v in w0.canonical_map.items()}

    cfg = {"z_threshold": Z_THRESHOLD, "top_n": TOP_N, "categories": {}}
    for cat, (metric, examples) in CATEGORIES.items():
        examples = [e for e in examples if e != exclude]
        if not examples:
            continue
        mat = pd.concat({w: all_stats.loc[w][metric] for w in normal_ids}, axis=1)
        mu, sigma = mat.mean(axis=1), mat.std(axis=1).replace(0, np.nan)
        z_by = {e: (all_stats.loc[e][metric] - mu) / sigma for e in examples}
        max_abs = pd.concat(z_by, axis=1).abs().max(axis=1)
        entries = []
        for col in max_abs.sort_values(ascending=False).head(TOP_N).index:
            zvals = {e: z_by[e][col] for e in examples}
            best = max(zvals, key=lambda e: abs(zvals[e]))
            lo, hi = lo_map.get(col), hi_map.get(col)
            entries.append(
                {
                    "key": col,
                    "label": label_map.get(col, col),
                    "mu": None if pd.isna(mu[col]) else float(mu[col]),
                    "sigma": None if pd.isna(sigma[col]) else float(sigma[col]),
                    "direction": 1 if zvals[best] > 0 else -1,
                    "lo_limit": None if lo is None or pd.isna(lo) else float(lo),
                    "hi_limit": None if hi is None or pd.isna(hi) else float(hi),
                }
            )
        cfg["categories"][cat] = {"metric": metric, "example_wafers": examples, "columns": entries}
    return cfg


def build_die_baseline(wafers, exclude: int) -> DieBaseline:
    cols = wafers[0].test_cols
    keys = [wafers[0].canonical_map[c] for c in cols]
    pool = np.vstack(
        [w.df[cols].to_numpy(float) for w in wafers if WAFER_STATUS[w.wafer_id] == "Normal" and w.wafer_id != exclude]
    )
    med = np.nanmedian(pool, axis=0)
    mad = np.nanmedian(np.abs(pool - med), axis=0) * 1.4826
    std = np.nanstd(pool, axis=0)
    scale = np.where(mad > 1e-9, mad, std)
    scale = np.where(scale > 1e-9, scale, np.nan)
    return DieBaseline.from_arrays(keys, med, scale)


def main():
    wafers = load_all_wafers()
    all_stats = pd.read_pickle(ROOT / "reports" / "wafer_col_stats.pkl")

    rows = []
    print(f"{'held-out':9s} {'true':17s} {'stage1':9s} {'stage2 cause':18s} 結果")
    for wd in wafers:
        h = wd.wafer_id
        cfg = build_stats_config(all_stats, wafers, exclude=h)
        detector = AnomalyDetector(config=cfg)
        analyzer = HierarchicalAnalyzer(build_die_baseline(wafers, exclude=h))
        diag = run_wafer(wd, detector, analyzer)

        true_cause = TRUE_TO_CAUSE[wd.status]
        s1_ok = diag.abnormal == (true_cause is not None)
        s2_ok = diag.cause == true_cause
        only_example = true_cause in CATEGORIES and CATEGORIES[true_cause][1] == [h]
        rows.append(
            dict(wafer=h, true=wd.status, abnormal=diag.abnormal, cause=diag.cause, s1_ok=s1_ok, s2_ok=s2_ok,
                 only_example=only_example, n_exc=diag.n_excursion,
                 pids=[d["pid"] for d in diag.affected_dice] if diag.die_localizable else None)
        )
        note = "（該類型唯一範例被拿掉）" if only_example else ""
        print(f"W{h:02d}      {wd.status:17s} {'ABNORMAL' if diag.abnormal else 'normal  ':9s} "
              f"{(diag.cause or '-'):18s} {'OK ' if s2_ok else 'BAD'} {note}", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "reports" / "lowo_results.csv", index=False)
    n = len(df)
    normal = df[df.true == "Normal"]
    abn = df[df.true != "Normal"]
    print(f"\n=== 留一片交叉驗證（{n} 折）===")
    print(f"第 1 層 二元判斷：{int(df.s1_ok.sum())}/{n}")
    print(f"  Normal wafer 誤報：{int((normal.abnormal).sum())}/{len(normal)}")
    print(f"  異常 wafer 漏報：{int((~abn.abnormal).sum())}/{len(abn)}")
    print(f"第 2 層 原因分類：{int(df.s2_ok.sum())}/{n}")
    print(f"  異常 wafer 原因正確：{int(abn.s2_ok.sum())}/{len(abn)}")
    print(f"  其中「該類型還有其他範例」：{int(abn[~abn.only_example].s2_ok.sum())}/{int((~abn.only_example).sum())}"
          f"；「唯一範例被拿掉」：{int(abn[abn.only_example].s2_ok.sum())}/{int(abn.only_example.sum())}")


if __name__ == "__main__":
    main()
