"""
場景二接到 ONEAPI 範例 (oneAPI_py3.10/bin/sample.py) 的膠水層。
兩層：
  1. 每顆晶片、每個 predict 點回傳預測值（TempPredictor）
  2. wafer 層級預警 + 報表 JSON（WaferMonitor）

給合併用：Monitor 類別只要在三個地方各加一行：

    from scene2_hook import Scene2

    class SampleMonitor(Monitor):
        def __init__(self):
            ...
            self.scene2 = Scene2(model_dir="models", report_dir="report")

        def consumeData(self, tc, data):
            self.scene2.on_data(tc, data, DataType, ActionManager)   # <-- 1. 每個事件都丟進來
            ... 場景一的處理 ...

        def consumeTPRequest(self, tc, request):
            jsonObj = json.loads(request)
            key, data = jsonObj.get("key"), jsonObj.get("data")
            if key == "predict":
                return self.scene2.on_predict(tc, data, ActionManager)   # <-- 2. predict 分支交給它
            ...

事件對應（ONEAPI User Guide 1.1.3.4）：
  WAFERSTART  get_WaferId()                      -> 開新 wafer 報表
  TESTSTART   get_HeadSiteList(), query_XCoord(i)/query_YCoord(i)  -> 記 site 與座標
  MEASURED_*  (交給 TempPredictor)
  TESTEND     query_HeadSite(i), query_PartId(i), query_SBinResult(i), query_XCoord/YCoord
              -> 收集這 4 顆的預測/實際 -> WaferMonitor.end_touchdown() -> 必要時 set_message
  WAFEREND    -> 報表標 done
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from temp_predictor import TempPredictor, to_site
from wafer_monitor import WaferMonitor

INVALID_COORDS = {-32768, 32767, 65535, -1}   # ONEAPI 沒座標時給的值

log = logging.getLogger("scene2")


class Scene2:
    def __init__(self, model_dir="models", report_dir="report", wait=10, ndigits=3,
                 default_sites=(1, 2, 3, 4), min_touchdowns=2, z_alert=3.0, alerts_enabled=False):
        """alerts_enabled: wafer 層級過熱警告（set_message）。預設關，主辦方要的是預測 vs 實際的誤差。"""
        self.tp = TempPredictor(os.path.join(model_dir, "temp_models.pkl"))
        self.wm = WaferMonitor(os.path.join(model_dir, "baseline.json"), out_dir=report_dir,
                               min_touchdowns=min_touchdowns, z_alert=z_alert, alerts_enabled=alerts_enabled)
        self.wait = wait
        self.ndigits = ndigits
        self.sites = list(default_sites)
        self.coords = {}            # site -> (x, y)，TESTSTART 時記
        self.forecast = {}          # site -> {k: 初次預測}（問 sensor1 時鏈式猜的 6 個）
        self.step = 0               # touchdown 內進度：2k-1 = 問完 sensor k，2k = 量到 sensor k
        self.pid_counter = 0
        self.history = []           # (timestamp, k, {site: value})
        self.wm.start_wafer("unknown")

    # ---- 1. consumeData ----
    def on_data(self, tc, data, DataType, ActionManager=None):
        try:
            t = data.getType()
            if t == getattr(DataType, "DATA_TYP_PRODUCTION_LOTSTART", object()):
                self.tp.reset_bias()          # 換 lot 重新學偏差
                return
            if t == DataType.DATA_TYP_PRODUCTION_WAFERSTART:
                wid = _safe(lambda: str(data.get_WaferId()), "unknown")
                self.pid_counter = 0
                self.wm.start_wafer(wid)
                return
            if t == DataType.DATA_TYP_PRODUCTION_WAFEREND:
                self.wm.end_wafer()
                return
            if t == DataType.DATA_TYP_PRODUCTION_TESTSTART:
                self._on_teststart(data)
                return
            if t == DataType.DATA_TYP_PRODUCTION_TESTEND:
                self._on_testend(tc, data, ActionManager)
                self.tp.end_all()
                return
            kind = self.tp.consume_nexus_data(data, DataType)
            if kind in ("MULTI_PARAM", "PARAMETRIC"):
                k = self._sensor_in_event(data)
                if k:                                   # sensor k 的真值到了
                    self.step = max(self.step, 2 * k)
                    self._write_live()
        except Exception as e:  # 絕不能讓場景二的錯誤把整個 consumeData 弄掛
            log.exception("scene2.on_data error: %s", e)

    def _on_teststart(self, data):
        hs = _safe(lambda: list(data.get_HeadSiteList()), [])
        if hs:
            sites = []
            for i, h in enumerate(hs):
                s = self._to_site(data, h)
                sites.append(s)
                self.coords[s] = (_safe(lambda: data.query_XCoord(i), None), _safe(lambda: data.query_YCoord(i), None))
            self.sites = sites
        self.tp.end_all()
        self.forecast = {}
        self.step = 0
        self._write_live()

    def _sensor_in_event(self, data):
        try:
            n = int(data.get_ResultCount())
            for i in range(n):
                num = int(data.query_TestNumber(i))
                for k, key in self.tp.target_key.items():
                    if key[0] == num:
                        return k
        except Exception:
            pass
        return None

    def _write_live(self):
        pred = {s: dict(self.tp.last_pred.get(s, {})) for s in self.sites}
        actual = {s: {k: self.tp.buf.get(s, {}).get(key) for k, key in self.tp.target_key.items()} for s in self.sites}
        self.wm.write_live(self.wm.touchdowns + 1, self.step, self.sites, self.forecast, pred, actual, self.coords)

    def _on_testend(self, tc, data, ActionManager):
        n = _safe(lambda: int(data.get_ResultCount()), 0)
        for i in range(n):
            site = self._to_site(data, data.query_HeadSite(i))
            x = _safe(lambda: data.query_XCoord(i), None)
            y = _safe(lambda: data.query_YCoord(i), None)
            if x in INVALID_COORDS or y in INVALID_COORDS:
                x, y = self.coords.get(site, (None, None))
            if x in INVALID_COORDS or y in INVALID_COORDS:
                x, y = None, None
            pid = _safe(lambda: data.query_PartId(i), None)
            self.pid_counter += 1
            if pid in (None, ""):
                pid = self.pid_counter
            sbin = _safe(lambda: data.query_SBinResult(i), None)
            pred = dict(self.tp.last_pred.get(site, {}))
            raw = dict(self.tp.last_raw.get(site, {}))
            actual = {k: self.tp.buf.get(site, {}).get(key) for k, key in self.tp.target_key.items()}
            self.wm.record_device(pid, site, x, y, pred, actual, sbin=sbin, raw=raw, forecast=self.forecast.get(site))
        if n:
            _, msgs = self.wm.end_touchdown()
            for m in msgs:
                log.warning("scene2 ALERT: %s", m)
                if ActionManager is not None:
                    try:
                        ActionManager.set_message(tc.testerId, m)
                    except Exception as e:
                        log.exception("set_message failed: %s", e)

    # ---- 2. consumeTPRequest 的 predict 分支 ----
    def on_predict(self, tc, predict_num, ActionManager=None):
        """回傳 ActionManager.get() 的結果；若沒給 ActionManager（本機測試），回傳 message 字串。"""
        try:
            k = int(predict_num)
        except (TypeError, ValueError):
            k = 1
        try:
            if k == 1:
                # 問 sensor1 的那一刻，把 6 個全部鏈式猜一遍當「初次預測」（後面的 sensor 用自己的預測當輸入）
                self.forecast = {}
                for s in self.sites:
                    self.forecast[s] = {kk: round(self.tp.predict_site(kk, s)[0], self.ndigits) for kk in range(1, 7)}
            preds = self.tp.predict(k, self.sites, self.ndigits)
            self.step = max(self.step, 2 * k - 1)
            self._write_live()
        except Exception as e:
            log.exception("scene2.on_predict error: %s", e)
            m = self.tp.models.get(k)
            fallback = round(float(m["intercept"]), self.ndigits) if m else 25.22
            preds = {s: fallback for s in self.sites}
        message = f"prediction {k}:" + "".join(f" ({s},{v})" for s, v in preds.items())
        self.history.append((time.time(), k, preds))
        log.info("scene2 %s", message)
        if ActionManager is None:
            return message
        ActionManager.set_wait(tc.testerId, self.wait, message)
        return ActionManager.get(tc.testerId)

    # ---- 內部 ----
    @staticmethod
    def _to_site(data, headsite):
        return to_site(headsite)


def _safe(fn, default):
    try:
        v = fn()
        return default if v is None else v
    except Exception:
        return default
