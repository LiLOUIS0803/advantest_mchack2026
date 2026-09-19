#!/usr/bin/env python3
"""
用假的 NexusData 物件測 TempPredictor.consume_nexus_data()，
模擬 ONEAPI 手冊 1.1.3.4 的 MEASURED_MULTI_PARAM / MEASURED_PARAMETRIC / TESTEND 事件。
不需要真的 oneapi 套件。
"""
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from temp_predictor import TempPredictor, _split_name
from train_temp_models import load_csv, META


class FakeDataType:
    DATA_TYP_PRODUCTION_TESTSTART = 3
    DATA_TYP_MEASURED_PARAMETRIC = 7
    DATA_TYP_MEASURED_MULTI_PARAM = 9
    DATA_TYP_PRODUCTION_TESTEND = 4


class FakeMultiParam:
    """一個測項、4 個 site 的 MULTI_PARAM 事件；同編號多 pin 時 Results 是多個值"""
    def __init__(self, num, suite, pins, per_site_values, sites=(1, 2, 3, 4)):
        self.num, self.suite, self.pins, self.vals, self.sites = num, suite, pins, per_site_values, sites
    def getType(self): return FakeDataType.DATA_TYP_MEASURED_MULTI_PARAM
    def get_ResultCount(self): return len(self.sites)
    def query_HeadSite(self, i): return self.sites[i]
    def toSite(self, hs): return hs
    def query_TestNumber(self, i): return self.num
    def query_TestText(self, i): return f"{self.suite}:{self.pins[0]}" if len(self.pins) == 1 else self.suite
    def query_Results(self, i): return list(self.vals[i])
    def query_PinResults(self, i): return list(range(len(self.pins)))
    def query_PinName(self, pid): return self.pins[pid]


class FakeParametric(FakeMultiParam):
    def getType(self): return FakeDataType.DATA_TYP_MEASURED_PARAMETRIC
    def query_Result(self, i): return self.vals[i][0]


class FakeTestEnd:
    def getType(self): return FakeDataType.DATA_TYP_PRODUCTION_TESTEND


def main():
    tp = TempPredictor("models/temp_models.pkl")
    df, _ = load_csv("../data/A12345_W10_RawResult.csv")
    test_cols = [c for c in df.columns if c not in META]
    td = df.sort_values("PID").iloc[:4]          # 第一個 touchdown, site 1..4
    sites = td.Site.tolist()

    # 把 CSV 欄位依 (編號, suite) 分組 -> 一個事件可能帶多支 pin
    groups = {}
    for c in test_cols:
        num, core, pin = _split_name(c)
        groups.setdefault((num, core), []).append((pin, c))
    sensor_cols = [c for c in test_cols if "sensor" in c]

    ok = True
    for (num, core), pinlist in groups.items():          # dict 保持插入順序 = 流程順序
        first_col = pinlist[0][1]
        if first_col in sensor_cols:                      # 到 sensor 之前先預測，和離線比對
            k = sensor_cols.index(first_col) + 1
            for s, (_, r) in zip(sites, td.iterrows()):
                pv, info = tp.predict_site(k, s)
                # 離線同樣特徵直接算
                m = tp.models[k]
                x = np.array([r[n] if not np.isnan(r[n]) else med for n, med in zip(m["feature_names"], m["median"])])
                ref = float(((x - m["mean"]) / m["scale"]) @ m["coef"] + m["intercept"])
                if abs(pv - ref) > 1e-9 or info["n_missing"] > 0:
                    ok = False
                    print(f"MISMATCH sensor{k} site{s}: stream={pv:.6f} offline={ref:.6f} missing={info['missing']}")
        pins = [p for p, _ in pinlist]
        vals = [[r[c] for _, c in pinlist] for _, r in td.iterrows()]
        ev = FakeMultiParam(num, core, pins, vals, sites) if len(pins) > 1 or num % 2 else FakeParametric(num, core, pins, vals, sites)
        tp.consume_nexus_data(ev, FakeDataType)

    print("buffer 內每個 site 的 key 數:", {s: len(b) for s, b in tp.buf.items()}, "(應為 35 = 29 features + 6 sensors)")
    print("560 的兩支 pin 都有存:", [(k, round(v, 3)) for k, v in tp.buf[1].items() if k[0] == 560])
    print("stats:", tp.stats)
    tp.consume_nexus_data(FakeTestEnd(), FakeDataType)
    print("TESTEND 後 buffer 清空:", tp.buf == {})
    print("\n串流預測 == 離線計算:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
