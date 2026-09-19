#!/usr/bin/env python3
"""
用假的 ONEAPI 事件把一片 wafer 從 WAFERSTART 跑到 WAFEREND，驅動完整的 Scene2 hook
（預測 + wafer 層級預警 + 報表 JSON）。

    python replay_wafer_events.py --wafer 2 --out report_demo
    → report_demo/wafer_W02.json（最終）、report_demo/snapshots/W02_td01.json ... td20.json（每個 touchdown）

用來：驗證警告時機、產生網頁靜態版要內嵌的快照。
"""
import argparse, glob, json, os, re, shutil, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene2_hook import Scene2
from temp_predictor import _split_name
from train_temp_models import load_csv, META


class DT:  # 假的 DataType 列舉，值不重要，只要彼此不同
    DATA_TYP_PRODUCTION_LOTSTART = 0
    DATA_TYP_PRODUCTION_WAFERSTART = 1
    DATA_TYP_PRODUCTION_WAFEREND = 2
    DATA_TYP_PRODUCTION_TESTSTART = 3
    DATA_TYP_PRODUCTION_TESTEND = 4
    DATA_TYP_MEASURED_PARAMETRIC = 7
    DATA_TYP_MEASURED_MULTI_PARAM = 9


class Ev:
    def __init__(self, typ, **kw):
        self.typ = typ; self.__dict__.update(kw)
    def getType(self): return self.typ
    def toSite(self, hs): return hs


class WaferStart(Ev):
    def __init__(self, wid): super().__init__(DT.DATA_TYP_PRODUCTION_WAFERSTART, wid=wid)
    def get_WaferId(self): return self.wid


class WaferEnd(Ev):
    def __init__(self): super().__init__(DT.DATA_TYP_PRODUCTION_WAFEREND)


class TestStart(Ev):
    def __init__(self, rows): super().__init__(DT.DATA_TYP_PRODUCTION_TESTSTART, rows=rows)
    def get_HeadSiteList(self): return [int(r.Site) for r in self.rows]
    def query_XCoord(self, i): return int(self.rows[i].X)
    def query_YCoord(self, i): return int(self.rows[i].Y)


class TestEnd(Ev):
    def __init__(self, rows): super().__init__(DT.DATA_TYP_PRODUCTION_TESTEND, rows=rows)
    def get_ResultCount(self): return len(self.rows)
    def query_HeadSite(self, i): return int(self.rows[i].Site)
    def query_XCoord(self, i): return int(self.rows[i].X)
    def query_YCoord(self, i): return int(self.rows[i].Y)
    def query_PartId(self, i): return str(int(self.rows[i].PID))
    def query_SBinResult(self, i): return int(self.rows[i].SBin)


class MultiParam(Ev):
    def __init__(self, num, core, pins, rows, cols):
        super().__init__(DT.DATA_TYP_MEASURED_MULTI_PARAM, num=num, core=core, pins=pins, rows=rows, cols=cols)
    def get_ResultCount(self): return len(self.rows)
    def query_HeadSite(self, i): return int(self.rows[i].Site)
    def query_TestNumber(self, i): return self.num
    def query_TestText(self, i): return f"{self.core}:{self.pins[0]}" if len(self.pins) == 1 else self.core
    def query_Results(self, i): return [float(self.rows[i][c]) for c in self.cols]
    def query_PinResults(self, i): return list(range(len(self.pins)))
    def query_PinName(self, pid): return self.pins[pid]


class TC:
    testerId = "testerA"


class FakeActionManager:
    log = []
    @classmethod
    def set_wait(cls, tid, wait, msg): cls.log.append(("set_wait", msg))
    @classmethod
    def set_message(cls, tid, msg): cls.log.append(("set_message", msg))
    @classmethod
    def get(cls, tid): return "ok"


def run_wafer(w, data_dir, out_dir, model_dir="models"):
    path = os.path.join(data_dir, f"A12345_W{w:02d}_RawResult.csv")
    df, _ = load_csv(path)
    df = df.sort_values("PID").reset_index(drop=True)
    test_cols = [c for c in df.columns if c not in META]
    groups = {}
    for c in test_cols:
        n, core, pin = _split_name(c)
        groups.setdefault((n, core), []).append((pin, c))
    sensor_first = {c: i + 1 for i, c in enumerate([c for c in test_cols if "sensor" in c])}

    snap_dir = os.path.join(out_dir, "snapshots"); os.makedirs(snap_dir, exist_ok=True)
    s2 = Scene2(model_dir=model_dir, report_dir=out_dir)
    tc = TC(); FakeActionManager.log.clear()
    wid = f"W{w:02d}"
    s2.on_data(tc, WaferStart(wid), DT, FakeActionManager)
    for start in range(0, len(df), 4):
        rows = [df.iloc[i] for i in range(start, min(start + 4, len(df)))]
        s2.on_data(tc, TestStart(rows), DT, FakeActionManager)
        for (n, core), pl in groups.items():
            first = pl[0][1]
            if first in sensor_first:
                s2.on_predict(tc, sensor_first[first], FakeActionManager)
            s2.on_data(tc, MultiParam(n, core, [p for p, _ in pl], rows, [c for _, c in pl]), DT, FakeActionManager)
        s2.on_data(tc, TestEnd(rows), DT, FakeActionManager)
        td = s2.wm.touchdowns
        shutil.copy(os.path.join(out_dir, f"wafer_{wid}.json"), os.path.join(snap_dir, f"{wid}_td{td:02d}.json"))
    s2.on_data(tc, WaferEnd(), DT, FakeActionManager)
    return s2, [m for k, m in FakeActionManager.log if k == "set_message"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--wafer", default="2,10", help="逗號分隔")
    ap.add_argument("--out", default="report_demo")
    args = ap.parse_args()
    for w in [int(x) for x in args.wafer.split(",")]:
        s2, alerts = run_wafer(w, args.data, args.out)
        st = s2.wm.state()
        s4 = st["sensors"]["4"]
        fm = lambda v, fmt: ("—" if v is None else format(v, fmt))
        print(f"W{w:02d}: {st['devices_done']} 顆 / {st['touchdowns_done']} touchdown | sensor4 實際平均 {fm(s4['mean_actual'], '.3f')} "
              f"預測平均 {fm(s4['mean_pred'], '.3f')} MAE {fm(s4.get('mae'), '.3f')}（校正前 {fm(s4.get('mae_raw'), '.3f')}） "
              f"z={fm(s4['z'], '+.1f')} 預估超限 {fm(s4['over_limit_rate_est'], '.0%')} 實際超限 {s4['n_over_limit_actual']}/{st['devices_done']} | 警告 {len(alerts)} 則")
        for a in st["alerts"]:
            print(f"   touchdown {a['touchdown']} sensor{a['sensor']}: {a['message']}")
    print("輸出目錄:", args.out)


if __name__ == "__main__":
    main()
