# JSON API v1

Backend: `http://127.0.0.1:8771`; frontend: `http://127.0.0.1:8770`.
前端透過同來源 `/api/*` proxy 呼叫後端。資料以 JSON 傳輸，不是由前端讀取 CSV，也不是以 JSON 檔取代訓練資料。

| Method | Path | Data |
|---|---|---|
| GET | /api/health | status, api_version |
| GET | /api/catalog | wafers, model |
| GET | /api/tests | tests：模型測項名稱陣列 |
| GET | /api/state?test=0 | 即時狀態與所選測項圖表 |
| GET | /api/export | 同狀態 JSON，可下載 |
| GET | /api/evaluation | 已儲存的開發驗證結果 |
| POST | /api/replay | `{"wafer":14,"delay":0.1}` |
| POST | /api/pause | `{"paused":true}`；只暫停重播 |
| POST | /api/events | 正規化事件，格式見 README |

狀態包含 `schema_version: 1`、`wafer`、`lot`、`completed`、`total_devices`、`passed`、`failed`、`yield`、`devices`、`failed_devices`、`timeline`、`alerts`、`predicted_label`、`predicted_labels`、`classification_history`、`running`、`paused`、`error`。

七類分類器已啟用：`predicted_label` 為一個官方 label，資料不足或不完整時為 null。相容欄位 `predicted_labels` 為長度 0 或 1 的陣列。滿 16 顆後每次 TestEnd 更新；部分測量、未完成 die 不進入分類。
`classification_history` 保留每批已完成數、單一預測與未判定原因；中途類別可能變動，不代表存在官方逐批真值。
`alerts` 仍保留舊模型診斷證據，但其 `formal_label` 為 null，不能合併成 wafer 類別。
`/api/evaluation` 現在回傳七類分類器比較報告：`selected`、`models`、`class_counts` 等；不再回舊模型的多標籤評分。

- `yield` 為 0–1 比例；尚無完成結果時為 null。
- `devices[].passed` 測試中為 null，完成後為 boolean。PF、Bin 缺值為 null 或尚未提供，不以模型分數補值。
- `timeline` 每筆含批次、累積完成/Fail/良率，以及該批完成數、Fail 數與比例。
- `alerts` 為模型事件，和實際 Fail 清單分開；`formal_label` 可為 null（輔助預警）。
- `test_chart` 只在指定 test 參數時提供；只包含已收到的測量值。
- 錯誤回應為非 2xx HTTP 狀態及 `{"error":"說明"}`。前端 proxy 在後端失聯時回 502。

單一後端目前只支援一條 wafer 串流；控制動作屬共享 session。CSV 重播的模擬順序限制維持不變。
