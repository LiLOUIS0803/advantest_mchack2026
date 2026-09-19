> Deployment update: Scene 1 and Scene 2 have independent pages and results. Edge sends JSON to the HC receiver; HC serves `/anomaly` and `/temperature`. See [HC deployment instructions](../deploy/HC_EDGE_TASKS.md). The local replay commands below remain available for development.

# 即時異常模型與報表

目前主分類為七類 Logistic Regression，Site unbalance 已啟用、W2 排除。原本的 12 片正常統計模型仍供測項曲線及輔助證據使用。以下歷史實驗與統計界線不等於主分類決策。

## 執行

目前服務已啟用 `ClassifierEngine`：使用 `artifacts/wafer_classifier/model.joblib`，先安裝 `realtime/requirements-ml.txt`。
主畫面只顯示一個官方 wafer label；未完成 16 顆、缺測項或缺 Site 時為「判定中」。每批 TestEnd 才更新分類，PF／Fail 仍是獨立實際結果。
Site unbalance 已啟用；W2 排除。舊模型只提供曲線與診斷證據，不決定主 label。
執行 `python -m realtime.check_classifier_stream` 可驗證逐事件路徑，輸出 `reports/wafer_classifier/stream_check.json`。
全部 24 片參與訓練，此重播是樣本內检查，不是泛化準確率；五類只有一片，早期預測仍可能變動。

Wafer 單一分類器：安裝 ML 依賴後執行 `python -m realtime.wafer_classifier`。
啟用 Site 特徵並排除 W2；比較正則化 Logistic Regression、淺層 Random Forest、Extra Trees。
使用官方 label，按 wafer 留一驗證；結果在 [分類器比較](../reports/wafer_classifier/README.md)。
此實驗最終以所有 24 片訓練，因此原 validation 不再是它的獨立測試集；五個單例異常類別缺少泛化證據。
最終模型 `artifacts/wafer_classifier/model.joblib` 已接到服務；中途輸出為暫定預測，不是已驗證的即時分類。

### 前後端分離（建議）

分別在兩個終端啟動：

```powershell
python -m realtime.server --port 8771 --api-only
python -m realtime.frontend --port 8770 --backend http://127.0.0.1:8771
```

開啟 http://127.0.0.1:8770 。前端在 `realtime/web/`：HTML 結構、`dashboard.css` 樣式、`api.js` JSON 客戶端、`app.js` 狀態呈現，其他 JS 管理圖表與由粗到細的互動。
前端服務只提供靜態檔並轉送 `/api/*`，不載入模型或 CSV；後端 `--api-only` 只回 JSON，處理重播、測試事件與模型推論。
目前後端採七類分類器；舊統計模型的診斷事件不再作為 wafer 類別。

JSON 契約見 [API.md](API.md)。首頁依序為整片概況、空間／批次趨勢、Fail／告警紀錄；點選後展開單顆與測項證據。模型參數與限制收在說明區。

W25 漏報分析：`python -m realtime.variance_audit`；候選改善：
`python -m realtime.residual_experiment`，前提是已有時序 PCA 模型。
候選保留主成分訊號並加入群體重建殘差變異下降，正常資料校準門檻；
見 [候選報告](../reports/residual_experiment/README.md) 與同目錄 `report.html`。
分支是分析 W25 後選擇的，仍需新資料驗證；沒有把殘差下降直接當成官方 Stdev Down 類型。

後續 ML 比較：`python -m realtime.ml_comparison`（先執行下面的 PCA 基準）。
以同一 8/4 正常 wafer 切分，比較前後視窗的 PCA 與小型 Autoencoder；
結果在 [ML 比較](../reports/ml_comparison/README.md)，同目錄附兩份可播放 HTML。
修改規則受到先前驗證誤報分析啟發，因此仍屬開發驗證，不是獨立測試。

