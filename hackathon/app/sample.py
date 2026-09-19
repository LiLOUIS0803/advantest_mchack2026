"""
待辦 3 + 4：ACS RTDI App 主邏輯。

- consumeData()：場景一。被動接收即時測試事件，累積 per-site / per-device buffer，
  在 WAFEREND（以及測到一半時的早期預警）呼叫 AnomalyDetector 做 wafer 級異常分類，
  異常時用 ActionManager.set_message() 通知機台，並產出可視化 HTML 報告。
- consumeTPRequest()：場景二。SmarTest 執行到 receive_temp_predictN 時主動發送
  {"key":"predict","data":N} 請求，用目前 buffer 裡「已經發生」的資料做推論，
  透過 ActionManager.set_wait() + ActionManager.get() 回傳每個 site 的預測值。

⚠️ import oneapi 這行：本機開發/測試時用 oneapi_mock，部署到 ACS Gemini 時
   要換成官方真正的 SDK import（見檔案開頭 main.py 的說明）。這個檔案本身完全
   不用改，因為兩邊的 class 介面（Interface/Monitor/ActionManager/...）刻意設計成一致。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime

from anomaly_detector import AnomalyDetector, WaferBuffer
from hierarchical import STATS_ONLY_CAUSES, HierarchicalAnalyzer
from report_generator import CategoryFinding, WaferReportContext, build_message_text, save_report
from sensor_predictor import SensorPredictor

try:
    from oneapi import ActionManager, DataType, Monitor, NexusData, TestCell  # type: ignore
except ImportError:
    from oneapi_mock import ActionManager, DataType, Monitor, NexusData, TestCell

log = logging.getLogger("acs_rtdi_app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class SampleMonitor(Monitor):
    def __init__(self):
        self.detector = AnomalyDetector()
        self.predictor = SensorPredictor()

        self.buf: WaferBuffer | None = None
        self.wafer_id: int | None = None
        self.lot: str = ""
        self.current_device: dict[int, dict[str, float]] = defaultdict(dict)
        self.current_meta: dict[int, dict] = defaultdict(dict)
        self.known_sites: set[int] = set()

        self.hier = HierarchicalAnalyzer()  # 三層式診斷：二元判斷 → 原因 → die 定位

        self._stats_check_every = 20  # 每完成 N 顆 device，對「沒有離群 die 的異常類型」做一次統計檢查
        self._prev_stats_cause: str | None = None  # 上一次統計檢查的結論，用來 debounce
        self._alerted_cause: str | None = None  # 這片 wafer 已經通報過的原因，避免重複打擾機台

    # ------------------------------------------------------------------ #
    # 場景一：consumeData
    # ------------------------------------------------------------------ #
    def consumeData(self, tc: TestCell, data: NexusData) -> None:
        dtype = data.getType()

        if dtype == DataType.PRODUCTION_WAFERSTART:
            self._on_wafer_start(tc, data)
        elif dtype == DataType.PRODUCTION_TESTSTART:
            self._on_test_start(data)
        elif dtype in (
            DataType.MEASURED_PARAMETRIC,
            DataType.MEASURED_FUNCTIONAL,
            DataType.MEASURED_MULTI_PARAM,
        ):
            self._on_measured(data)
        elif dtype == DataType.PRODUCTION_TESTEND:
            self._on_test_end(tc, data)
        elif dtype == DataType.PRODUCTION_WAFEREND:
            self._on_wafer_end(tc, data)
        # 其餘 DataType（LOTSTART/FLOWSTART/SUITESTART...）本 App 不需要處理

    def _on_wafer_start(self, tc: TestCell, data: NexusData) -> None:
        self.wafer_id = data.extra.get("wafer", getattr(tc, "wafer", None))
        self.lot = data.extra.get("lot", getattr(tc, "lot", "") or "")
        self.buf = WaferBuffer()
        self.current_device.clear()
        self.current_meta.clear()
        self.known_sites.clear()
        self.hier.reset()
        self._prev_stats_cause = None
        self._alerted_cause = None
        log.info("WAFERSTART wafer=%s lot=%s", self.wafer_id, self.lot)

    def _on_test_start(self, data: NexusData) -> None:
        site = data.site
        if site is None:
            return
        self.known_sites.add(site)
        self.current_device[site] = {}
        self.current_meta[site] = {"x": data.x, "y": data.y}

    def _on_measured(self, data: NexusData) -> None:
        site = data.site
        if site is None or data.test_num is None:
            return
        key = f"{data.test_num}#{data.pin}"
        self.current_device[site][key] = data.value

    def _on_test_end(self, tc: TestCell, data: NexusData) -> None:
        site = data.site
        if site is None or self.buf is None:
            return
        meta = {
            "site": site,
            "x": self.current_meta.get(site, {}).get("x", data.x),
            "y": self.current_meta.get(site, {}).get("y", data.y),
            "pf": data.extra.get("pf"),
            "sbin": data.sbin,
            "hbin": data.hbin,
            "test_time": data.test_time,
            "pid": self.buf.n_devices + 1,
        }
        values = self.current_device.get(site, {})
        self.buf.add_device_result(meta, values)
        rec = self.hier.add_die(meta, values)
        self.current_device[site] = {}

        # 第 1 層（die 層級二元判斷）：這顆 die 一測完就即時判斷，不用等整片 wafer
        if rec.status == "EXCURSION":
            log.warning(
                "wafer=%s die PID=%d site=%s (X=%s,Y=%s) 判定為離群 die：%d 個測項離群",
                self.wafer_id, rec.pid, rec.site, rec.x, rec.y, rec.k,
            )
            self._diagnose(tc, final=False)
        elif self.buf.n_devices % self._stats_check_every == 0:
            self._diagnose(tc, final=False, use_stats=True)

    def _on_wafer_end(self, tc: TestCell, data: NexusData) -> None:
        if self.buf is None:
            return
        self._diagnose(tc, final=True)
        log.info(
            "WAFEREND wafer=%s n_devices=%d yield=%.1f%%",
            self.wafer_id,
            self.buf.n_devices,
            self.buf.yield_rate * 100,
        )

    def _diagnose(self, tc: TestCell, final: bool, use_stats: bool = False) -> None:
        """三層式診斷：第 1 層二元（是否 abnormal）→ 第 2 層原因 → 第 3 層 die 定位。

        mid-wafer（final=False）只在「診斷出新的原因」時通報一次；
        wafer 統計偵測（low_yield / stdev_trend_down，沒有離群 die 可依據）雜訊較大，
        需要連續兩次檢查都得到同一個結論才通報（debounce）。
        final=True（WAFEREND）一定會存報告，異常時再通報一次最終結論。
        """
        assert self.buf is not None
        stats = self.detector.evaluate(self.buf) if (final or use_stats) else []
        diag = self.hier.analyze(stats)

        if not final:
            if not diag.abnormal:
                if use_stats:
                    self._prev_stats_cause = None
                return
            if diag.cause in STATS_ONLY_CAUSES:
                confirmed = diag.cause == self._prev_stats_cause
                self._prev_stats_cause = diag.cause
                if not confirmed:
                    return
            if diag.cause == self._alerted_cause:
                return
            self._alerted_cause = diag.cause

        findings = [
            CategoryFinding(
                category=f["category"],
                score=f["score"],
                severity=f["severity"],
                triggered_columns=f["triggered_columns"],
            )
            for f in stats
            if f["category"] == diag.cause and diag.cause in STATS_ONLY_CAUSES
        ]

        ctx = WaferReportContext(
            wafer_id=self.wafer_id or -1,
            lot=self.lot,
            tester_id=tc.testerId,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S") + (" (mid-wafer)" if not final else ""),
            n_devices=self.buf.n_devices,
            yield_rate=self.buf.yield_rate,
            devices=self.buf.devices,
            findings=findings,
            trend_series={},
            diagnosis=diag,
        )
        report_path = save_report(ctx)

        if diag.abnormal:
            ActionManager.set_message(tc.testerId, build_message_text(ctx, report_path))
            log.warning("wafer=%s ABNORMAL cause=%s final=%s", self.wafer_id, diag.cause, final)
        elif final:
            log.info("wafer=%s normal, report saved to %s", self.wafer_id, report_path)

    # ------------------------------------------------------------------ #
    # 場景二：consumeTPRequest
    # ------------------------------------------------------------------ #
    def consumeTPRequest(self, tc: TestCell, request: str) -> str:
        try:
            payload = json.loads(request)
        except (TypeError, json.JSONDecodeError):
            log.error("consumeTPRequest: cannot parse request=%r", request)
            return ""

        key = payload.get("key")
        if key != "predict":
            log.info("consumeTPRequest: ignoring unknown key=%s", key)
            return ""

        predict_num = int(payload["data"])
        wait = 10
        message = f"prediction {predict_num}: "
        for site in sorted(self.known_sites):
            buffer = self.current_device.get(site, {})
            meta = self.current_meta.get(site, {})
            try:
                value = self.predictor.predict(predict_num, site, meta.get("x"), meta.get("y"), buffer)
            except KeyError:
                log.exception("no model for stage %s", predict_num)
                value = float("nan")
            message += f"{site},{value:.2f}  "

        ActionManager.set_wait(tc.testerId, wait, message)
        response = ActionManager.get(tc.testerId)
        log.debug("consumeTPRequest predict_num=%s -> %s", predict_num, response)
        return response

    def consumeTPSend(self, tc: TestCell, data: str) -> None:
        log.debug("consumeTPSend: %s", data)
