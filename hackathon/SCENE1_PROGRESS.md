# 場景一（異常偵測）— 目前做法與進度

> 更新時間：2026-09-19。範圍只包含場景一；場景二（溫度預測）不在本文件內。
> 背景與競賽規則請見 `PROJECT_CONTEXT.md`。

---

## 1. 目標

對每一片 wafer 做三件事，而且要精確到「哪一顆 die 有問題」：

1. **第 1 層 二元判斷**：這片 wafer 是否 abnormal。
2. **第 2 層 細分原因**：Site unbalance / Low yield / Mean Trend Up / Mean Trend Down / Stdev Trend Up / Stdev Trend Down。
3. **第 3 層 die 定位**：列出造成異常的具體 die（PID、Site、X/Y）。

所有判斷只用「已經測完的 die」的資料，每顆 die 的 TESTEND 即時更新（因果安全）。

---

## 2. 資料上的發現（設計依據）

- 每片 wafer 80 顆 die、4 個 site 輪流測（PID 1,2,3,4,1,2,3,4…），PID 順序 = 測試時間序。
- CSV 表頭的 High/Low Limit 是反的（見 `PROJECT_CONTEXT.md` 4.2），`src/data_loader.py` 已統一修正。
- 每個測項用 `test_num#pin` 當 key（App 上線時從事件拿得到的就是這兩個）。
- **die 層級的離群訊號很乾淨**（以「robust z-score 超過 5 的測項個數 k」衡量）：
  - Normal wafer 的 pass die：k ≈ 0。
  - 一般 bin-fail die：k ≈ 5（4~5 個測項爆掉，即 md 4.5 的 mode A）。
  - 異常事件中的 die：k = 10 ~ 115。
- 各異常在 die 層級的樣子：

| Wafer | 標籤 | 離群 die | 特徵 |
|---|---|---|---|
| W01 | Site unbalance | PID 8/12/16/20/24 | 全在 site 4；離群方向幾乎全負 |
| W14 | Mean Trend Up | PID 16~28（13 顆） | 四個 site 都有；方向 100% 為正；k 從 19 爬到 115 |
| W18 | Mean Trend Down | PID 16~28（13 顆） | 方向 100% 為負；k 從 11 爬到 115 |
| W23 | Stdev Trend Up | PID 20~28（9 顆） | 正負混雜（55% 正）；k 從 19 爬到 35 |
| W25 | Stdev Trend Down | **無** | 沒有任何離群 die（是變異縮小），k 最大 5 |
| W03 / W09 | Low yield | 無（只有 bin-fail die） | 靠良率損失與 subflow1 測項超標 |

- **W02 疑點**：良率 53.8%（遠低於 80%）卻標成 Normal，且有 5 個測項（含 sensor3、多個 IDDQ）在全部 80 顆 die 都超標。系統目前照標籤當 Normal。

---

## 3. 目前的做法

### 3.1 正常基準（`src/build_die_baseline.py` → `reports/die_baseline.json`）
只用標記為 Normal 的 18 片（1440 顆 die），對 3036 個測項各算 **median 與 MAD×1.4826**（MAD=0 時退回 std）。用 median/MAD 是因為 fail die 的測項會飆到 5~8V，會把平均與標準差拉歪。

### 3.2 第 1 層：二元判斷（`app/hierarchical.py`）
**die 層級**：每顆 die 算 `z = (值 − median) / scale`。

| 參數 | 值 | 意義 |
|---|---|---|
| `Z_OUT` | 5 | \|z\| 超過此值算離群測項 |
| `K_EXC` | 10 | 離群測項數 ≥ 此值 → EXCURSION（離群 die，才算異常） |
| `WAFER_WIDE_FRAC` | 0.5 | 某測項在 ≥50% 已測 die 都離群 → 視為整片 wafer 的系統性偏移，從 k 中扣除（需已測 ≥6 顆） |

- die 狀態：`EXCURSION`（k≥10）／`FAIL`（SBin≠1，一般 bin-fail，視為背景良率損失，不算異常）／`PASS`。

**wafer 層級**：離群 die ≥ `MIN_EXC_DICE`(3) 顆 → ABNORMAL；或第 3.3 節的統計偵測對「沒有離群 die 的類型」達 critical。