ML 實驗：安裝 `pip install -r realtime/requirements-ml.txt` 後執行
`python -m realtime.pca_experiment`。12 片正常訓練資料內再分 8 片 PCA 擬合、4 片門檻校準，W2 排除。
結果：[PCA 評估](../reports/pca_experiment/README.md)；可直接在瀏覽器開啟
`reports/pca_experiment/report.html` 播放階段分數、可疑 PID／測項與 wafer 圖。
不使用逐 die 偽標籤，不輸出已確認根因或異常類型，不更換現有服務模型。

同切分模型實驗：執行 `python -m realtime.compare_models`，結果在
[模型比較報告](../reports/model_comparison/README.md)。比較現有模型、排除 Site 的 hackathon die 元件，以及保留現有低良率／標準差下降判定的混合版。
此命令只用既有 train_normal 重建 die 基準，不讀 hackathon 原本的已訓練模型，不切換目前服務模型。

在專案根目錄執行（Python 3.10+、NumPy）：

```powershell
python -m realtime.train
python -m realtime.evaluate
python -m unittest discover -s tests -v
python -m realtime.server --port 8765
```

開啟 http://127.0.0.1:8765 。選 wafer 開始重播，可暫停、繼續、選取異常事件查看證據及下載 JSON。報表同時顯示開發驗證結果。伺服器只綁定本機；只支援單一 wafer 資料流，實際多機台需各自隔離 Engine 狀態。

## Wafer 與測項圖表

- 實際結果區顯示已完成 Pass／Fail 數、最近完成批次 Fail、目前良率、Fail 累積曲線與每批失敗比例；均只在 TestEnd 更新，不預測 PF。
- Fail 明細保留 PID、座標、PF、SBin／HBin，點選可定位同一張 wafer 圖。模型預警使用外框，不改變實際結果底色。
- CSV 沒有逐測項 Fail 旗標，模型偏離測項不可當成已確認失敗測項；即時輸入可缺省 pf/sbin/hbin，未知時顯示「—」。

- Wafer 圖依已收到的 X/Y 繪製，Pass／Fail 色彩與橙色單顆預警外框分開；紫點只表示選定事件的相關視窗。
- 點選晶粒可定位 PID；若有單顆偏離測項，優先顯示其中一項。點選事件或證據表測項也會切換曲線。
- 可搜尋全部測項；尚未收到的測項不畫數值。Wafer 圖也可切到所選測項的數值色階。
- 原始數值圖顯示正常模型上下界；平均值差及標準差比值圖使用與偵測器相同的 16 顆視窗、每 4 顆更新一次。
- CSV 座標保守地到 TestEnd 才揭露；即時事件可在 TestStart 或 TestEnd 提供 `x`／`y`。無效座標 -32768 不繪製。圓形輪廓僅示意，沒有真實 wafer 尺寸或 notch 方位。
- `/api/state?test=0` 在同一狀態快照中提供所選測項曲線；`/api/tests` 提供模型測項名稱。僅保存當片已收到的歷史，切換 wafer 時清除。

## 模型

- `artifacts/normal_model.npz`：正常平均值、片內樣本標準差尺度、正常數值與變化界線。
- `artifacts/model_info.json`：訓練 wafer、來源 SHA256、參數與限制。
- 單顆值超出訓練包絡：device 層級預警。正常 wafer 也有失敗 device，因此此預警不直接標記整片異常。
- 同測項收滿 16 筆，每新增 4 筆評估一次；比較前後 8 筆算術平均值，至少 5 個測項連續兩個視窗超界才發正式事件；返回首 8 筆基準的方向不視為新趨勢。
- 標準差使用 ddof=1，計算後 8 筆／前 8 筆比值。需偏離首 8 筆標準差基準且平均值沒有同時跨界，降低恢復與平均值漂移的混淆。這些規則仍可能漏報或多報。
- 低良率用已完成 device，至少 16 顆且單側 95% Wilson 上界低於 80%。此區間未校正重複序列檢定，不是整個串流的 5% 誤報保證。
- 信心等級由樣本數及出現證據的批次数決定，不是機率；多批證據不一定連續。
- 事件依種類合併，保留首次時點與每次證據；報表狀態為「本片曾有異常」，不宣稱事件已恢復。
- 驗證檔為開發資料，非獨立測試。`reports/evaluation.json` 比較原始 label 與全部正式預測集合，記錄完全符合、漏報、額外標籤及各類 precision/recall；包含正確類型但多報不算完全正確。單顆預警不列為正式類別。W1 僅探索，PID 沒有 ground truth。

