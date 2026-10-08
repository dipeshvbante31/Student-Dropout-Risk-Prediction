import numpy as np
import pandas as pd
import pytest

from ml.features import ENGINEERED, FeatureEngineer
from ml.predict import ModelUnavailable, Predictor
from ml.preprocess import FEATURES, RAW_PATH, clean_name, load_raw, to_binary_target, validate_dataset


@pytest.fixture(scope="module")
def predictor():
    return Predictor.load()


def test_dataset_loads_and_validates():
    df = load_raw()
    info = validate_dataset(df)
    assert info["rows"] == 4424 and info["missing_values"] == 0
    assert set(FEATURES) <= set(df.columns)
    assert to_binary_target(df).sum() == 1421  # Dropout count in the UCI dataset


def test_clean_name():
    assert clean_name("Mother's qualification") == "mothers_qualification"
    assert clean_name("Daytime/evening attendance\t") == "daytime_evening_attendance"
    assert clean_name("Nacionality") == "nationality"


def test_feature_engineering_safe_division():
    df = load_raw()[FEATURES].head(5).copy()
    df["curricular_units_1st_sem_enrolled"] = 0
    out = FeatureEngineer().transform(df)
    assert set(ENGINEERED) <= set(out.columns)
    assert (out["sem1_approval_rate"] == 0).all() and np.isfinite(out[ENGINEERED].values).all()


def test_model_loads_and_predicts(predictor, sample_df):
    recs = []
    for _, r in sample_df.iterrows():
        clean, errs, _ = predictor.validate_record(r.to_dict())
        assert not errs
        recs.append(clean)
    probs = predictor.predict_proba(recs)
    assert len(probs) == len(recs) and all(0 <= p <= 1 for p in probs)
    assert len(set(round(p, 3) for p in probs)) > 5  # real, varied probabilities


def test_single_and_batch_predictions_are_consistent(predictor, sample_df):
    recs = [predictor.validate_record(r.to_dict())[0] for _, r in sample_df.head(10).iterrows()]
    batch = predictor.predict_proba(recs)
    for r, b in zip(recs, batch):
        assert predictor.predict_proba([r])[0] == pytest.approx(b, abs=1e-9)


def test_model_beats_baseline_on_real_data(predictor):
    m = predictor.metadata["metrics"]
    assert m["roc_auc"] > 0.85 and m["recall"] > 0.7


def test_validation_rejects_bad_values(predictor, sample_df):
    good = sample_df.iloc[0].to_dict()
    for key, val in [("course", 1), ("age_at_enrollment", "abc"), ("gdp", ""), ("admission_grade", 500),
                     ("curricular_units_1st_sem_approved", 2.5), ("gender", 7), ("debtor", None)]:
        bad = {**good, key: val}
        clean, errs, _ = predictor.validate_record(bad)
        assert clean is None and any(e.startswith(key) for e in errs), key


def test_out_of_training_range_is_flagged_not_rejected(predictor, sample_df):
    rec = {**sample_df.iloc[0].to_dict(), "age_at_enrollment": 99}
    clean, errs, warns = predictor.validate_record(rec)
    assert clean is not None and not errs and any("age_at_enrollment" in w for w in warns)


def test_missing_model_raises(tmp_path):
    with pytest.raises(ModelUnavailable):
        Predictor.load(tmp_path)
