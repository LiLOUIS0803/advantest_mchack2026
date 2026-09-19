"""
場景二：串流溫度預測器（推論端，只依賴 numpy）

用法（在 container 裡）:

    from temp_predictor import TempPredictor
    tp = TempPredictor("models/temp_models.pkl")

    # A. 最省事：在 consumeData 裡直接把 ONEAPI 的 NexusData 丟進來
    #    （會自己處理 MEASURED_PARAMETRIC / MEASURED_MULTI_PARAM / TESTEND）
    tp.consume_nexus_data(data, DataType)

    # B. 或者自己拆好再餵：test 可以是編號 220、欄名 "220_Main.Suite1#CP"、STDF 名 "Main.Suite1:CP"
    tp.update(site=1, test=220, value=1.145)              # 編號唯一時可以不給 pin
    tp.update(site=1, test=560, value=1.3, pin="MR")     # 560 有 CP/MR 兩支 pin，要給 pin

    # 機台送來 key=="predict", data==k 時（consumeTPRequest 裡）:
    msg = tp.predict_message(k, sites=[1, 2, 3, 4])       # 'prediction 3: (1,29.135) (2,29.101) ...'

    # 該 touchdown 測完（TESTEND）後清掉 buffer：
    tp.end_all()

設計重點:
  - 每個 site 一個 buffer，只存「模型會用到的」測項，其他測項直接忽略
  - buffer 的 key 是 (測項編號, pin)。同一編號多支 pin 的測項（例如 560 的 CP/MR）不會互相覆蓋
  - 缺值（還沒收到、或 NaN）用訓練資料的中位數補，info 裡會記錄缺了哪些
  - 預測 sensor k 時，若 sensor 1..k-1 的實際值已收到就用實際值；沒收到可用自己先前的預測值代替
"""
import pickle
import json
import re
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

try:  # 真正的 ONEAPI 環境：headsite 是 head+site 合成的整數，要用 oneapi.toSite 轉
    from oneapi import toSite as _oneapi_toSite
except Exception:  # 本機測試沒有 oneapi
    _oneapi_toSite = None


def to_site(headsite) -> int:
    if _oneapi_toSite is not None:
        try:
            return int(_oneapi_toSite(headsite))
        except Exception:
            pass
    return int(headsite)


Key = Tuple[int, str]  # (test_number, pin)  pin 可為 ""


def _split_name(name: str) -> Tuple[Optional[int], str, str]:
    """'220_Main.Suite1#CP' -> (220, 'Main.Suite1', 'CP');  'Main.Suite1:CP' -> (None, 'Main.Suite1', 'CP')"""
    num = None
    m = re.match(r"^(\d+)_(.*)$", name)
    if m:
        num, name = int(m.group(1)), m.group(2)
    pin = ""
    for sep in ("#", ":"):
        if sep in name:
            name, pin = name.split(sep, 1)
            break
    return num, name.strip(), pin.strip()


