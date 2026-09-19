# ACS RTDI 黑客松競賽 — 專案參考文件

> 這份文件給 Claude Code 參考，包含競賽目標、系統架構、資料分析發現、以及開發時絕對不能違反的限制條件。開始寫程式前請先完整讀過。

---

## 1. 競賽目標

利用 Advantest **ACS RTDI (Real-Time Data Infrastructure)**，開發能協助使用者即時監測半導體測試量產的系統，用 AI/ML 發現問題或預測 IC 效能，部署到模擬產線上即時監控。

**兩個場景：**

- **場景一（異常偵測）**：模擬量產情境下，即時偵測異常，整理成報告後通知特定人員或供查詢。
- **場景二（溫度預測）**：模擬量產情境下，預測 IC 的溫度，並將結果通知機台的軟體。

**評分標準：**

| 項目 | 配分 |
|---|---|
| 符合場景需求 | 10% |
| 作品可以順利在 ACS Gemini 運行 | 25% |
| 正確的時機偵測問題或是預測結果 | 25% |
| 資料分析方法（創新） | 15% |
| **異常報告的呈現是否有新穎（創新）** | **25%（單項最高）** |

---

## 2. 系統架構（ACS RTDI）

```
Host Controller                         Edge Server
┌─────────────────┐                   ┌──────────────────────┐
│ SmarTest         │◄──── Nexus ──────►│ App（用 OneAPI 開發）  │
│ (跑測試程式)      │   (居中橋接)       │ 跑在 Docker Container  │
└─────────────────┘                   └──────────────────────┘
        ▲
        │
┌─────────────────┐
│ V93000 Tester    │
└─────────────────┘
```

- **Host Controller**：實體跑 SmarTest 的地方，也裝了 ACS Nexus。
- **ACS Nexus**：中樞，負責把 SmarTest 的即時事件轉發給 Edge Server 上的 App；也負責把 App 下的控制指令轉回 SmarTest。
- **ACS Edge Server**：跑你開發的 App（Docker container），x86 + 選配 GPU。
- **AUS (Application Update Server)**：測試區中央伺服器，App 打包成 image 後 push 到這裡，Edge Server 再從這裡 pull。
- **OneAPI**：App 跟 Nexus 溝通的標準 SDK（C++/Python），核心 class 是 `Interface`（建立連線）與 `Monitor`（實作你的邏輯）。

**資料流（場景一：被動監聽型）：**
```
SmarTest → Nexus → App.consumeData(tc, data) 被觸發
→ 分析資料 → 若異常 → ActionManager.set_message(testerId, msg) → 送回 Nexus → SmarTest
```

**資料流（場景二：主動問答型，見第 5 節，跟場景一機制不同！）：**
```
SmarTest 執行到 receive_temp_predictN → 透過 consumeTPRequest 主動發送 {"key":"predict","data":N}
→ App 用目前已累積的資料做推論 → ActionManager.set_wait() + ActionManager.get() 回傳預測值 → SmarTest 繼續往下跑
```

---

## 3. 開發 / 部署完整流程

1. **登入 ACS Gemini**（VM 沙盒環境），啟動 Edge Server VM 和 Host Controller VM（兩台要各自手動 Start）。
2. **進入 Host Controller VM**（VNC），在裡面連開發環境：
   - 瀏覽器：`http://advantestcell.local:29080`，密碼 `1qaz2wsx`
   - SSH：`ssh -p 29022 debugger@advantestcell.local`
   - 開發環境是 Edge Server 上的一個 docker container，Python 3.10，程式碼存在持久化的 `/home/debugger/project`
3. **寫 App**：主要邏輯在 `sample.py` 的 `consumeData()`（場景一）以及 `consumeTPRequest()`（場景二，處理 predict 請求）。
4. **本機驗證**：`python3 main.py` 直接跑，觀察 log。
5. **回 Host Controller 端跑 SmarTest 驗證**（`Case_Event/SmarTest/` 目錄下）：
   ```bash
   ./runTp.sh load        # 第一次要先 load 測試程式
   ./runTp.sh eng_run 2   # 手動跑 N 次，方便 debug
   ./runTp.sh prod_run    # 跑生產模擬（正式評分用這個）
   ```
6. **打包 Docker Image**（`py-app.dockerfile` 定義），推送到 AUS：
   ```bash
   sudo ./tag.sh
   ```
7. **模擬正式產線**：`./runTp.sh prod_run` 會讓 Edge Server 從 AUS pull image、啟動 container，開始等待即時事件。用 ACS Nexus GUI 觀察 Session/Edge/Datalog 狀態確認真的跑起來了。

---

## 4. 資料集分析發現（重要！）