### 3.3 第 2 層：細分原因
**有離群 die**（規則式，不需訓練）：

| 條件 | 判定 |
|---|---|
| ≥80% 離群 die 集中在同一個 site | Site unbalance（並記下 site） |
| 跨 site，離群方向 ≥90% 為正 | Mean Trend Up |
| 跨 site，離群方向 ≥90% 為負 | Mean Trend Down |
| 跨 site，正負混雜 | Stdev Trend Up |

**沒有離群 die**（Low yield、Stdev Trend Down）→ 用 wafer 統計偵測器（`app/anomaly_detector.py`，這是唯一「從資料學」的部分）：
- 離線（`src/eda_scan.py` → `reports/anomaly_detector_config.json`）：對每片 wafer、每個測項算 4 個統計量 `site_unbalance / mean_trend / stdev_trend / oos_rate`，拿已知異常 wafer 跟 Normal 基準比 z-score，每類挑 |z| 最大的 30 個測項，記錄 baseline mu/sigma、方向、規格上下限。
- 上線：用同一套定義在已收資料上重算；該類 ≥15% 的關鍵測項 |z|≥3 且方向一致 → 觸發，≥40% 為 critical。
- 只採用 critical；測到一半要**連續兩次檢查**得到同一結論才通報（debounce）。

### 3.4 第 3 層：die 定位
- 離群類異常：列出具體 die（PID、site、X/Y、SBin、離群測項數、最離群的測項）與 PID 時間窗。
- Low yield：列出所有 bin-fail die。
- **Stdev Trend Down：無法定位到單顆 die**（沒有任何離群 die）。報告與訊息明確標示 `die_localizable=False`，不硬編 die 清單。

### 3.5 上線行為（`app/sample.py`）
- 每顆 die TESTEND 即時算 k 並判定狀態。
- 離群 die 累積到 3 顆且診斷出「新的原因」→ 即時通報一次（例：W14 在第 18 顆就通報）。
- 每 20 顆對統計類（Low yield / Stdev Down）做一次檢查，需連續兩次同結論才通報。
- WAFEREND：一定產出 HTML 報告；異常則再送一次最終結論。
- 通報方式：`ActionManager.set_message()` 送文字（原因 + 問題 die 清單 + 報告路徑），並存 HTML 報告到 `reports/live/`（含 `index.html` 查詢介面）。
- HTML 報告（`app/report_generator.py`，自包含、不依賴 CDN）：三層流程橫幅、每顆 die 離群數時間軸、wafer map（離群 die 橘色標 PID）、受影響 die 明細表。

---

## 4. 檔案清單（場景一相關）

| 檔案 | 用途 |
|---|---|
| `src/data_loader.py` | 讀 CSV、修正 limit 表頭、canonical key |
| `src/eda_scan.py` | 掃全部測項 × 25 片，產生統計偵測設定檔 |
| `src/build_die_baseline.py` | 建立 die 層級正常基準 |
| `app/hierarchical.py` | 三層式診斷核心（die 判定、原因規則、定位） |
| `app/anomaly_detector.py` | wafer 統計偵測器（Low yield / Stdev Down 用） |
| `app/sample.py` | `consumeData()` 串接：即時判定 + 通報 |
| `app/report_generator.py` | HTML 報告與機台文字訊息 |
| `app/oneapi_mock.py` | 本機 OneAPI 模擬（正式上機要換成官方 SDK） |
| `app/replay.py` | 用 CSV 重播成即時事件序列（整合測試） |
| `app/eval_hierarchical.py` | 離線評估（樣本內） |
| `app/eval_lowo.py` | 留一片交叉驗證 |
| `reports/die_baseline.json`, `reports/anomaly_detector_config.json` | 執行時載入的基準與設定 |
| `reports/live/` | 新流程產生的報告；舊開發報告已移至 `reports/live_archive/` |

---

## 5. 驗證結果

### 5.1 樣本內（用 25 片設計、用 25 片評估）—— 不是泛化證據
`app/eval_hierarchical.py`：

- 第 1 層二元判斷：**25/25**
- 第 2 層原因分類：**25/25**
- 18 片 Normal wafer 上被誤判為離群 die 的總數：**0**
- 定位結果：W01 → site 4 的 PID 8/12/16/20/24；W14、W18 → PID 16~28；W23 → PID 20~28；W25 → 無法定位；W03/W09 → 所有 bin-fail die。

