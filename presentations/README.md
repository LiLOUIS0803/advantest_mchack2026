# ACS RTDI 設計簡報

- `ACS_RTDI_design_story.pptx`：14 頁、16:9；文字、流程與比較圖可編輯，每頁附講者備註及來源。
- `ACS_RTDI_design_story.pdf`：供快速閱讀的圖像式 PDF 預覽。
- `overview.png`：全頁縮圖。
- `evidence.json`：場景 2 相同 wafer 分组下的訓練折平均值基準，以及保存的 Lasso 評估結果。

## 論述順序

題目痛點 → 時機與部署目標 → 標籤限制 → 場景 1 設計與比較 → 場景 2 因果輸入與基準比較 → 介面層級 → 官方系統分工 → 現場問題 → 驗收指標 → 結論。

## 數字的解讀

場景 1：19/24 是候選選型所用的完整 wafer 留一片結果，不代表七類泛化準確率。五個異常類別各只有一片。最終模型使用全部 24 片訓練，訓練內 24/24 不作效能證據。

場景 2：排除 W2，外層 5 折以 wafer 分組；依序排序 wafer，以 `wafers[i::5]` 決定每折。固定基準僅使用該折訓練 wafer 的目標平均值預測測試折。Lasso MAE 取自 `artifacts/scene2/evaluation.json`，沒有加線上偏差校正，也未量化現場回覆延遲。

70% 是「80 顆中測完 24 顆，剩下 56 顆」的示意比例，不是實測時間節省。47 項測試及 20 MB 傳輸測試是本機工程驗證，不是 Gemini 現場驗收。

## 重建版面

在專案根目錄執行 `python presentations/build_deck.py`。需要 python-pptx 與 Pillow；目前使用 Windows Microsoft JhengHei 字型。預覽由同一份版面程式繪製，並非 PowerPoint 本身輸出的逐像素渲染。