### 4.1 資料規模
- 25 片 wafer 作為 training data，每片 80 顆 device，每顆約 3000 個測試項目。
- 每片 wafer 有兩種格式：`.csv`（已攤平的寬表格）與 `.stdf`（原始二進位格式，業界標準）。
- CSV 是 STDF 攤平轉出來的，兩者數值完全一致；CSV 欄位命名規則：`<test number>_<test suite name>#<pin name>`。

### 4.2 ⚠️ CSV 表頭陷阱：High Limit / Low Limit 標反了！
比對 STDF 原始的 `LO_LIMIT` / `HI_LIMIT` 欄位後發現，**CSV 表頭的「High Limit」實際上是 STDF 的 LO_LIMIT，CSV 的「Low Limit」實際上是 STDF 的 HI_LIMIT**。

範例（sensor 類測項）：
- CSV 表頭寫：High Limit = 0, Low Limit = 35
- STDF 真實值：LO_LIMIT = 0, **HI_LIMIT = 35**（也就是溫度上限是 35°C）

**寫程式判斷是否超標時，務必用 STDF 的真實限值方向，不要照 CSV 表頭字面意思。**

### 4.3 溫度感測器目標測項（場景二要預測的東西）
| Test Number | 欄位名稱 |
|---|---|
| 100 | `Main.sensor1_CP` |
| 120 | `Main.sensor2_DS0` |
| 140 | `Main.sensor3_IO4` |
| 160 | `Main.sensor4_IO1` |
| 180 | `Main.sensor5_IO2` |
| 200 | `Main.sensor6_IO3` |

正常值範圍約 25~30°C，規格上限（HI_LIMIT）為 35°C。

### 4.4 Wafer 級異常狀態表（場景一的 ground truth，非常重要）
25 片 wafer 各自被標記了狀態，這才是場景一真正要偵測的目標分類，**不是個別晶片的 SBin/HBin pass/fail**：

| 狀態類型 | 範例 wafer |
|---|---|
| Normal | 多數 |
| Site unbalance | W1 |
| Low yield（良率 < 80%） | W3, W9 |
| Mean Trend Up | W14 |
| Mean Trend Down | W18 |
| Stdev Trend Up | W23 |
| Stdev Trend Down | W25 |

> ⚠️ 已知盲點：初步檢查 W1（Site unbalance）的 6 個溫度感測器欄位，發現各 Site 平均值/標準差其實很接近，代表這個異常特徵**很可能藏在其他上千個測項欄位裡，不是溫度感測器欄位本身**。需要系統性掃描全部 ~3000 欄，找出哪些測項在哪些 wafer 上出現 site 間差異 / 趨勢異常 / 標準差異常，才能建立可靠的異常分類模型。

### 4.5 個別晶片層級的兩種 fail pattern（已知現象，但非 4.4 的 wafer 級異常目標）
在 W01 資料中觀察到的、屬於一般良率 fail 的兩種模式（可作為輔助特徵，但不是主要偵測目標）：
- **模式 A（SBin=6, HBin=6）**：`subflow1.Flow1_SuiteXXX#CP` 類欄位同時有 4~5 個測項嚴重超標（正常值約 1.0~1.2V，故障時飄到 5~8V，遠超規格上限 2.3V）。
- **模式 B（SBin=3, HBin=3）**：只有 `sensor4`（IO1腳位）超過上限 35.0，數值落在 35.001~35.119，屬於臨界值飄移。

---

## 5. ⚠️⚠️ 開發時絕對不能違反的限制（來自官方題目 PPT）

### 5.1 測試流程與資料時序（Data Leakage 風險，直接影響評分 25%）

官方流程圖：
```
Suite1~Suite14 → IDDQ_flow → [receive_temp_predict1] → sensor1 →
subflow1 → [receive_temp_predict2] → sensor2 →
subflow2 → [receive_temp_predict3] → sensor3 →
subflow3 → [receive_temp_predict4] → sensor4 →
subflow4 → [receive_temp_predict5] → sensor5 →
subflow5 → [receive_temp_predict6] → sensor6 →
subflow6 → 結束
```

**鐵律：訓練預測 sensorN 的模型時，絕對不能使用「還沒執行到的測試項」的結果。**

例如：訓練預測 sensor1 的模型，**只能用 Suite1~Suite14、IDDQ_flow 的結果**，不能用 subflow1 之後（包括 sensor1 自己的真實值、subflow1、sensor2...）的任何資料。

完整的 feature 使用邊界：

| 要預測 | 這個時間點能用的 feature |
|---|---|
| sensor1 | Suite1~Suite14、IDDQ_flow |
| sensor2 | 上面 + sensor1 真實值 + subflow1 結果 |
| sensor3 | 上面 + sensor2 真實值 + subflow2 結果 |
| sensor4 | 上面 + sensor3 真實值 + subflow3 結果 |
| sensor5 | 上面 + sensor4 真實值 + subflow4 結果 |
| sensor6 | 上面 + sensor5 真實值 + subflow5 結果 |

