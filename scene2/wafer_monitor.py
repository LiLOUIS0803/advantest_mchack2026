"""
場景二第二層：wafer 層級的溫度預警 + 報表資料（只依賴標準函式庫）

想法：
  溫度的變異主要是「整片 wafer 一起偏高/偏低」，片內每顆差異很小，
  所以測完前幾個 touchdown，用目前的平均就能推估整片的溫度水準。
  和訓練資料裡 23 片正常 wafer 的分佈比，算 z 分數；z 超過門檻就發警告（每片每個 sensor 只發一次）。

用法：
    wm = WaferMonitor("models/baseline.json", out_dir="report")
    wm.start_wafer("W02")
    # 每顆晶片測完（TESTEND）時：
    wm.record_device(pid=1, site=1, x=5, y=2, pred={1: 28.39, ...}, actual={1: 28.39, ...}, sbin=1)
    ...
    summary, alerts = wm.end_touchdown()     # 更新統計、判斷警告、寫 report/wafer_W02.json
    wm.end_wafer()

JSON 格式（給網頁用）：
  {
    "wafer_id", "updated_at", "touchdowns_done", "devices_done", "status": "testing"|"done",
    "devices": [{"pid","site","x","y","sbin","pred":[6],"actual":[6],"over_limit_pred":[6],"over_limit_actual":[6]}],
    "sensors": {"1": {"name","limit_hi","mu0","sd0","within",
                      "n","mean_pred","mean_actual","z","over_limit_rate_est",
                      "n_over_limit_pred","n_over_limit_actual","alert": bool,"alert_at_touchdown": int|null}},
    "alerts": [{"touchdown","sensor","z","over_limit_rate_est","message"}],
    "history": [{"touchdown","devices_done","z":{"1":..},"mean_actual":{"1":..}}]
  }
"""
import json
import math
import os
import time
from typing import Callable, Dict, List, Optional


def _norm_sf(x: float, mu: float, sd: float) -> float:
    """P(N(mu, sd) > x)，不用 scipy"""
    if sd <= 0:
        return 1.0 if mu > x else 0.0
    return 0.5 * math.erfc((x - mu) / (sd * math.sqrt(2)))


