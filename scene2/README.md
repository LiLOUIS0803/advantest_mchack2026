# 場景二：溫度感測器預測（sensor1–6）

## 檔案

| 檔案 | 用途 |
|---|---|
| `temp_predictor.py` | **推論核心**，只依賴 numpy。含 `consume_nexus_data()`，直接吃 ONEAPI 的 NexusData |
| `scene2_hook.py` | **合併用膠水層**。同學的 Monitor 加兩行呼叫就接上（見下） |
| `models/temp_models.pkl` | 6 個訓練好的模型（純 numpy 權重，9 KB） |
| `train_temp_models.py` | 重新訓練 + leave-wafer-out 評估，輸出 `models/` |
| `replay_test.py` | 用 CSV 模擬串流回放，驗證整條路 |
| `test_nexus_adapter.py` | 用假的 NexusData 物件測 ONEAPI 事件解析（不用真的 oneapi 套件） |
| `models/eval_report.json` / `.png` | 評估結果 |

## 在實驗室 server 上跑

```bash
pip install numpy pandas scikit-learn matplotlib     # 訓練端才需要 sklearn；推論端只要 numpy
python train_temp_models.py --data ../data --out models/temp_models.pkl
python replay_test.py --data ../data                 # 串流回放，應與 eval_report.json 的 MAE 一致
python test_nexus_adapter.py                         # 應印出 PASS
```

## 模型設計

- **特徵**：只用流程上在該 sensor 之前的欄位：Suite1–14（18 欄，Suite13 恆為 0 已剔除）+ IDDQ_A1–A11 + 更早的 sensor 實際值。**不用 subflow 欄位**，因為場景一的異常就注入在 subflow 區塊，用了預測會被拖歪。
- **模型**：標準化 + Lasso（自動選 alpha）。2000 筆資料配 30 個特徵，線性模型已經足夠；梯度提升樹試過反而較差。
- **缺值**：用訓練集中位數補；若更早的 sensor 實際值還沒收到，用自己剛才的預測值代替。
- **多 pin 測項**：`560_Main.Suite14` 有 CP 和 MR 兩支 pin，buffer 以 (編號, pin) 當 key，不會互相覆蓋。
- **評估**（leave-wafer-out，每折留 5 片）：

| 目標 | MAE | 只猜平均值的 MAE | 主要特徵 |
|---|---|---|---|
| sensor1 | 0.003 | 0.20 | IDDQ_A1（相關 0.98） |
| sensor2 | 0.043 | 0.18 | IDDQ_A2、sensor1 |
| sensor3 | 0.021 | 0.45 | IDDQ 群 |
| sensor4 | 0.051 | 0.20 | IDDQ_A8 |
| sensor5 | 0.065 | 0.19 | Suite/IDDQ 混合 |
| sensor6 | 0.067 | 0.19 | Suite/IDDQ 混合 |

- **sensor4 貼著上限 35**（平均 34.3，W1/W2 平均 34.9）。用預測值判斷會不會超限：39 顆實際超限中命中 24–29 顆，誤報 14–18 顆。誤差 0.05 和上限的距離同量級，所以這個預警可以做，但只能當「風險提示」不能當判定。

## 和 ONEAPI 對應（依 ONEAPI User Guide 1.1.3）

| 手冊裡的東西 | 我們怎麼用 |
|---|---|
| `consumeData(tc, data)` 每個事件都會呼叫 | `Scene2.on_data(tc, data, DataType)` 丟進去，它自己挑 |
| `DATA_TYP_MEASURED_PARAMETRIC` | `query_TestNumber(i)`、`query_HeadSite(i)`、`query_Result(i)` → 存進 buffer |
| `DATA_TYP_MEASURED_MULTI_PARAM` | 同上，但值在 `query_Results(i)`（list），pin 用 `query_PinResults(i)` + `query_PinName(pid)` |
| `DATA_TYP_PRODUCTION_TESTSTART` | 記下這個 touchdown 的 site 清單 (`get_HeadSiteList()`)，清空 buffer |
| `DATA_TYP_PRODUCTION_TESTEND` | touchdown 結束，清空 buffer |
| headsite → site | 手冊說有 `toSite()`；有就用，沒有就直接當 site 號 |
| `consumeTPRequest(tc, request)` 收到 `{"key":"predict","data":k}` | `Scene2.on_predict(tc, k, ActionManager)` |
| `ActionManager.set_wait(testerId, wait, message)` + `ActionManager.get(testerId)` | `on_predict` 裡照範例呼叫，`get` 必須在 `consumeTPRequest` 內呼叫（手冊要求） |

STDF 檔顯示 3030 個測項幾乎全是 MPR（multi-param）記錄，所以 **實際上主要會走 MULTI_PARAM 那條路**。

## 合併到同學的 sample.py

```python
from scene2_hook import Scene2

class SampleMonitor(Monitor):
    def __init__(self):
        super().__init__()
        self.scene2 = Scene2(model_path="models/temp_models.pkl")

    def consumeData(self, tc, data):
        self.scene2.on_data(tc, data, DataType)          # 場景二：一行
        # ... 場景一的處理照舊 ...

    def consumeTPRequest(self, tc, request):
        jsonObj = json.loads(request)
        key, data = jsonObj.get("key"), jsonObj.get("data")
        if key == "predict":
            return self.scene2.on_predict(tc, data, ActionManager)   # 場景二：一行，取代原本的 predict 分支
        # ... 其他 key 照舊 ...
```

`on_data` / `on_predict` 內部都有 try/except，場景二出錯不會把整個 callback 弄掛；predict 失敗時退回模型的截距值（約等於平均溫度），不會回空字串。

## Docker 要注意

- Base image `unifiedserver.local/acs-app/template-data-app:v22.04` 的套件清單有 numba，所以 numpy 應該已經在裡面；推論端不需要 sklearn/pandas。
- 要 COPY 進 image 的只有：`temp_predictor.py`、`scene2_hook.py`、`models/temp_models.pkl`。放到 `bin/` 旁邊，`Scene2(model_path=...)` 的路徑用相對於 `WORKDIR /opt/nexus/OneAPI/bin` 的路徑。
- `wait=10` 照範例保留；手冊只說 set_wait 是「wait time and reason」，實際單位要在 Gemini 上試一次。

## 還要跟主辦方確認

1. 預測 sensor2 時，sensor1 的實際值來得及送到 container 嗎？來不及的話 `use_own_prediction=True`（預設）會用自己的預測值補。
2. 回傳格式的小數位數有沒有限制？目前 3 位。
3. W1/W2 的分佈和其他 23 片不同（sensor3 低 2.5 度、sensor4 貼上限），評估用的 4 片是哪一種？
4. 評估時 headsite 編號是不是就是 1–4？（影響 `toSite` 轉換）