**這代表要訓練 6 個獨立的階段性模型（不是一個模型），每個模型的 feature set 嚴格遞增。違反這條規則，離線驗證準確率會虛高，但正式在 Gemini 上跑一定會失準，因為 production 當下那些「未來」資料根本還沒產生。**

### 5.2 場景二的通訊機制是「請求-回應」，不是被動 consumeData！

這點跟一般 OneAPI 教學（被動等 `consumeData` 觸發）不同。SmarTest 執行到 `receive_temp_predictN` 節點時，會透過 `consumeTPRequest` **主動發送請求**問你現在要預測第幾個 sensor，你必須**即時回應預測值**，測試程式才會繼續往下跑。

官方提供的 container 端範例邏輯：
```python
elif key == "predict":
    wait = 10
    predict_num = data   # 1~6，代表現在要預測 sensor幾
    # trigger to run prediction based on predict_num and get results of all sites
    message = f"prediction {predict_num}: "
    for site in self.sites:
        value = 25.22   # ← 這裡要換成你訓練好的第 predict_num 階段模型的推論結果
        message += f'{site},{value}  '
    ActionManager.set_wait(tc.testerId, wait, message)
    response = ActionManager.get(tc.testerId)
```

**你的 App 架構需要：**
1. 一個 per-site 的 buffer，在 `consumeData()` 裡持續累積每個 site 目前已經跑完的測項結果。
2. 用 `consumeTPRequest()` 監聽測試程式送來的 `{"key": "predict", "data": <1~6>}` 請求。
3. 收到請求後，依 `predict_num` 選對應階段模型，用**目前 buffer 裡已有的資料**做推論（絕不可能有還沒發生的資料）。
4. 組出每個 site 的預測值訊息，透過 `ActionManager.set_wait()` + `ActionManager.get()` 回傳。
5. 注意有 `wait` 時間限制（範例是 10 秒），推論速度要夠快，不能拖太久。

### 5.3 場景一的通知機制

偵測到異常後，用以下 API 把訊息送回機台端：
```python
ActionManager.set_message(tc.testerId, "你的異常報告內容")
```
- 第一個參數：機台名稱，從 `tc.testerId`（每個 OneAPI event 裡的 `TestCell` 物件）取得。
- 這是「規定要做」的最低要求；「異常報告的呈現是否新穎」佔 25% 單項最高分，建議在這之外**額外**做更完整的呈現方式（例如即時 dashboard、email/Slack 通知、可查詢的報告介面）來拉開差距。

---

## 6. OneAPI 關鍵 API 速查

**`Interface`（靜態函式，負責連線）**
```python
Interface.connect(me: AppInfo, cmdPort: int = 0, dataPort: int = 0) -> int
Interface.disconnect() -> int
Interface.registerMonitor(myMonitor: Monitor) -> None
Interface.getConnectionState(cmdChannel: int) -> None
Interface.sendCommand(tc: TestCell, cmd: Command) -> int
```

**`Monitor`（你要實作的邏輯）**
```python
def consumeData(tc: TestCell, data: NexusData) -> None       # 場景一：被動接收即時測試資料
def consumeTPSend(tc: TestCell, data: str) -> None            # 測試程式主動送訊息
def consumeTPRequest(tc: TestCell, request: str) -> str       # 場景二：測試程式問你要答的請求
```

**`DataType`（`consumeData` 收到的 `data.getType()` 可能值）**
```
PRODUCTION_LOTSTART / PRODUCTION_LOTEND
PRODUCTION_WAFERSTART / PRODUCTION_WAFEREND
PRODUCTION_TESTSTART / PRODUCTION_TESTEND      ← 含 SBin/HBin/X/Y/Test Time
PRODUCTION_TESTFLOWSTART / PRODUCTION_TESTFLOWEND
PRODUCTION_TESTSUITESTART / PRODUCTION_TESTSUITEEND
MEASURED_PARAMETRIC        ← 單一參數量測
MEASURED_FUNCTIONAL        ← 功能測試 pass/fail
MEASURED_MULTI_PARAM       ← 多 pin 參數量測（sensor 溫度資料走這個）
MEASURED_SCAN
DEVICE
USERDEFINED
DATALOGTEXT
```

**`ActionManager`（下動作 / 回應 / 通知）**
```python
ActionManager.set_message(testerId, message)          # 場景一：發異常訊息給機台
ActionManager.set_wait(testerId, wait_seconds, message)  # 場景二：設定等待+要回傳的訊息
ActionManager.get(testerId)                             # 取得目前的動作/組出回應
```

