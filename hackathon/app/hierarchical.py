"""
三層式異常診斷：

  第 1 層 二元判斷（是否 abnormal）
      die 層級：一顆 die 有 >= K_EXC 個測項的 robust z-score 超過 Z_OUT（且不是整片 wafer
                 的系統性偏移欄位）→ EXCURSION die。一般 bin-fail（約 5 個測項爆掉）視為背景
                 良率損失 FAIL，不算 abnormal。
      wafer 層級：EXCURSION die >= MIN_EXC_DICE 顆，或 wafer 統計偵測器（AnomalyDetector）
                 對「沒有離群 die 的異常類型」（low_yield / stdev_trend_down）達 critical。
  第 2 層 細分原因
      有離群 die：
        * 離群 die 集中在單一 site（>= 80%）            → Site unbalance
        * 跨 site、離群方向 >= 90% 為正 / 負              → Mean Trend Up / Down
        * 跨 site、正負混雜（變異數放大、平均值沒有位移）  → Stdev Trend Up
      沒有離群 die：交給 wafer 統計偵測器（low_yield / stdev_trend_down）。
  第 3 層 die 定位
      回報造成該異常的具體 die（PID、site、X/Y、離群測項數、主要離群測項）與時間窗。
      ⚠️ 例外：stdev_trend_down 在資料裡沒有任何離群 die（是變異數縮小），無法定位到單顆 die，
      報告會明確標示 die_localizable=False，而不是硬編出一份 die 清單。

全部只用「已經測完的 die」的資料，可以在每顆 die 的 TESTEND 即時更新（因果安全）。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "reports" / "die_baseline.json"

Z_OUT = 5.0  # robust z-score 超過這個值就算該測項離群
K_EXC = 10  # 一顆 die 至少幾個（非系統性）離群測項才算 EXCURSION
MIN_EXC_DICE = 3  # wafer 至少要有幾顆 EXCURSION die 才判定 abnormal
WAFER_WIDE_FRAC = 0.5  # 測項在這個比例以上的 die 都離群 → 視為整片 wafer 的系統性偏移
MIN_DICE_FOR_WAFER_WIDE = 6
SITE_CONC = 0.8
DIR_COHERENT = 0.9

CAUSE_LABELS = {
    "site_unbalance": "Site 不平衡 (Site Unbalance)",
    "low_yield": "低良率 (Low Yield)",
    "mean_trend_up": "均值上升趨勢 (Mean Trend Up)",
    "mean_trend_down": "均值下降趨勢 (Mean Trend Down)",
    "stdev_trend_up": "變異數上升趨勢 (Stdev Trend Up)",
    "stdev_trend_down": "變異數下降趨勢 (Stdev Trend Down)",
}
STATS_ONLY_CAUSES = ("low_yield", "stdev_trend_down")  # 沒有離群 die，只能靠 wafer 統計偵測


class DieBaseline:
    def __init__(self, path: Path = BASELINE_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.keys: list[str] = raw["keys"]
        self.index = {k: i for i, k in enumerate(self.keys)}
        nan = float("nan")
        self.median = np.array([nan if v is None else v for v in raw["median"]], dtype=float)
        self.scale = np.array([nan if v is None else v for v in raw["scale"]], dtype=float)
        self.usable = np.isfinite(self.scale)

    @classmethod
    def from_arrays(cls, keys: list[str], median: np.ndarray, scale: np.ndarray) -> "DieBaseline":
        self = cls.__new__(cls)
        self.keys = keys
        self.index = {k: i for i, k in enumerate(keys)}
        self.median = median
        self.scale = scale
        self.usable = np.isfinite(scale)
        return self

    def vectorize(self, values: dict[str, float]) -> np.ndarray:
        vec = np.full(len(self.keys), np.nan)
        for k, v in values.items():
            j = self.index.get(k)
            if j is not None and v is not None:
                vec[j] = v
        return vec


@dataclass
class DieRecord:
    pid: int
    site: int | None
    x: float | None
    y: float | None
    sbin: int | None
    k_raw: int
    k: int = 0
    status: str = "PASS"  # PASS | FAIL | EXCURSION
    top_cols: list = field(default_factory=list)  # [(key, z)]


@dataclass
class WaferDiagnosis:
    abnormal: bool
    cause: str | None
    cause_label: str | None
    n_dice: int
    n_excursion: int
    die_localizable: bool
    affected_dice: list[dict]
    window: tuple[int, int] | None
    site: int | None
    evidence: list[str]
    dice: list[DieRecord]


class HierarchicalAnalyzer:
    def __init__(self, baseline: DieBaseline | None = None):
        self.baseline = baseline or DieBaseline()
        self.reset()

    def reset(self) -> None:
        self._records: list[DieRecord] = []
        self._out: list[np.ndarray] = []  # bool[n_cols] 每顆 die 的離群遮罩
        self._sign: list[np.ndarray] = []  # int8[n_cols] +1/-1/0
        self._z: list[np.ndarray] = []

    def _wafer_wide_mask(self) -> np.ndarray:
        n = len(self._out)
        if n < MIN_DICE_FOR_WAFER_WIDE:
            return np.zeros(len(self.baseline.keys), dtype=bool)
        return np.mean(np.array(self._out), axis=0) >= WAFER_WIDE_FRAC

    def add_die(self, meta: dict, values: dict[str, float]) -> DieRecord:
        b = self.baseline
        vec = b.vectorize(values)
        with np.errstate(invalid="ignore", divide="ignore"):
            z = (vec - b.median) / b.scale
        out = np.isfinite(z) & (np.abs(z) > Z_OUT) & b.usable
        rec = DieRecord(
            pid=int(meta.get("pid") or len(self._records) + 1),
            site=meta.get("site"),
            x=meta.get("x"),
            y=meta.get("y"),
            sbin=meta.get("sbin"),
            k_raw=int(out.sum()),
        )
        self._records.append(rec)
        self._out.append(out)
        self._sign.append(np.where(out, np.sign(np.nan_to_num(z)), 0).astype(np.int8))
        self._z.append(np.nan_to_num(z, nan=0.0).astype(np.float32))
        self._finalize_status()
        return self._records[-1]

    def _finalize_status(self) -> None:
        wide = self._wafer_wide_mask()
        keys = self.baseline.keys
        for rec, out, z in zip(self._records, self._out, self._z):
            adj = out & ~wide
            rec.k = int(adj.sum())
            if rec.k >= K_EXC:
                rec.status = "EXCURSION"
                idx = np.where(adj)[0]
                top = idx[np.argsort(-np.abs(z[idx]))[:5]]
                rec.top_cols = [(keys[j], float(z[j])) for j in top]
            elif rec.sbin is not None and rec.sbin != 1:
                rec.status = "FAIL"
                rec.top_cols = []
            else:
                rec.status = "PASS"
                rec.top_cols = []

    @property
    def records(self) -> list[DieRecord]:
        return self._records

    def analyze(self, stats_findings: list[dict] | None = None) -> WaferDiagnosis:
        """stats_findings: AnomalyDetector.evaluate() 的輸出（wafer 層統計偵測結果）。"""
        stats_findings = stats_findings or []
        recs = self._records
        exc = [r for r in recs if r.status == "EXCURSION"]
        evidence: list[str] = []

        def dies(sel: list[DieRecord]) -> list[dict]:
            return [
                {
                    "pid": r.pid,
                    "site": r.site,
                    "x": r.x,
                    "y": r.y,
                    "sbin": r.sbin,
                    "k": r.k,
                    "status": r.status,
                    "top_cols": r.top_cols,
                }
                for r in sel
            ]

        if len(exc) >= MIN_EXC_DICE:
            wide = self._wafer_wide_mask()
            sites = Counter(r.site for r in exc)
            top_site, top_n = sites.most_common(1)[0]
            pos = neg = 0
            for r, sign in zip(recs, self._sign):
                if r.status == "EXCURSION":
                    s = sign[~wide]
                    pos += int((s > 0).sum())
                    neg += int((s < 0).sum())
            pos_frac = pos / max(pos + neg, 1)
            pids = [r.pid for r in exc]

            if top_n / len(exc) >= SITE_CONC:
                cause = "site_unbalance"
                affected = [r for r in exc if r.site == top_site]
                evidence.append(
                    f"{len(affected)}/{len(exc)} 顆離群 die 集中在 site {top_site}，其他 site 同期間正常"
                )
                site = top_site
            else:
                site = None
                affected = exc
                if pos_frac >= DIR_COHERENT:
                    cause = "mean_trend_up"
                elif pos_frac <= 1 - DIR_COHERENT:
                    cause = "mean_trend_down"
                else:
                    cause = "stdev_trend_up"
                evidence.append(
                    f"{len(exc)} 顆離群 die 橫跨 {len(sites)} 個 site，PID {min(pids)}~{max(pids)}，"
                    f"離群方向為正的比例 {pos_frac*100:.0f}%"
                )
                ks = [r.k for r in sorted(exc, key=lambda r: r.pid)]
                evidence.append(f"離群測項數隨測試順序 {ks[0]} → {ks[-1]}（最大 {max(ks)}）")

            return WaferDiagnosis(
                abnormal=True,
                cause=cause,
                cause_label=CAUSE_LABELS[cause],
                n_dice=len(recs),
                n_excursion=len(exc),
                die_localizable=True,
                affected_dice=dies(sorted(affected, key=lambda r: r.pid)),
                window=(min(r.pid for r in affected), max(r.pid for r in affected)),
                site=site,
                evidence=evidence,
                dice=recs,
            )

        stats_cands = [
            f for f in stats_findings if f["category"] in STATS_ONLY_CAUSES and f["severity"] == "critical"
        ]
        if stats_cands:
            best = max(stats_cands, key=lambda f: f["score"])
            cause = best["category"]
            top = best["triggered_columns"][0] if best["triggered_columns"] else None
            evidence.append(f"wafer 統計偵測：{best['score']*100:.0f}% 關鍵測項超標")
            if top:
                evidence.append(f"主要測項 {top['label']} (z={top['z']:+.1f})")
            if cause == "low_yield":
                fails = [r for r in recs if r.status in ("FAIL", "EXCURSION")]
                evidence.append(f"bin fail die {len(fails)}/{len(recs)}，良率 {(1-len(fails)/max(len(recs),1))*100:.1f}%")
                return WaferDiagnosis(
                    True, cause, CAUSE_LABELS[cause], len(recs), len(exc), True,
                    dies(fails), None, None, evidence, recs,
                )
            evidence.append("此異常類型為變異數縮小，沒有任何單顆離群 die，無法定位到單顆 die")
            return WaferDiagnosis(
                True, cause, CAUSE_LABELS[cause], len(recs), len(exc), False, [], None, None, evidence, recs
            )

        return WaferDiagnosis(False, None, None, len(recs), len(exc), True, [], None, None, evidence, recs)
