"""
Wafer 級異常偵測器（場景一）。

用 src/eda_scan.py 離線掃描 25 片訓練 wafer 產生的
reports/anomaly_detector_config.json（每個異常類別的關鍵測項 + Normal 基準
mu/sigma/方向/規格上下限），在 runtime 用「同一套統計量定義」在目前這片 wafer
已經收到的資料上重新計算，跟訓練時的基準比對 z-score。

四個統計量的定義跟 src/eda_scan.py 的 compute_wafer_col_stats() 完全一致：
  site_unbalance : 4 個 site 平均值的離散度 / 整片 overall std
  mean_trend     : 數值 vs. PID（測試順序）的 Pearson 相關係數
  stdev_trend    : log( std(最後 1/3 筆) / std(最前 1/3 筆) )
  oos_rate       : 超出真實規格上下限的比例

因為量測是即時累積的，這些統計量在「wafer 測到一半」時就可以先算一次
（給早期預警），在 WAFEREND 時再算一次最終版本（用於送出正式異常報告）。
這完全符合因果限制：只用「已經發生」的資料，沒有用到未來。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "reports" / "anomaly_detector_config.json"

MIN_SAMPLES = 8  # 至少要有這麼多顆 device 的資料才開始算統計量，避免早期雜訊
MIN_SITE_SAMPLES = 10  # site_unbalance 專用：每個 site 至少要有這麼多顆，樣本太少時 site 平均值本身雜訊就很大


class WaferBuffer:
    """單片 wafer 從 WAFERSTART 到 WAFEREND 累積的原始資料。"""

    def __init__(self):
        self.devices: list[dict] = []  # 已完成的 device：{pid,site,x,y,pf,sbin,hbin,test_time}
        self.col_history: dict[str, list[float]] = defaultdict(list)  # key -> 依 device 順序的值
        self.site_col_history: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    def add_device_result(self, meta: dict, values: dict[str, float]) -> None:
        self.devices.append(meta)
        site = meta.get("site")
        for k, v in values.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            self.col_history[k].append(v)
            if site is not None:
                self.site_col_history[site][k].append(v)

    @property
    def n_devices(self) -> int:
        return len(self.devices)

    @property
    def yield_rate(self) -> float:
        if not self.devices:
            return 1.0
        good = sum(1 for d in self.devices if d.get("sbin") == 1)
        return good / len(self.devices)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def compute_column_stat(metric: str, key: str, buf: WaferBuffer, lo=None, hi=None) -> float | None:
    hist = buf.col_history.get(key)
    if not hist or len(hist) < MIN_SAMPLES:
        return None

    if metric == "oos_rate":
        if lo is None or hi is None:
            return None
        return sum(1 for v in hist if v < lo or v > hi) / len(hist)

    if metric == "site_unbalance":
        site_means = [
            _mean(vals[key])
            for vals in buf.site_col_history.values()
            if key in vals and len(vals[key]) >= MIN_SITE_SAMPLES
        ]
        if len(site_means) < 2:
            return None
        overall_std = _std(hist)
        if not overall_std:
            return None
        return _std(site_means) / overall_std

    if metric == "mean_trend":
        pid = list(range(len(hist)))  # 依收到順序 = 測試時間序
        n = len(hist)
        mx, my = _mean(pid), _mean(hist)
        sx = math.sqrt(sum((x - mx) ** 2 for x in pid))
        sy = math.sqrt(sum((y - my) ** 2 for y in hist))
        if not sx or not sy:
            return None
        cov = sum((x - mx) * (y - my) for x, y in zip(pid, hist))
        return cov / (sx * sy)

    if metric == "stdev_trend":
        n = len(hist)
        third = n // 3
        if third < 3:
            return None
        std_first = _std(hist[:third])
        std_last = _std(hist[-third:])
        return math.log((std_last + 1e-9) / (std_first + 1e-9))

    return None


class AnomalyDetector:
    def __init__(self, config_path: Path = CONFIG_PATH, config: dict | None = None):
        if config is not None:
            self.config = config
        else:
            with open(config_path, encoding="utf-8") as f:
                self.config = json.load(f)
        self.z_threshold = self.config.get("z_threshold", 3.0)

    def evaluate(self, buf: WaferBuffer) -> list[dict]:
        """回傳觸發的異常類別列表：
        [{"category","metric","score","severity","triggered_columns":[...]}]"""
        findings = []
        for cat_name, cat_cfg in self.config["categories"].items():
            metric = cat_cfg["metric"]
            triggered = []
            for col in cat_cfg["columns"]:
                raw = compute_column_stat(metric, col["key"], buf, col.get("lo_limit"), col.get("hi_limit"))
                if raw is None or col["mu"] is None or not col["sigma"]:
                    continue
                z = (raw - col["mu"]) / col["sigma"]
                same_direction = (z > 0) == (col["direction"] > 0)
                if abs(z) >= self.z_threshold and same_direction:
                    triggered.append(
                        {
                            "key": col["key"],
                            "label": col["label"],
                            "z": z,
                            "current": raw,
                            "baseline_mu": col["mu"],
                            "baseline_sigma": col["sigma"],
                        }
                    )
            total = len(cat_cfg["columns"])
            score = len(triggered) / total if total else 0.0
            if score >= 0.15:
                triggered.sort(key=lambda c: abs(c["z"]), reverse=True)
                severity = "critical" if score >= 0.4 else "warning"
                findings.append(
                    {
                        "category": cat_name,
                        "metric": metric,
                        "score": score,
                        "severity": severity,
                        "triggered_columns": triggered,
                    }
                )
        findings.sort(key=lambda f: f["score"], reverse=True)
        return findings

    def trend_series_for(self, category: str, buf: WaferBuffer) -> dict | None:
        """給報告畫趨勢線用：該類別 z 最高的欄位，回傳 (pid, values)。"""
        cat_cfg = self.config["categories"].get(category)
        if not cat_cfg:
            return None
        best_col, best_z = None, -1.0
        for col in cat_cfg["columns"]:
            raw = compute_column_stat(cat_cfg["metric"], col["key"], buf, col.get("lo_limit"), col.get("hi_limit"))
            if raw is None or col["mu"] is None or not col["sigma"]:
                continue
            z = abs((raw - col["mu"]) / col["sigma"])
            if z > best_z:
                best_z, best_col = z, col
        if best_col is None:
            return None
        hist = buf.col_history.get(best_col["key"], [])
        return {"label": best_col["label"], "pid": list(range(len(hist))), "values": hist}