### 5.2 OneAPI 事件重播整合測試（W1、W2、W14、W25）
- W1：第 8 顆即時通報 site unbalance，最終定位 site 4。
- W14：第 18 顆先通報（PID 16~18），最終列出 PID 16~28 共 13 顆。
- W25：判為 abnormal，標示無法定位。
- W2：全程無通報，判為 Normal。

### 5.3 留一片交叉驗證（LOWO，`app/eval_lowo.py`，25 折全部完成）
每折把 1 片 wafer 完全拿掉：die 基準只用其餘 Normal wafer 重建；統計偵測器的關鍵測項/基準/方向只用其餘 wafer 重選。結果檔：`reports/lowo_results.csv`。

| 指標 | 結果 |
|---|---|
| 第 1 層 二元判斷 | **22/25** |
| 第 2 層 原因分類（含 Normal） | **22/25** |
| Normal wafer 誤報 | **0/18** |
| 異常 wafer 漏報 | **3/7**（W03、W09、W25） |
| 異常 wafer 原因正確 | **4/7** |

| 異常 wafer | held-out 結果 | 說明 |
|---|---|---|
| W01 Site unbalance | ✅ 正確 | die 結構規則，不依賴範例 |
| W14 Mean Trend Up | ✅ 正確 | 同上 |
| W18 Mean Trend Down | ✅ 正確 | 同上 |
| W23 Stdev Trend Up | ✅ 正確 | 同上 |
| W03 Low yield | ❌ 漏報 | 只剩 W09 一片範例可學 |
| W09 Low yield | ❌ 漏報 | 只剩 W03 一片範例可學 |
| W25 Stdev Trend Down | ❌ 漏報 | 唯一範例被拿掉，沒有可學的東西 |

**結論**：靠 die 結構規則的 4 類（Site unbalance、Mean Trend Up/Down、Stdev Trend Up）在 held-out 下都成立，且 18 片 Normal 零誤報；**靠統計偵測器的 Low yield、Stdev Trend Down 在 held-out 下全部失敗**。也就是說，樣本內的 25/25 有 3 片是靠「這片本來就在設計資料裡」撐起來的。

註：4 類「成立」是指規則沒有針對被拿掉的那片重新學習；但規則本身的門檻（Z_OUT、K_EXC 等）仍是看過全部 25 片才定的（見第 6 節第 3 點），所以這 4 類的 held-out 成績仍可能偏樂觀。

---

## 6. 已知限制

1. **Low yield 泛化不足（LOWO 已證實失敗）**：目前只靠 30 個關鍵測項的 oos_rate，且只有 W03、W09 兩片範例，拿掉任一片都漏報。
2. **Stdev Trend Down 無法定位到單顆 die，且 LOWO 已證實學不到**：只有 W25 一片範例，held-out 下漏報。
3. **門檻是人工設定、看過全部 25 片才定**（Z_OUT=5、K_EXC=10、3 顆、80%、90%、15%/40%），交叉驗證還原不了這部分。
4. **die 層級沒有標準答案**，定位的正確性只能用間接證據支持（Normal wafer 零誤報、定位結果是乾淨的連續視窗或單一 site），算不出精確率/召回率。
5. Stdev Trend Up 與 Mean Trend 的區分（方向是否一致）是依 W14/W18/W23 三片歸納出的規則，物理上合理但樣本極少。
6. **W02 標籤存疑**（良率 53.8% 卻標 Normal）。
7. `app/oneapi_mock.py` 的 NexusData 欄位名稱是依 `PROJECT_CONTEXT.md` 第 6 節猜的，正式上機（Gemini）必須對照官方 ONEAPI 手冊確認。

---

## 7. 下一步（待決定）

- **修 Low yield**：改用 die 層級資訊（bin-fail 比例、fail die 的模式 A/B）輔助判斷，不只靠 30 個關鍵測項；需先跟主辦方確認 W02 的標籤與「良率 < 80%」的定義。
- **重新檢查 Stdev Trend Up/Down**：各只有一片範例，分類依據偏弱。
- 若主辦方能提供每顆 die 的異常標記，可直接量化 die 定位的精確率/召回率。
