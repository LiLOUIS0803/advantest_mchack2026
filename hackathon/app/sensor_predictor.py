"""
待辦 4：載入 src/train_sensor_models.py 訓練好的 6 個階段性模型，
在 consumeTPRequest() 收到 predict 請求時，用「目前這個 site 已經累積到的資料」
做推論，回傳這個 site 的溫度預測值。

模型的 feature_cols 是用 canonical key ("<test_num>#<pin>") 存的，
跟 anomaly_detector 用同一套 key，所以 site 的即時 buffer 可以直接兩邊共用。
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"


class SensorPredictor:
    def __init__(self, models_dir: Path = MODELS_DIR):
        self.stages: dict[int, dict] = {}
        for k in range(1, 7):
            path = models_dir / f"sensor{k}_model.joblib"
            if path.exists():
                self.stages[k] = joblib.load(path)

    def predict(self, stage: int, site: int, x: float | None, y: float | None, buffer: dict[str, float]) -> float:
        """buffer: canonical_key -> 目前已量到的值（該 site、該顆 device）。"""
        bundle = self.stages.get(stage)
        if bundle is None:
            raise KeyError(f"no model loaded for sensor stage {stage}")
        model = bundle["model"]
        feature_cols: list[str] = bundle["feature_cols"]  # 已包含 Site/X/Y + canonical test key
        meta_values = {"Site": site, "X": x, "Y": y}

        row = {c: meta_values.get(c, buffer.get(c, np.nan)) for c in feature_cols}
        X = pd.DataFrame([row], columns=feature_cols)
        pred = model.predict(X)[0]
        return float(pred)
