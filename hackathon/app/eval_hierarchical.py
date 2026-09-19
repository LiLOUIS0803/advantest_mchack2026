"""
離線評估三層式診斷（不走 OneAPI 事件模擬，直接逐顆餵進 HierarchicalAnalyzer +
WaferBuffer/AnomalyDetector，計算方式跟 runtime 完全一樣，速度快很多）。

輸出：
  - 每片 wafer：真實狀態 vs. 第 1 層（是否 abnormal）vs. 第 2 層（細分原因）+ 定位到的 die
  - 第 1 層二元判斷正確率、第 2 層原因正確率
  - 19 片 Normal wafer 上有沒有任何 EXCURSION die 被誤判（die 層級誤報）
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from anomaly_detector import AnomalyDetector, WaferBuffer  # noqa: E402
from data_loader import load_all_wafers  # noqa: E402
from hierarchical import CAUSE_LABELS, HierarchicalAnalyzer  # noqa: E402

TRUE_TO_CAUSE = {
    "Site unbalance": "site_unbalance",
    "Low yield": "low_yield",
    "Mean Trend Up": "mean_trend_up",
    "Mean Trend Down": "mean_trend_down",
    "Stdev Trend Up": "stdev_trend_up",
    "Stdev Trend Down": "stdev_trend_down",
    "Normal": None,
}


def run_wafer(wd, detector, analyzer):
    analyzer.reset()
    buf = WaferBuffer()
    cmap = wd.canonical_map
    cols = wd.test_cols
    df = wd.df
    for idx in range(len(df)):
        row = df.iloc[idx]
        values = {cmap[c]: row[c] for c in cols if pd.notna(row[c])}
        meta = {
            "pid": idx + 1,
            "site": int(row["Site"]),
            "x": row["X"],
            "y": row["Y"],
            "sbin": int(row["SBin"]) if pd.notna(row["SBin"]) else None,
        }
        buf.add_device_result(meta, values)
        analyzer.add_die(meta, values)
    return analyzer.analyze(detector.evaluate(buf))


def main():
    wafers = load_all_wafers()
    detector = AnomalyDetector()
    analyzer = HierarchicalAnalyzer()

    ok1 = ok2 = 0
    normal_exc_dice = 0
    print(f"{'wafer':6s} {'true':17s} {'stage1':9s} {'stage2 cause':34s} {'localized dice (PID)'}")
    for wd in wafers:
        diag = run_wafer(wd, detector, analyzer)
        true_cause = TRUE_TO_CAUSE[wd.status]
        s1_ok = diag.abnormal == (true_cause is not None)
        s2_ok = diag.cause == true_cause
        ok1 += s1_ok
        ok2 += s2_ok
        if true_cause is None:
            normal_exc_dice += diag.n_excursion
        pids = [d["pid"] for d in diag.affected_dice]
        if len(pids) > 14:
            shown = f"{pids[:6]}...{pids[-3:]} ({len(pids)} dice)"
        else:
            shown = str(pids) if diag.die_localizable else "（無法定位到單顆 die）"
        site = f" site={diag.site}" if diag.site else ""
        print(
            f"W{wd.wafer_id:02d}    {wd.status:17s} {'ABNORMAL' if diag.abnormal else 'normal  ':9s} "
            f"{(diag.cause or '-'):22s}{'OK ' if s2_ok else 'BAD'}{site:9s} {shown}"
        )
    n = len(wafers)
    print(f"\n第 1 層（二元 abnormal/normal）：{ok1}/{n}")
    print(f"第 2 層（原因分類，含 Normal）：{ok2}/{n}")
    print(f"Normal wafer 上被誤判為 EXCURSION 的 die 總數：{normal_exc_dice}")


if __name__ == "__main__":
    main()
