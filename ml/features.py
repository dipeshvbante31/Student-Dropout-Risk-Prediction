"""Feature engineering as a scikit-learn transformer so it is serialized inside the pipeline.

Training, single prediction and CSV batch prediction all go through this one code path.
Ratios divide only when the denominator is positive; otherwise they are 0 (documented rule).
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

ENGINEERED = [
    "sem1_approval_rate", "sem2_approval_rate", "sem1_evaluation_success", "sem2_evaluation_success",
    "total_units_approved", "total_units_enrolled", "overall_approval_rate",
    "grade_change", "approved_change", "sem2_no_units_approved",
]


def _ratio(num, den):
    num = np.asarray(num, dtype=float)
    den = np.asarray(den, dtype=float)
    return np.divide(num, den, out=np.zeros_like(num), where=den > 0)


class FeatureEngineer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = pd.DataFrame(X).copy()
        c = lambda s, n: X[f"curricular_units_{s}_sem_{n}"].astype(float)
        X["sem1_approval_rate"] = _ratio(c("1st", "approved"), c("1st", "enrolled"))
        X["sem2_approval_rate"] = _ratio(c("2nd", "approved"), c("2nd", "enrolled"))
        X["sem1_evaluation_success"] = _ratio(c("1st", "approved"), c("1st", "evaluations"))
        X["sem2_evaluation_success"] = _ratio(c("2nd", "approved"), c("2nd", "evaluations"))
        X["total_units_approved"] = c("1st", "approved") + c("2nd", "approved")
        X["total_units_enrolled"] = c("1st", "enrolled") + c("2nd", "enrolled")
        X["overall_approval_rate"] = _ratio(X["total_units_approved"], X["total_units_enrolled"])
        X["grade_change"] = c("2nd", "grade") - c("1st", "grade")
        X["approved_change"] = c("2nd", "approved") - c("1st", "approved")
        X["sem2_no_units_approved"] = ((c("2nd", "enrolled") > 0) & (c("2nd", "approved") == 0)).astype(float)
        return X
