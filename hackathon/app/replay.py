"""
待辦 6（本機驗證那一段）：不用進 Gemini VM，也不用真的 STDF 二進位解析，
直接把 25 片 wafer 的 RawResult.csv（跟 STDF 數值完全一致，md 4.1 節）
攤開成「一顆一顆 device 依序測試」的事件序列，餵進 SampleMonitor，
驗證 consumeData() 的異常偵測、consumeTPRequest() 的溫度預測邏輯有沒有跑對。

事件順序（單一 device、單一 site）：
  TESTSTART
    -> Suite1..14, IDDQ_flow 各測項 MEASURED_* 事件
    -> [receive_temp_predict1] consumeTPRequest({"key":"predict","data":1})
    -> sensor1 MEASURED 事件（真實量到的溫度值，之後階段可以用）
    -> subflow1 各測項 MEASURED_* 事件
    -> [receive_temp_predict2] ...
    ... 一路到 sensor6 / subflow6
  TESTEND

⚠️ 這是單執行緒、依序處理每一顆 device 的簡化模擬，跟真正機台「4 個 site
同步平行跑」不完全一樣（見程式內註解），但用來驗證 consumeData/
consumeTPRequest 的邏輯正確性、以及在完整 25 片 wafer 上跑過一次因果安全的
線上預測 MAE，已經足夠。
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import WAFER_STATUS, find_sensor_col, load_all_wafers  # noqa: E402
from oneapi_mock import ActionManager, DataType, NexusData, TestCell  # noqa: E402
from sample import SampleMonitor  # noqa: E402

RESPONSE_RE = re.compile(r"(\d+),([\-\d.]+)")


def parse_predict_response(response: str, site: int) -> float | None:
    for s, v in RESPONSE_RE.findall(response):
        if int(s) == site:
            return float(v)
    return None


def replay_wafer(monitor: SampleMonitor, wd) -> dict:
    cols = wd.test_cols
    sensor_positions = {k: cols.index(find_sensor_col(wd, k)) for k in range(1, 7)}
    tester = TestCell(testerId="SIM_TESTER_1", lot="A12345", wafer=wd.wafer_id)

    monitor.consumeData(
        tester,
        NexusData(DataType.PRODUCTION_WAFERSTART, extra={"wafer": wd.wafer_id, "lot": "A12345"}),
    )

    pred_records = []
    for _, row in wd.df.iterrows():
        site = int(row["Site"])
        x, y = row.get("X"), row.get("Y")
        monitor.consumeData(tester, NexusData(DataType.PRODUCTION_TESTSTART, site=site, x=x, y=y))

        for i, col in enumerate(cols):
            for k, pos in sensor_positions.items():
                if i == pos:
                    request = json.dumps({"key": "predict", "data": k})
                    response = monitor.consumeTPRequest(tester, request)
                    pred_val = parse_predict_response(response, site)
                    pred_records.append(
                        {
                            "wafer": wd.wafer_id,
                            "stage": k,
                            "site": site,
                            "true": float(row[col]) if pd.notna(row[col]) else None,
                            "pred": pred_val,
                        }
                    )
            val = row[col]
            if pd.notna(val):
                monitor.consumeData(
                    tester,
                    NexusData(
                        DataType.MEASURED_PARAMETRIC,
                        test_num=wd.test_num[col],
                        pin=wd.pin[col],
                        value=float(val),
                        site=site,
                    ),
                )

        monitor.consumeData(
            tester,
            NexusData(
                DataType.PRODUCTION_TESTEND,
                site=site,
                x=x,
                y=y,
                sbin=int(row["SBin"]) if pd.notna(row.get("SBin")) else None,
                hbin=int(row["HBin"]) if pd.notna(row.get("HBin")) else None,
                test_time=row.get("Test Time"),
                extra={"pf": row.get("PF")},
            ),
        )

    n_msgs_before_end = len(ActionManager.sent_messages)
    monitor.consumeData(tester, NexusData(DataType.PRODUCTION_WAFEREND, extra={"wafer": wd.wafer_id}))
    final_alerted = len(ActionManager.sent_messages) > n_msgs_before_end
    return {"pred_records": pred_records, "final_alerted": final_alerted}


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 片 wafer（debug 用）")
    parser.add_argument("--range", type=str, default=None, help="只跑指定 wafer 範圍，例如 7-13（可平行開多個程序）")
    parser.add_argument("--tag", type=str, default="", help="輸出檔名後綴，平行執行時避免互相覆蓋")
    args = parser.parse_args()

    wafers = load_all_wafers()
    if args.limit:
        wafers = wafers[: args.limit]
    if args.range:
        lo, hi = (int(v) for v in args.range.split("-"))
        wafers = [w for w in wafers if lo <= w.wafer_id <= hi]
    monitor = SampleMonitor()

    all_preds = []
    detected_categories = {}
    for wd in wafers:
        ActionManager.sent_messages.clear()
        result = replay_wafer(monitor, wd)
        all_preds.extend(result["pred_records"])
        detected_categories[wd.wafer_id] = {
            "true_status": wd.status,
            "any_alerted": len(ActionManager.sent_messages) > 0,
            "final_alerted": result["final_alerted"],
        }
        print(
            f"wafer {wd.wafer_id:2d} [{wd.status:16s}] -> "
            f"final_alerted={result['final_alerted']} (any_alerted={detected_categories[wd.wafer_id]['any_alerted']})"
        )

    pred_df = pd.DataFrame(all_preds).dropna(subset=["true", "pred"])
    pred_df["abs_err"] = (pred_df["true"] - pred_df["pred"]).abs()
    print("\n=== 場景二：線上（causally-safe）預測誤差，依 stage ===")
    print(pred_df.groupby("stage")["abs_err"].agg(["mean", "max", "count"]))

    out_path = ROOT / "reports" / f"replay_predictions{args.tag}.csv"
    pred_df.to_csv(out_path, index=False)
    print(f"\nsaved {out_path}")

    print("\n=== 場景一：異常偵測 vs. 已知 ground truth ===")
    print("（final_alerted 是 WAFEREND 當下的最終結論；any_alerted 連同測到一半的早期預警也算，僅供參考）")
    correct_final, correct_any = 0, 0
    for wid, info in detected_categories.items():
        expect_alert = info["true_status"] != "Normal"
        ok_final = expect_alert == info["final_alerted"]
        ok_any = expect_alert == info["any_alerted"]
        correct_final += ok_final
        correct_any += ok_any
        print(
            f"  W{wid:02d}: status={info['true_status']:16s} "
            f"final={'OK ' if ok_final else 'MISS'} (any={'OK' if ok_any else 'miss'})"
        )
    print(f"\n最終判斷：{correct_final}/{len(detected_categories)} 正確")
    print(f"含早期預警在內：{correct_any}/{len(detected_categories)} 正確")


if __name__ == "__main__":
    main()
