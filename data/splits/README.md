# 場景 1：Wafer 層級資料拆分

使用固定 seed `20260919`，以完整 wafer 分組。W2 依使用者要求排除，不讀取、不輸出，也不參與任何統計。

| 目錄 | 用途 | Wafer 數 | Device 數 |
|---|---|---:|---:|
| `train_normal/` | 建立正常基準、擬合前處理 | 12 | 960 |
| `validation_normal/` | 檢查正常資料誤報 | 5 | 400 |
| `validation_anomaly/` | 檢查異常偵測及開發調整 | 7 | 560 |

詳細分組見 `split_info.json`；每片的原始路徑、輸出路徑與 wafer 標籤見 `manifest.csv`。標籤保留原文，沒有加入測試資料欄位。Wafer 異常標籤不代表其中每顆 device 都異常。

## 格式

各分組 CSV 保留原始欄名、全部 80 筆 device、全部欄位值與列順序，僅將原始欄名下的四列 Pin、Test Num、High Limit、Low Limit 移至 `metadata/`。可以直接用 `pandas.read_csv(path)` 讀取分組 CSV。

原始 CSV 與 STDF 均未修改；STDF 不複製。上下限保持原始值，尚未修正疑似顛倒的上下限。

## 避免資料洩漏

- 這是開發用拆分，沒有獨立測試集。驗證組若用來調整門檻，不能當成未見測試資料報告效果。
- 標準化、正常基準與特徵選擇僅能在 `train_normal` 擬合。
- 輸出是完整歷史紀錄，不表示同一列所有欄位在測試中途都已可取得。
- 第一版以 device／多 Site 批次完成並收到結果後為候選偵測時點。重播僅揭露已收到資料，禁止使用未來 device 或整片最終統計。
- 原始列順序保留，但尚未確認 PID 等於實際事件順序；多 Site 同批回傳與欄位可用時機需依 ONEAPI 核對。
- PF、SBin、HBin、Test Time 等最終欄位，需等相應完成結果回傳後才可使用。
- 若要在 device 測試中途告警，必須另按實際流程遮蔽尚未回傳的測項；本次沒有按 subflow 拆分。
- Lot、Wafer、PID 用於分組與追蹤，不作為異常分類的識別捷徑；manifest 的 label 不可作為模型輸入。

## 重現

在專案根目錄執行：

```powershell
python scripts/split_data.py
```

腳本會覆寫同名產出，驗證 wafer 分組互斥、W2 排除、資料筆數、欄位一致性與輸出儲存格值一致性。它不訓練模型、不做標準化，也不重排原始資料。
