"""Inference: one Predictor used by the single-prediction form AND CSV batch prediction.

Validation rules (documented policy; values are never silently altered or imputed):
  * every schema feature must be present and non-empty
  * categorical / binary values must belong to the allowed set seen in training
  * integers must be whole numbers; all numbers must be finite and within hard bounds
  * values outside the *training* min/max are accepted but flagged as 'out_of_range' warnings
"""
import json
import math
from pathlib import Path

import joblib
import pandas as pd

from ml.explain import local_explanation
from ml.preprocess import FEATURES

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


class ModelUnavailable(RuntimeError):
    pass


class Predictor:
    def __init__(self, version: str, pipeline, metadata: dict):
        self.version = version
        self.pipeline = pipeline
        self.metadata = metadata
        self.schema = metadata["schema"]
        self.by_name = {s["name"]: s for s in self.schema}
        self.threshold = metadata["config"]["decision_threshold"]

    @classmethod
    def load(cls, models_dir: Path = MODELS_DIR, version: str | None = None):
        try:
            if version is None:
                version = json.loads((models_dir / "current.json").read_text())["version"]
            meta = json.loads((models_dir / version / "metadata.json").read_text())
            pipe = joblib.load(models_dir / version / "model.joblib")
        except (OSError, KeyError, ValueError) as exc:
            raise ModelUnavailable(f"Production model could not be loaded: {exc}") from exc
        return cls(version, pipe, meta)

    # ---- validation -------------------------------------------------------------------------
    def validate_record(self, raw: dict):
        """Return (clean_record | None, errors[list[str]], warnings[list[str]])."""
        clean, errors, warnings = {}, [], []
        for s in self.schema:
            name, label = s["name"], s["label"]
            val = raw.get(name)
            if val is None or str(val).strip() == "":
                errors.append(f"{name}: value is required")
                continue
            try:
                num = float(str(val).strip())
            except ValueError:
                errors.append(f"{name}: '{str(val)[:20]}' is not a number")
                continue
            if not math.isfinite(num):
                errors.append(f"{name}: value must be finite")
                continue
            if s["kind"] in ("categorical", "binary", "integer") and num != int(num):
                errors.append(f"{name}: must be a whole number")
                continue
            if s["kind"] in ("categorical", "binary"):
                if int(num) not in s["allowed"]:
                    errors.append(f"{name}: {int(num)} is not an allowed value")
                    continue
                clean[name] = int(num)
                continue
            lo, hi = s.get("hard_min"), s.get("hard_max")
            if lo is not None and not (lo <= num <= hi):
                errors.append(f"{name}: {num:g} outside valid range {lo}-{hi}")
                continue
            clean[name] = int(num) if s["kind"] == "integer" else num
            if not (s["train_min"] <= num <= s["train_max"]):
                warnings.append(f"{name}: {num:g} outside training range {s['train_min']:g}-{s['train_max']:g}")
        return (None if errors else clean), errors, warnings

    # ---- inference --------------------------------------------------------------------------
    def frame(self, records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records, columns=FEATURES)

    def predict_proba(self, records: list[dict]) -> list[float]:
        try:
            return [float(p) for p in self.pipeline.predict_proba(self.frame(records))[:, 1]]
        except Exception as exc:  # surfaced to callers as a model failure, logged there
            raise ModelUnavailable(f"Prediction failed: {exc}") from exc

    def explain(self, record: dict, top_n: int = 5) -> dict:
        return local_explanation(self, record, top_n)
