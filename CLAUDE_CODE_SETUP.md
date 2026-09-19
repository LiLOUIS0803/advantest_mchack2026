# 任務：在這台 server 上建立 Advantest RTDI 比賽「場景二（溫度預測）」的工作環境並驗證

## 背景（一分鐘版）
- 比賽：用 Advantest ACS RTDI / Gemini 做半導體測試即時監控。我負責場景二：在測試流程中，機台會在 6 個時間點問 container「sensor k 等一下會量到幾度」，我們要用前面已測完的測項預測出來。
- 程式已經寫好並在別處驗證過（`scene2_temp_prediction.zip`），這次只是要在這台 server 上重建環境、重跑一次確認結果一致。
- 資料在 `data.zip`（25 片 wafer 的 CSV + STDF，約 720 MB 解壓後）。

## 要建立的目錄結構

```
~/rtdi/
├── data/                              ← data.zip 解壓（保留 zip 內的 data/ 這層）
│   ├── A12345_W01_RawResult.csv ... A12345_W25_RawResult.csv
│   ├── A12345_W01.stdf ... （STDF 不會用到，留著就好）
│   └── TrainDataInfo.txt
├── scene2/                            ← scene2_temp_prediction.zip 解壓
│   ├── temp_predictor.py              推論核心（只依賴 numpy）
│   ├── scene2_hook.py                 給 ONEAPI sample.py 合併用的膠水層
│   ├── train_temp_models.py           訓練 + leave-wafer-out 評估
│   ├── replay_test.py                 用 CSV 模擬串流回放
│   ├── test_nexus_adapter.py          用假 NexusData 測事件解析
│   ├── README.md
│   └── models/
│       ├── temp_models.pkl            已訓練好的 6 個模型（純 numpy 權重）
│       ├── eval_report.json
│       └── eval_report.png
└── venv/                              ← Python 虛擬環境（見下）
```

兩個 zip 目前在：`<請填入 zip 所在路徑>`。如果 zip 解出來多了一層目錄（例如 `scene2/scene2/`），請攤平成上面的結構。

## 步驟

1. `mkdir -p ~/rtdi && cd ~/rtdi`，解壓兩個 zip 到上面的結構。**不要修改 data/ 裡任何檔案。**
2. 建虛擬環境（Python 3.9–3.11 皆可；container 端的 ONEAPI 支援 3.9/3.10/3.11，若這台有 3.10 優先用 3.10）：
   ```bash
   python3 -m venv venv && source venv/bin/activate
   pip install numpy pandas scikit-learn matplotlib
   ```
   如果沒有網路或 pip 裝不了 sklearn，仍可跳過訓練直接跑第 4、5 步（推論端只需要 numpy + pandas）。
3. 訓練與評估（約 3–5 分鐘，會訓 6 個模型 × 5 折）：
   ```bash
   cd scene2
   python train_temp_models.py --data ../data --out models/temp_models.pkl
   ```
4. 串流回放：
   ```bash
   python replay_test.py --data ../data
   ```
5. 事件解析測試：
   ```bash
   python test_nexus_adapter.py
   ```

## 驗收標準（請逐項回報）

- [ ] 目錄結構和上面一致，`data/` 有 25 個 `*_RawResult.csv`
- [ ] 第 3 步印出 6 行 `sensorK: ... LWO MAE=...`，數值應接近：
      sensor1≈0.003、sensor2≈0.043、sensor3≈0.021、sensor4≈0.051、sensor5≈0.065、sensor6≈0.067
      （差在 ±0.005 內都正常；差很多才需要回報）
- [ ] 第 4 步印出「回放 25 片, 12000 次預測」，串流 MAE 與上面的 LWO MAE 同量級，缺值次數全為 0
- [ ] 第 5 步最後一行印出 `串流預測 == 離線計算: PASS`
- [ ] 回報 Python 版本、numpy 版本、每次 predict 的平均微秒數

## 限制

- 不要改 `scene2/` 裡任何 `.py` 的邏輯；遇到錯誤先回報錯誤訊息和你判斷的原因，不要自行「修正」模型或特徵。路徑類的小問題（例如 zip 多一層目錄、`test_nexus_adapter.py` 裡寫死的 `../data/...` 路徑）可以直接處理，但要說明改了什麼。
- 不要動 `data/`。
- 不要安裝 oneapi / ONEAPI SDK，那是之後到 Gemini 上才做的事。
- 全部完成後，把 `scene2/models/eval_report.json` 的內容摘要（每個 sensor 的 mae、sensor4_limit_alert）貼出來。
