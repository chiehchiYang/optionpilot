"""Baseline buy-point model (XGBoost). Predicts P(profitable buy) from the feature row.

Kept deliberately thin: fit/predict over a feature DataFrame + label vector. The NudgeLayer
wraps predict() output downstream; this class knows nothing about nudging.

TODO: implement fit/predict over engineered features once the feature set is defined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class BaselineModel:
    def __init__(self, **xgb_params):
        self.params = xgb_params
        self._model = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "BaselineModel":
        raise NotImplementedError("BaselineModel.fit — implement with xgboost")

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return P(buy) in [0,1] per row."""
        raise NotImplementedError("BaselineModel.predict_proba")