class WaferMonitor:
    def __init__(self, baseline_path: str, out_dir: str = "report",
                 min_touchdowns: int = 2, z_alert: float = 3.0, rate_alert: float = 0.10,
                 alert_sensors: Optional[List[int]] = None, on_alert: Optional[Callable[[str], None]] = None,
                 use_z_alert: bool = False, alerts_enabled: bool = False):
        """
        警告規則（每片每個 sensor 只發一次，從第 min_touchdowns 個 touchdown 起判斷）：
          - 預估最終超限率 > rate_alert  （以規格上限為準，跨 lot 都適用）
          - use_z_alert=True 時額外：z > z_alert（相對訓練 lot 的正常 wafer；換 lot 後基準會失準，預設關）
        z 仍然會算並寫進報表當參考。
        """
        b = json.load(open(baseline_path))
        self.base: Dict[int, dict] = {int(k): v for k, v in b["sensors"].items()}
        self.out_dir = out_dir
        self.min_td = min_touchdowns
        self.z_alert = z_alert
        self.rate_alert = rate_alert
        self.alert_sensors = alert_sensors or sorted(self.base.keys())
        self.on_alert = on_alert
        self.use_z_alert = use_z_alert
        self.alerts_enabled = alerts_enabled     # 預設關：主辦方要的是預測 vs 實際的誤差，過熱警告只是附加
        self.wafer_id: Optional[str] = None
        self._reset()

    # ------------------------------------------------------------ 生命週期
    def _reset(self):
        self.devices: List[dict] = []
        self.touchdowns = 0
        self.alerts: List[dict] = []
        self.alerted = {k: None for k in self.base}
        self.history: List[dict] = []
        self.status = "testing"
        self._pending: List[dict] = []
        self._last_n = 0

    def start_wafer(self, wafer_id: str):
        self.wafer_id = str(wafer_id)
        self._reset()
        self._write()

    def record_device(self, pid, site, x, y, pred: Dict[int, float], actual: Dict[int, float],
                      sbin=None, pf=None, raw: Optional[Dict[int, float]] = None,
                      forecast: Optional[Dict[int, float]] = None):
        """
        pred     = 正式被問時回給機台的預測值（含線上偏差校正；問 sensor k 時已用到 sensor 1..k-1 的真值）
        raw      = 模型原始輸出（校正前）
        forecast = 問 sensor1 那一刻就鏈式猜出的 6 個「初次預測」（後面 sensor 的真值都還沒有）
        """
        ks = sorted(self.base.keys())
        raw = raw or {}
        forecast = forecast or {}
        row = {
            "pid": _int(pid), "site": _int(site), "x": _int(x), "y": _int(y),
            "sbin": _int(sbin) if sbin is not None else None,
            "pf": _int(pf) if pf is not None else None,
            "pred": [_f(pred.get(k)) for k in ks],
            "raw": [_f(raw.get(k)) for k in ks],
            "forecast": [_f(forecast.get(k)) for k in ks],
            "actual": [_f(actual.get(k)) for k in ks],
        }
        row["over_limit_pred"] = [self._over(k, v) for k, v in zip(ks, row["pred"])]
        row["over_limit_actual"] = [self._over(k, v) for k, v in zip(ks, row["actual"])]
        self._pending.append(row)

    def end_touchdown(self):
        """一個 touchdown 的所有晶片 record_device 之後呼叫。回傳 (sensors_summary, new_alert_messages)"""
        self._last_n = len(self._pending)
        self.devices.extend(self._pending)
        self._pending = []
        self.touchdowns += 1
        summ = self._summarize()
        new_msgs = []
        if self.alerts_enabled and self.touchdowns >= self.min_td:
            for k in self.alert_sensors:
                s = summ[str(k)]
                if self.alerted[k] is not None or s["n"] == 0:
                    continue
                hot = self.use_z_alert and s["z"] is not None and s["z"] > self.z_alert
                risky = s["over_limit_rate_est"] is not None and s["over_limit_rate_est"] > self.rate_alert
                if hot or risky:
                    msg = self._alert_text(k, s)
                    self.alerted[k] = self.touchdowns
                    self.alerts.append({"touchdown": self.touchdowns, "sensor": k, "z": s["z"],
                                        "over_limit_rate_est": s["over_limit_rate_est"], "message": msg})
                    new_msgs.append(msg)
                    if self.on_alert:
                        try:
                            self.on_alert(msg)
                        except Exception:
                            pass
        errs = self._touchdown_errors(len(self.devices))
        self.history.append({"touchdown": self.touchdowns, "devices_done": len(self.devices),
                             "mae_td": errs["mae_td"], "mae_raw_td": errs["mae_raw_td"],
                             "mae_cum": errs["mae_cum"], "mae_raw_cum": errs["mae_raw_cum"],
                             "z": {k: v["z"] for k, v in summ.items()},
                             "mean_actual": {k: v["mean_actual"] for k, v in summ.items()},
                             "mean_pred": {k: v["mean_pred"] for k, v in summ.items()},
                             "over_limit_rate_est": {k: v["over_limit_rate_est"] for k, v in summ.items()}})
        self._write(summ)
        return summ, new_msgs

    def write_live(self, touchdown: int, step: int, sites: list, forecast: dict, pred: dict, actual: dict, coords: dict):
        """
        一個 touchdown 進行中的即時狀態（給正式版網頁輪詢用）。
        step: 0 = 剛壓下去；2k-1 = 已問 sensor k（預測出來了）；2k = sensor k 量到了。一個 touchdown 共 12 步。
        forecast/pred/actual: {site: {k: value}}
        """
        if not self.out_dir:
            return
        ks = sorted(self.base.keys())
        live = {
            "wafer_id": self.wafer_id, "updated_at": time.time(),
            "touchdown": touchdown, "step": step, "devices_done": len(self.devices),
            "sites": [{
                "site": _int(s), "x": _int(coords.get(s, (None, None))[0]), "y": _int(coords.get(s, (None, None))[1]),
                "forecast": [_f(forecast.get(s, {}).get(k)) for k in ks],
                "pred": [_f(pred.get(s, {}).get(k)) for k in ks],
                "actual": [_f(actual.get(s, {}).get(k)) for k in ks],
            } for s in sites],
        }
        try:
            os.makedirs(self.out_dir, exist_ok=True)
            tmp = os.path.join(self.out_dir, "live.json.tmp")
            with open(tmp, "w") as f:
                json.dump(live, f)
            os.replace(tmp, os.path.join(self.out_dir, "live.json"))
        except Exception:
            pass

    def end_wafer(self):
        if self._pending:
            self.end_touchdown()
        self.status = "done"
        self._write()

    # ------------------------------------------------------------ 統計
    def _touchdown_errors(self, n_done: int) -> dict:
        """這個 touchdown（最後 _last_n 顆）與累積到目前為止的 MAE，校正後(pred)與校正前(raw)各一份"""
        ks = sorted(self.base.keys())
        last = self.devices[-self._last_n:] if self._last_n else []
        def mae(rows, field):
            out = {}
            for i, k in enumerate(ks):
                e = [abs(d[field][i] - d["actual"][i]) for d in rows if d[field][i] is not None and d["actual"][i] is not None]
                out[str(k)] = (sum(e) / len(e)) if e else None
            return out
        return {"mae_td": mae(last, "pred"), "mae_raw_td": mae(last, "raw"),
                "mae_cum": mae(self.devices, "pred"), "mae_raw_cum": mae(self.devices, "raw")}

    def _summarize(self) -> Dict[str, dict]:
        out = {}
        for i, k in enumerate(sorted(self.base.keys())):
            b = self.base[k]
            act = [d["actual"][i] for d in self.devices if d["actual"][i] is not None]
            prd = [d["pred"][i] for d in self.devices if d["pred"][i] is not None]
            use = act if act else prd            # 有實際值優先用實際值
            n = len(use)
            mean = sum(use) / n if n else None
            z = None
            rate = None
            if n:
                se = math.sqrt(b["sd0"] ** 2 + b["within"] ** 2 / n)
                z = (mean - b["mu0"]) / se
                rate = _norm_sf(b["limit_hi"], mean, b["within"])
            out[str(k)] = {
                "name": b["name"], "limit_hi": b["limit_hi"], "mu0": b["mu0"], "sd0": b["sd0"], "within": b["within"],
                "n": n,
                "mean_pred": (sum(prd) / len(prd)) if prd else None,
                "mean_actual": (sum(act) / len(act)) if act else None,
                "z": z, "over_limit_rate_est": rate,
                "n_over_limit_pred": sum(1 for d in self.devices if d["over_limit_pred"][i]),
                "n_over_limit_actual": sum(1 for d in self.devices if d["over_limit_actual"][i]),
                "alert": self.alerted[k] is not None, "alert_at_touchdown": self.alerted[k],
                "mae": _mae([(d["pred"][i], d["actual"][i]) for d in self.devices]),
                "mae_raw": _mae([(d["raw"][i], d["actual"][i]) for d in self.devices]),
                "max_abs_err": _maxerr([(d["pred"][i], d["actual"][i]) for d in self.devices]),
            }
        return out

    def _alert_text(self, k: int, s: dict) -> str:
        parts = [f"Wafer {self.wafer_id}: sensor{k} mean {s['mean_actual'] or s['mean_pred']:.2f}C after {s['n']} devices",
                 f"{s['z']:+.1f} sigma vs normal ({s['mu0']:.2f}C)"]
        if s["over_limit_rate_est"] is not None and s["over_limit_rate_est"] > 0.005:
            parts.append(f"est. {s['over_limit_rate_est']:.0%} devices will exceed {s['limit_hi']:.0f}C limit")
        parts.append("recommend cool-down")
        return "; ".join(parts)

    def _over(self, k: int, v):
        if v is None:
            return False
        b = self.base[k]
        return bool(v > b["limit_hi"] or v < b["limit_lo"])

    # ------------------------------------------------------------ 輸出
    def state(self, summ=None) -> dict:
        return {
            "wafer_id": self.wafer_id, "updated_at": time.time(), "status": self.status,
            "touchdowns_done": self.touchdowns, "devices_done": len(self.devices),
            "devices": self.devices, "sensors": summ or self._summarize(),
            "alerts": self.alerts, "history": self.history,
        }

    def _write(self, summ=None):
        if not self.out_dir or self.wafer_id is None:
            return
        try:
            os.makedirs(self.out_dir, exist_ok=True)
            path = os.path.join(self.out_dir, f"wafer_{self.wafer_id}.json")
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state(summ), f)
            os.replace(tmp, path)            # 原子寫入，網頁不會讀到寫一半的檔
            with open(os.path.join(self.out_dir, "current.json"), "w") as f:
                json.dump({"wafer_id": self.wafer_id, "file": os.path.basename(path)}, f)
        except Exception:
            pass


def _mae(pairs):
    e = [abs(a - b) for a, b in pairs if a is not None and b is not None]
    return (sum(e) / len(e)) if e else None


def _maxerr(pairs):
    e = [abs(a - b) for a, b in pairs if a is not None and b is not None]
    return max(e) if e else None


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _f(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None