class TempPredictor:
    def __init__(self, model_path: str, use_own_prediction: bool = True,
                 bias_correction: bool = True, bias_alpha: float = 0.3):
        """
        bias_correction: 線上偏差校正。每顆晶片的 sensor 實際值在預測後馬上會量到，
            用 (實際 − 預測) 的指數移動平均當作下一顆的修正量。用來吸收不同 lot/batch 的整體平移
            （Gemini 回放的 lot B13456 相對訓練 lot A12345，sensor4 整體偏 0.7°C）。
        bias_alpha: EMA 係數，0.3 代表大約 3–4 顆就跟上。
        """
        if str(model_path).endswith('.json'):
            with open(model_path, encoding='utf-8') as f:self.bundle=json.load(f)
            self.bundle['models']={int(k):v for k,v in self.bundle['models'].items()}
            self.bundle['targets']={int(k):v for k,v in self.bundle['targets'].items()}
            for model in self.bundle['models'].values():
                for field in ('median','mean','scale','coef'):model[field]=np.asarray(model[field],dtype=float)
        else:
            with open(model_path, "rb") as f:
                self.bundle = pickle.load(f)
        self.bias_correction = bias_correction
        self.bias_alpha = bias_alpha
        self.bias: Dict[int, float] = {}          # k -> 目前修正量
        self.bias_n: Dict[int, int] = {}          # k -> 已看過幾個殘差
        self.models: Dict[int, dict] = self.bundle["models"]
        self.targets: Dict[int, str] = self.bundle["targets"]
        self.use_own_prediction = use_own_prediction

        # 每個模型的特徵 key 列表
        self.model_keys: Dict[int, List[Key]] = {}
        for k, m in self.models.items():
            self.model_keys[k] = [self._key_from_name(n) for n in m["feature_names"]]
        self.target_key: Dict[int, Key] = {k: self._key_from_name(v) for k, v in self.targets.items()}
        self.key_to_sensor: Dict[Key, int] = {v: k for k, v in self.target_key.items()}

        # 需要的 key 集合、以及 編號 -> 該編號有哪些 pin
        self.needed: set = set()
        for keys in self.model_keys.values():
            self.needed.update(keys)
        self.needed.update(self.target_key.values())
        self.pins_of_num: Dict[int, List[str]] = {}
        for num, pin in self.needed:
            self.pins_of_num.setdefault(num, []).append(pin)

        # 測試名稱（不含編號） -> 編號，讓 STDF 風格 "Main.Suite1:CP" 也能對上
        self.name_to_num: Dict[str, int] = {}
        for m in self.models.values():
            for n in m["feature_names"]:
                num, core, _ = _split_name(n)
                self.name_to_num[core] = num
        for v in self.targets.values():
            num, core, _ = _split_name(v)
            self.name_to_num[core] = num

        self.buf: Dict[int, Dict[Key, float]] = {}        # site -> {key: value}
        self.last_pred: Dict[int, Dict[int, float]] = {}  # site -> {k: predicted (含校正)}
        self.last_raw: Dict[int, Dict[int, float]] = {}   # site -> {k: 模型原始輸出 (未校正)}
        self.stats = {"updates_kept": 0, "updates_ignored": 0, "predicts": 0}

    # ------------------------------------------------------------ 資料進入
    def update(self, site: int, test, value, pin: Optional[str] = None) -> bool:
        """餵一筆量測值。回傳 True 表示這個測項是模型需要的（有被存起來）。"""
        key = self._resolve_key(test, pin)
        if key is None:
            self.stats["updates_ignored"] += 1
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if not np.isfinite(v):
            return False
        self.buf.setdefault(int(site), {})[key] = v
        self.stats["updates_kept"] += 1
        kk = self.key_to_sensor.get(key)
        if kk is not None and self.bias_correction:
            raw = self.last_raw.get(int(site), {}).get(kk)
            if raw is not None:
                r = v - raw
                if kk in self.bias:
                    self.bias[kk] = (1 - self.bias_alpha) * self.bias[kk] + self.bias_alpha * r
                else:
                    self.bias[kk] = r
                self.bias_n[kk] = self.bias_n.get(kk, 0) + 1
        return True

    def consume_nexus_data(self, data, DataType) -> Optional[str]:
        """
        直接吃 ONEAPI 的 NexusData（在 consumeData 裡呼叫）。
        回傳處理到的事件種類字串，或 None（不是我們關心的事件）。
        依 ONEAPI User Guide 1.1.3.4：
          MEASURED_PARAMETRIC : get_ResultCount, query_HeadSite(i), query_TestNumber(i), query_Result(i), query_TestText(i)
          MEASURED_MULTI_PARAM: 同上，但值在 query_Results(i)（list），pin 在 query_PinResults(i)/query_PinName(pid)
          PRODUCTION_TESTEND  : 一個 touchdown 結束 -> 清 buffer
        """
        t = data.getType()
        if t == DataType.DATA_TYP_MEASURED_PARAMETRIC:
            n = data.get_ResultCount()
            for i in range(n):
                num = int(data.query_TestNumber(i))
                if num not in self.pins_of_num:
                    continue
                site = self._site_of(data, i)
                pin = self._pin_from_text(data, i)
                self.update(site, num, data.query_Result(i), pin=pin)
            return "PARAMETRIC"

        if t == DataType.DATA_TYP_MEASURED_MULTI_PARAM:
            n = data.get_ResultCount()
            for i in range(n):
                num = int(data.query_TestNumber(i))
                if num not in self.pins_of_num:
                    continue
                site = self._site_of(data, i)
                vals = list(data.query_Results(i))
                pins: List[str] = []
                try:
                    pins = [str(data.query_PinName(pid)) for pid in data.query_PinResults(i)]
                except Exception:
                    pass
                if len(pins) == len(vals) and pins:
                    for p, v in zip(pins, vals):
                        self.update(site, num, v, pin=p)
                else:
                    # 沒有 pin 資訊：只有一個值就當作該編號唯一的 pin
                    if vals:
                        self.update(site, num, vals[0], pin=self._pin_from_text(data, i))
            return "MULTI_PARAM"

        if t == DataType.DATA_TYP_PRODUCTION_TESTEND:
            self.end_all()
            return "TESTEND"
        return None

    def end_device(self, site: int):
        self.buf.pop(int(site), None)
        self.last_pred.pop(int(site), None)
        self.last_raw.pop(int(site), None)

    def end_all(self):
        """一個 touchdown 結束：清晶片 buffer。偏差修正量保留（它是 lot/wafer 層級的）。"""
        self.buf.clear()
        self.last_pred.clear()
        self.last_raw.clear()

    def reset_bias(self):
        """換 lot 或想重新學偏差時呼叫（換 wafer 通常不用）。"""
        self.bias.clear()
        self.bias_n.clear()

    # ------------------------------------------------------------ 預測
    def predict_site(self, k: int, site: int):
        """回傳 (value, info)。info 含缺值清單與是否會超規格。"""
        k = int(k)
        m = self.models[k]
        keys = self.model_keys[k]
        b = self.buf.get(int(site), {})
        own = self.last_pred.get(int(site), {})
        x = np.empty(len(keys), dtype=float)
        missing = []
        for i, key in enumerate(keys):
            if key in b:
                x[i] = b[key]
            else:
                kk = self.key_to_sensor.get(key)
                if kk is not None and self.use_own_prediction and kk in own:
                    x[i] = own[kk]
                else:
                    x[i] = m["median"][i]
                    missing.append(m["feature_names"][i])
        z = (x - m["mean"]) / m["scale"]
        raw = float(z @ m["coef"] + m["intercept"])
        val = raw + (self.bias.get(k, 0.0) if self.bias_correction else 0.0)
        self.last_raw.setdefault(int(site), {})[k] = raw
        self.last_pred.setdefault(int(site), {})[k] = val
        self.stats["predicts"] += 1
        info = {
            "missing": missing,
            "n_missing": len(missing),
            "n_features": len(keys),
            "limit_lo": m["limit_lo"],
            "limit_hi": m["limit_hi"],
            "over_limit": bool(val > m["limit_hi"] or val < m["limit_lo"]),
            "raw": raw, "bias": self.bias.get(k, 0.0), "bias_n": self.bias_n.get(k, 0),
        }
        return val, info

    def predict(self, k: int, sites: Optional[Iterable[int]] = None, ndigits: int = 3) -> Dict[int, float]:
        if sites is None:
            sites = sorted(self.buf.keys())
        return {int(s): round(self.predict_site(k, s)[0], ndigits) for s in sites}

    def predict_message(self, k: int, sites: Iterable[int], ndigits: int = 3) -> str:
        """組成主辦方範例要的字串（與 sample.py 完全一致）:  'prediction 3: (1,28.771) (2,28.802)' """
        msg = f"prediction {int(k)}:"
        for s, v in self.predict(k, sites, ndigits).items():
            msg += f" ({s},{v})"
        return msg

    # ------------------------------------------------------------ 內部
    def _key_from_name(self, name: str) -> Key:
        num, _, pin = _split_name(name)
        return (int(num), pin)

    def _resolve_key(self, test, pin: Optional[str]) -> Optional[Key]:
        num: Optional[int] = None
        if isinstance(test, (int, np.integer)):
            num = int(test)
        else:
            s = str(test)
            if s.isdigit():
                num = int(s)
            else:
                n, core, p = _split_name(s)
                num = n if n is not None else self.name_to_num.get(core)
                if pin is None and p:
                    pin = p
        if num is None or num not in self.pins_of_num:
            return None
        pins = self.pins_of_num[num]
        if pin is None or pin == "":
            if len(pins) == 1:
                return (num, pins[0])
            return None  # 多 pin 卻沒指定 pin -> 無法判斷，忽略
        pin = str(pin).strip()
        if (num, pin) in self.needed:
            return (num, pin)
        # pin 名稱對不上（ONEAPI 的 TestText 有時不是 pin），但該編號只有一支需要的 pin -> 仍接受
        return (num, pins[0]) if len(pins) == 1 else None

    @staticmethod
    def _site_of(data, i) -> int:
        return to_site(data.query_HeadSite(i))

    @staticmethod
    def _pin_from_text(data, i) -> Optional[str]:
        """SmarTest 7 的 TestText 是 'suite:test:pin' 或 'suite:test'；取最後一段當 pin（只在有 ':' 時）"""
        try:
            txt = str(data.query_TestText(i))
        except Exception:
            return None
        _, _, pin = _split_name(txt)
        return pin or None
