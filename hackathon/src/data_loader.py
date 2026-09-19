"""
資料載入工具 — ACS RTDI 黑客松

CSV 格式（每片 wafer 一個檔案）：
  row1 (header)   : 欄位名稱  <test number>_<test suite name>#<pin name>
  row2            : Pin
  row3            : Test Num
  row4            : "High Limit"  <-- 陷阱！這其實是 STDF 的 LO_LIMIT（下限）
  row5            : "Low Limit"   <-- 陷阱！這其實是 STDF 的 HI_LIMIT（上限）
  row6...         : 實際量測資料

前 10 欄是 meta 欄位：PID, Lot, Wafer, Site, X, Y, PF, SBin, HBin, Test Time
其餘每一欄是一個測項。

本模組統一處理「表頭陷阱」，對外一律提供「真實物理意義」的 lo_limit / hi_limit，
呼叫端不需要再自己記標籤反過來這件事。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

META_COLS = ["PID", "Lot", "Wafer", "Site", "X", "Y", "PF", "SBin", "HBin", "Test Time"]

# 場景二要預測的 6 個溫度感測器測項（依官方流程順序 sensor1..sensor6）
# test number 固定為 100/120/140/160/180/200，欄位名稱格式為 <num>_Main.sensorN#<pin>
SENSOR_TEST_NUMS = {1: 100, 2: 120, 3: 140, 4: 160, 5: 180, 6: 200}
SENSOR_HI_LIMIT_C = 35.0  # 規格上限（STDF 真實 HI_LIMIT），CSV 表頭寫成 "Low Limit" 是陷阱


def find_sensor_col(wd: "WaferData", k: int) -> str:
    """回傳 wafer 資料中 sensorK 對應的欄位名稱（依 test number 精確比對）。"""
    target = SENSOR_TEST_NUMS[k]
    for col, tn in wd.test_num.items():
        if tn == target and f"sensor{k}" in col:
            return col
    # fallback：只用 test number 比對
    for col, tn in wd.test_num.items():
        if tn == target:
            return col
    raise KeyError(f"sensor{k} column not found (test num {target})")

WAFER_STATUS = {
    1: "Site unbalance",
    2: "Normal",
    3: "Low yield",
    4: "Normal",
    5: "Normal",
    6: "Normal",
    7: "Normal",
    8: "Normal",
    9: "Low yield",
    10: "Normal",
    11: "Normal",
    12: "Normal",
    13: "Normal",
    14: "Mean Trend Up",
    15: "Normal",
    16: "Normal",
    17: "Normal",
    18: "Mean Trend Down",
    19: "Normal",
    20: "Normal",
    21: "Normal",
    22: "Normal",
    23: "Stdev Trend Up",
    24: "Normal",
    25: "Stdev Trend Down",
}


@dataclass
class WaferData:
    wafer_id: int
    status: str
    df: pd.DataFrame  # data rows, meta cols + test cols, numeric
    test_num: dict  # colname -> test number (int or None)
    pin: dict  # colname -> pin name
    lo_limit: dict  # colname -> REAL physical lower limit (float or NaN)
    hi_limit: dict  # colname -> REAL physical upper limit (float or NaN)

    @property
    def test_cols(self) -> list[str]:
        return [c for c in self.df.columns if c not in META_COLS]

    @property
    def canonical_map(self) -> dict[str, str]:
        """欄位原始名稱 -> canonical key ("<test_num>#<pin>")。

        用 test_num + pin 當 key，而不是原始 CSV 欄位全名，是因為 App 在 runtime
        從 OneAPI NexusData 收到的事件只會帶 test number 跟 pin name，不一定會有
        「suite 名稱」這種展示用字串。用這個 key 才能讓「訓練時的 feature 欄位」
        跟「on-line 收到的即時資料」對得起來。
        （這個 CSV schema 裡幾乎每個 test_num 都是唯一的，唯一例外是 560 號
        測項同時有 #CP 和 #MR 兩個 pin，用 test_num+pin 就能正確區分。）
        """
        out = {}
        for col in self.test_cols:
            tn = self.test_num.get(col)
            pin = self.pin.get(col)
            out[col] = f"{tn}#{pin}"
        return out

    def df_canonical(self) -> pd.DataFrame:
        """回傳測項欄位已改名成 canonical key 的 DataFrame（meta 欄位名稱不變）。"""
        return self.df.rename(columns=self.canonical_map)


def _wafer_id_from_filename(path: Path) -> int:
    m = re.search(r"_W(\d+)_RawResult", path.name)
    if not m:
        raise ValueError(f"cannot parse wafer id from {path.name}")
    return int(m.group(1))


def load_wafer_csv(path: str | Path) -> WaferData:
    """讀取單片 wafer 的 RawResult.csv，回傳整理好的 WaferData。"""
    path = Path(path)
    raw = pd.read_csv(path, header=0, low_memory=False)

    pin_row = raw.iloc[0]
    testnum_row = raw.iloc[1]
    label_high_row = raw.iloc[2]  # CSV 稱 "High Limit"，實為 STDF LO_LIMIT
    label_low_row = raw.iloc[3]  # CSV 稱 "Low Limit"，實為 STDF HI_LIMIT

    data = raw.iloc[4:].reset_index(drop=True).copy()

    test_num, pin, lo_limit, hi_limit = {}, {}, {}, {}
    for col in raw.columns:
        if col in META_COLS:
            continue
        pin[col] = pin_row[col]
        tn = pd.to_numeric(testnum_row[col], errors="coerce")
        test_num[col] = None if pd.isna(tn) else int(tn)
        # 表頭陷阱修正：CSV "High Limit" 欄實際是真實下限，CSV "Low Limit" 欄實際是真實上限
        lo_limit[col] = pd.to_numeric(label_high_row[col], errors="coerce")
        hi_limit[col] = pd.to_numeric(label_low_row[col], errors="coerce")

    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    wafer_id = int(data["Wafer"].iloc[0]) if "Wafer" in data.columns else _wafer_id_from_filename(path)
    status = WAFER_STATUS.get(wafer_id, "Unknown")

    return WaferData(
        wafer_id=wafer_id,
        status=status,
        df=data,
        test_num=test_num,
        pin=pin,
        lo_limit=lo_limit,
        hi_limit=hi_limit,
    )


def load_all_wafers(data_dir: str | Path = DATA_DIR) -> list[WaferData]:
    data_dir = Path(data_dir)
    files = sorted(data_dir.glob("*_RawResult.csv"), key=lambda p: _wafer_id_from_filename(p))
    return [load_wafer_csv(f) for f in files]


if __name__ == "__main__":
    wd = load_wafer_csv(DATA_DIR / "A12345_W01_RawResult.csv")
    print("wafer", wd.wafer_id, "status", wd.status, "rows", len(wd.df), "test cols", len(wd.test_cols))
    print("sample limits (sensor1):", wd.lo_limit.get("100_Main.sensor1#CP"), wd.hi_limit.get("100_Main.sensor1#CP"))