## 因果與重播限制

CSV 每四列模擬一個多 Site 批次，依序揭露前段／IDDQ，再 sensor1+subflow1，直到 sensor6+subflow6；最後才提供 PF 與 PID。這是確定性的離線假設，尚未由現場事件驗證。重播器雖持有完整檔案，Engine 只收到當步已揭露資料，沒有標籤或未來值。

同一測項只接受每 device 一次結果；遇到重複、未知欄位、不完整批次會報錯，不會默默重複計數。Retest 尚未支援。真實回傳的單位、Scaling、PartFlag 有效位元需在 adapter 正確處理，不可直接套 CSV 的 `PF==0` 規則。

## 即時輸入介面

`POST /api/events` 接受已正規化事件，直接使用與重播相同的 Engine；重播進行中拒絕混入外部事件。尚未接入實際 ONEAPI，也未部署到 ACS。

依序送以下 JSON（measurement 可多次送不同測項）：

```json
{"type":"wafer_start","wafer":"4","lot":"A12345","mode":"live","total_devices":80}
{"type":"test_start","batch":1,"devices":[{"key":"tester:4:1:1","site":1}]}
{"type":"measurement","keys":["tester:4:1:1"],"tests":["220_Main.Suite1#CP"],"values":[[1.1]],"stage":"Main.Suite1"}
{"type":"test_end","outcomes":[{"key":"tester:4:1:1","pid":"1","passed":true}]}
{"type":"wafer_end"}
```

測項名稱必須與模型完全對應。`values` 是 device × test 的矩陣。中途用機台／wafer／批次／Head／Site 對應 device，結束後補 PID；缺少 PID 不猜值。實際 adapter 需將 `consumeData` 的 Parametric/MultiParametric 事件轉換為此格式；`prod_action` 是動作讀取，不是測量值入口。解析 pin 與複合測項時不可僅靠 TestNumber，因為編號可能重複。

## 提早暫停與節省

只有建議，程式不送出機台控制。上方暫停按鈕只暫停重播。首次群體告警記錄當時尚未開始的 device 數，作為潛在可避免工作量的上限；它不含正在測試的一批，不代表實際省下這些 device。沒有停止生效時間與可靠測試耗時前，`estimated_saved_seconds` 保持 null。
# 分類信心與站內通知

分類旁顯示所選類別的 `predict_proba` 百分比；JSON 的 `classification_confidence` 包含 `score`、`calibrated: false` 與 `method`。不足 16 顆或缺少必要資料時為 null。分數尚未校準，不能視為實際正確率，也不會單憑分數控制停機。

站內通知在至少完成 24 顆、連續三次 TestEnd 分類為同一異常時建立；WaferEnd 仍為異常時也會建立。同次重播／測試、同一類別只通知一次。這是通知去重規則，並非經驗證的異常確認標準。重播與即時來源會分開標示。

通知保存在 `reports/notifications.sqlite3`，可查詢、確認看到、標記已處理，以及下載當時的 JSON 快照。快照不會隨後續分類變動；已處理也不表示模型判定恢復正常。

- `GET /api/notifications?q=...&status=...`：查詢最近 100 筆符合條件的通知與未確認總數。
- `GET /api/notifications/{id}`：取得通知、資料快照與操作紀錄。
- `POST /api/notifications/{id}`，body 為 `{"status":"acknowledged"}` 或 `{"status":"resolved"}`。

目前為本機站內通知，尚未串接 Email／通訊軟體、指定人員身份或存取權限。