其他控制型態（`settest`, `setpat`, `setprogvar`, `setrestore`, `set_pause` 等）用於場景一進階互動，詳見 ONEAPI 手冊 1.1.2 節「Tester control instruction」表格。

**環境變數**
```
ONEAPI_DEBUG = 6   # 0~6，數字越大 log 越詳細，6 = console+file 都輸出 DEBUG level
```
本機 log 路徑固定在 `${home}/.log/ACS_ONEAPI_yyyy-mm-dd.log`

---

## 7. STDF ↔ OneAPI 事件對應表

| STDF Record | 對應 OneAPI DataType |
|---|---|
| WIR | `PRODUCTION_WAFERSTART` |
| WRR | `PRODUCTION_WAFEREND` |
| PIR | `PRODUCTION_TESTSTART` |
| PRR | `PRODUCTION_TESTEND` |
| PTR | `MEASURED_PARAMETRIC` |
| MPR | `MEASURED_MULTI_PARAM` |
| FTR | `MEASURED_FUNCTIONAL` |

用途：訓練資料的 STDF 檔可以用來模擬/回放（STDF replay）成即時事件序列，在本機或開發環境先驗證 `consumeData()` / buffer 邏輯正不正確，不用每次都要進 Gemini VM 才能測試。

---

## 8. 待辦事項（優先順序）

1. [x] 系統性掃描全部 25 片 wafer 的 ~3000 個測項欄位，找出「Site unbalance / Low yield / Mean Trend Up-Down / Stdev Trend Up-Down」這幾種 wafer 級異常各自對應到哪些欄位的統計特徵，建立分類模型的 feature set。
   → `src/eda_scan.py`（用 site_unbalance / mean_trend / stdev_trend / oos_rate 四個統計量，對每個已知異常 wafer 算 z-score，找出最相關測項）。結果：`reports/eda_scan_top_columns.txt`（人類可讀）+ `reports/anomaly_detector_config.json`（app 用的機器可讀版本，含 baseline mu/sigma/方向/規格上下限）。
2. [x] 依照第 5.1 節的時序限制，把 25 片 wafer 的資料切分成 6 組 feature set（sensor1~sensor6 各一組），分別訓練 6 個階段性溫度預測模型。
   → `src/train_sensor_models.py`（用 CSV 欄位「實際出現順序」= SmarTest 執行順序，在 sensorK 欄位位置切 feature set，嚴格避免 data leakage；GroupKFold by wafer 驗證）。CV MAE 全部在 0.02~0.03°C，超標判斷一致率 97.9~100%。模型存在 `models/sensor{1..6}_model.joblib`，指標見 `reports/sensor_model_metrics.csv`。
3. [x] 實作 `consumeData()`：累積 per-site buffer + 呼叫場景一異常分類模型 + `ActionManager.set_message()`。
   → `app/sample.py` + `app/anomaly_detector.py`（線上重算跟訓練時同一套統計量，跟 baseline 比 z-score，觸發時存 HTML 報告並呼叫 `ActionManager.set_message()`）。
4. [x] 實作 `consumeTPRequest()`：解析 `{"key":"predict","data":N}`、呼叫對應階段模型、`ActionManager.set_wait()` + `ActionManager.get()` 回傳。
   → `app/sample.py` + `app/sensor_predictor.py`。
5. [x] 設計異常報告呈現方式（這是創新分數最高的單項，25%）—— 建議做即時 dashboard 或查詢介面，不要只送純文字訊息。
   → `app/report_generator.py`：自包含 HTML（inline SVG，不依賴任何 CDN，適合 airgapped Gemini VM）— wafer map、關鍵測項 |z| 排行長條圖、趨勢線、詳細數據表，每次異常都存檔到 `reports/live/`，並自動維護 `reports/live/index.html` 當查詢介面。
6. [~] 本機（或用 STDF replay）驗證邏輯 → 打包 Docker image → push AUS → Gemini 上 `prod_run` 實際跑通。
   → 本機驗證：`app/replay.py` 把 25 片 wafer CSV 攤成即時事件序列跑過 `SampleMonitor`（不用進 Gemini VM）。**Docker 打包 / push AUS / Gemini `prod_run` 這幾步一定要在真正的 Host Controller / Edge Server VM 上做**，本機沒有 `py-app.dockerfile`、`tag.sh`、`runTp.sh`、也沒有真正的 OneAPI SDK，這部分無法在本機完成或驗證。
   ⚠️ 上機第一件事：對照官方 ONEAPI 手冊確認 `NexusData` 真正的 getter 方法名稱（test number / pin / site / value 怎麼拿），目前 `app/oneapi_mock.py` 只是依 PROJECT_CONTEXT.md 第 6 節的 API 速查表做的最佳猜測，`import oneapi` 的實際套件路徑也要在上機時確認。

