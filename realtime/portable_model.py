"""NumPy-only inference for the exported scaler + multinomial logistic model."""
import numpy as np


class PortableClassifier:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as data:
            if int(data['format_version']) != 1:
                raise ValueError('Unsupported portable model version')
            for name in ('mean', 'scale', 'coef', 'intercept', 'classes', 'features', 'columns'):
                setattr(self, name, data[name].copy())
        self.classes_ = self.classes
        if self.coef.shape != (len(self.classes), len(self.features)) or np.any(self.scale <= 0):
            raise ValueError('Invalid portable model dimensions or scales')

    def predict_proba(self, values):
        x = np.asarray(values, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != len(self.features) or not np.isfinite(x).all():
            raise ValueError('Invalid classifier feature matrix')
        logits = ((x - self.mean) / self.scale) @ self.coef.T + self.intercept
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        return probabilities / probabilities.sum(axis=1, keepdims=True)
