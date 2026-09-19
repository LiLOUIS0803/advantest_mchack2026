# Wafer 單一分類器基準

候選選擇：logistic_l2；44 個摘要特徵；W2 排除，Site 差異已啟用。
每片只有一個訓練樣本；固定參數比較三個模型，留一片驗證。沒有將視窗隨機拆分。

| 模型 | LOO 正確 / 24 | Normal 誤報 / 17 | 可學類別平均召回 |
|---|---|---|---|
| logistic_l2 | 19 | 0 | 1.000 |
| random_forest | 17 | 0 | 0.500 |
| extra_trees | 18 | 1 | 0.971 |

可學類別只有 Normal（17 片）和 Low yield（2 片）。其餘 5 類各只有 1 片，留出後訓練集根本沒有該類，不能驗證七類泛化。
選擇結果僅為開發候選，不代表已證明適合所有七類。分數不可宣稱為七類準確率。
最終候選使用全部 24 片標籤重新訓練；原 validation 不再是此模型的獨立驗證。原切分檔不變。
comparison.json 的 prefix_replay_in_sample 僅展示測完每批後的单一預測；沒有給早期視窗套入最終異常標籤來訓練。
尚未替換即時服務：完整 wafer 分類與中途預測的分布不同，仍需事件重播與額外標註驗證。

| Wafer | 官方 label | 留一片預測 | 訓練集含該類 |
|---|---|---|---|
| W1 | Site unbalance | Normal | False |
| W3 | Low yield which yield is low than 80 | Low yield which yield is low than 80 | True |
| W4 | Normal | Normal | True |
| W5 | Normal | Normal | True |
| W6 | Normal | Normal | True |
| W7 | Normal | Normal | True |
| W8 | Normal | Normal | True |
| W9 | Low yield which yield is low than 80 | Low yield which yield is low than 80 | True |
| W10 | Normal | Normal | True |
| W11 | Normal | Normal | True |
| W12 | Normal | Normal | True |
| W13 | Normal | Normal | True |
| W14 | Mean Trend Up | Site unbalance | False |
| W15 | Normal | Normal | True |
| W16 | Normal | Normal | True |
| W17 | Normal | Normal | True |
| W18 | Mean Trend Down | Site unbalance | False |
| W19 | Normal | Normal | True |
| W20 | Normal | Normal | True |
| W21 | Normal | Normal | True |
| W22 | Normal | Normal | True |
| W23 | Stdev Trend Up | Low yield which yield is low than 80 | False |
| W24 | Normal | Normal | True |
| W25 | Stdev Trend Down | Normal | False |
