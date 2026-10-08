"""Dataset loading, cleaning, target definition, schema and the shared preprocessing pipeline."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.features import ENGINEERED, FeatureEngineer
from ml.labels import (BINARY, CATEGORICAL, FEATURE_META, FLOAT, GROUP_ORDER, HARD_BOUNDS, VALUE_LABELS)

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "data.csv"
TARGET = "target"
POSITIVE_LABEL = "Dropout"          # target = 1 when the raw outcome is Dropout; Graduate/Enrolled -> 0
FEATURES = list(FEATURE_META.keys())
NUMERIC = [f for f in FEATURES if f not in CATEGORICAL]


def clean_name(name: str) -> str:
    """Normalise a column header: 'Mother's qualification' -> 'mothers_qualification'."""
    s = str(name).strip().lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return {"nacionality": "nationality"}.get(s, s)


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    df.columns = [clean_name(c) for c in df.columns]
    return df


def validate_dataset(df: pd.DataFrame) -> dict:
    missing = [c for c in FEATURES + [TARGET] if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing columns: {missing}")
    extra = [c for c in df.columns if c not in FEATURES + [TARGET]]
    if extra:
        raise ValueError(f"Dataset has unexpected columns: {extra}")
    if set(df[TARGET].unique()) - {"Dropout", "Enrolled", "Graduate"}:
        raise ValueError("Unexpected target labels")
    return {"rows": int(len(df)), "columns": int(df.shape[1]), "missing_values": int(df.isna().sum().sum()),
            "duplicate_rows": int(df.duplicated().sum())}


def to_binary_target(df: pd.DataFrame) -> pd.Series:
    return (df[TARGET] == POSITIVE_LABEL).astype(int)


def build_pipeline(estimator) -> Pipeline:
    """FeatureEngineer -> ColumnTransformer(impute/scale numeric, impute/one-hot categorical) -> estimator."""
    prep = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUMERIC + ENGINEERED),
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), CATEGORICAL),
    ])
    return Pipeline([("features", FeatureEngineer()), ("prep", prep), ("model", estimator)])


def kind_of(name: str) -> str:
    if name in CATEGORICAL:
        return "categorical"
    if name in BINARY:
        return "binary"
    return "float" if name in FLOAT else "integer"


def build_schema(X_train: pd.DataFrame) -> list:
    """Feature schema derived from the training split; drives validation, forms, templates and explanations."""
    schema = []
    for name in FEATURES:
        label, group, helptext = FEATURE_META[name]
        col = X_train[name]
        kind = kind_of(name)
        item = {"name": name, "label": label, "group": group, "help": helptext, "kind": kind,
                "train_min": float(col.min()), "train_max": float(col.max())}
        if name in HARD_BOUNDS:
            item["hard_min"], item["hard_max"] = HARD_BOUNDS[name]
        if kind == "categorical":
            vals = sorted(int(v) for v in col.unique())
            item["allowed"] = vals
            item["baseline"] = int(col.mode().iloc[0])
            names = VALUE_LABELS.get(name, {})
            item["options"] = [{"value": v, "label": f"{names[v]} ({v})" if v in names else f"Code {v}"} for v in vals]
        elif kind == "binary":
            item["allowed"] = [0, 1]
            item["baseline"] = int(col.mode().iloc[0])
            names = VALUE_LABELS[name]
            item["options"] = [{"value": v, "label": names[v]} for v in (1, 0)]
        else:
            item["baseline"] = float(col.median())
            item["train_mean"] = float(col.mean())
        schema.append(item)
    return schema


def group_schema(schema: list) -> list:
    out = []
    for g in GROUP_ORDER:
        items = [s for s in schema if s["group"] == g]
        if items:
            out.append({"group": g, "fields": items})
    return out
