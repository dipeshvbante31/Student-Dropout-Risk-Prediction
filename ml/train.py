"""Reproducible training pipeline.   Usage: python ml/train.py

Steps: load -> validate -> clean -> EDA -> split -> compare models (5-fold CV on the training
split) -> select by CV F1 for the dropout class -> evaluate ONCE on the held-out test set ->
permutation importance -> serialize pipeline + metadata under models/<version>/.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
                             roc_curve)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.eda import run_eda  # noqa: E402
from ml.labels import FEATURE_META  # noqa: E402
from ml.preprocess import (FEATURES, RAW_PATH, ROOT, build_pipeline, build_schema, load_raw, to_binary_target,  # noqa: E402
                           validate_dataset)

SEED = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
DECISION_THRESHOLD = 0.5
MODELS_DIR = ROOT / "models"
DATASET_INFO = {
    "name": "Predict Students' Dropout and Academic Success",
    "source": "UCI Machine Learning Repository, dataset id 697",
    "url": "https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success",
    "license": "CC BY 4.0",
    "citation": "Realinho, V., Machado, J., Baptista, L., Martins, M.V. (2022). Predicting student dropout and "
                "academic success. Data, 7(11), 146.",
}


def candidates():
    return {
        "Logistic Regression": LogisticRegression(max_iter=3000, class_weight="balanced", C=0.5, random_state=SEED),
        "Decision Tree": DecisionTreeClassifier(max_depth=6, min_samples_leaf=10, class_weight="balanced", random_state=SEED),
        "Random Forest": RandomForestClassifier(n_estimators=250, min_samples_leaf=3, class_weight="balanced_subsample",
                                                n_jobs=-1, random_state=SEED),
        "Gradient Boosting": HistGradientBoostingClassifier(learning_rate=0.05, max_iter=250, max_depth=4,
                                                           class_weight="balanced", random_state=SEED),
    }


def test_metrics(y_true, proba):
    pred = (proba >= DECISION_THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    fpr, tpr, _ = roc_curve(y_true, proba)
    idx = np.unique(np.linspace(0, len(fpr) - 1, 101).astype(int))
    return {"accuracy": accuracy_score(y_true, pred), "precision": precision_score(y_true, pred, zero_division=0),
            "recall": recall_score(y_true, pred), "f1": f1_score(y_true, pred), "roc_auc": roc_auc_score(y_true, proba),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "roc_curve": {"fpr": fpr[idx].round(4).tolist(), "tpr": tpr[idx].round(4).tolist()}}


def main():
    print("Loading dataset:", RAW_PATH)
    raw_bytes = RAW_PATH.read_bytes()
    df = load_raw()
    info = validate_dataset(df)
    info["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
    info["class_counts"] = {k: int(v) for k, v in df["target"].value_counts().items()}
    y = to_binary_target(df)
    X = df[FEATURES]
    print("Dataset:", info)

    eda = run_eda(df, y)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=TEST_SIZE, stratify=y, random_state=SEED)
    schema = build_schema(X_tr)
    cv = StratifiedKFold(CV_FOLDS, shuffle=True, random_state=SEED)
    scoring = {"f1": "f1", "recall": "recall", "precision": "precision", "roc_auc": "roc_auc", "accuracy": "accuracy"}

    comparison = []
    for name, est in candidates().items():
        res = cross_validate(build_pipeline(est), X_tr, y_tr, cv=cv, scoring=scoring, n_jobs=1)
        row = {"model": name, **{f"cv_{m}": float(res[f"test_{m}"].mean()) for m in scoring},
               **{f"cv_{m}_std": float(res[f"test_{m}"].std()) for m in ("f1", "roc_auc")}}
        fitted = build_pipeline(candidates()[name]).fit(X_tr, y_tr)   # fit on training split only
        row["test"] = test_metrics(y_te, fitted.predict_proba(X_te)[:, 1])
        comparison.append(row)
        print(f"{name:20s} CV F1={row['cv_f1']:.3f} CV AUC={row['cv_roc_auc']:.3f} | test F1={row['test']['f1']:.3f} "
              f"recall={row['test']['recall']:.3f} AUC={row['test']['roc_auc']:.3f}")

    # Selection uses cross-validation on the training split only (never the test set).
    best = max(comparison, key=lambda r: (round(r["cv_f1"], 3), r["cv_roc_auc"]))
    best_name = best["model"]
    pipe = build_pipeline(candidates()[best_name]).fit(X_tr, y_tr)
    proba_te = pipe.predict_proba(X_te)[:, 1]
    final = test_metrics(y_te, proba_te)

    print("Permutation importance on held-out test set...")
    pi = permutation_importance(pipe, X_te, y_te, scoring="roc_auc", n_repeats=5, random_state=SEED, n_jobs=-1)
    importance = sorted(({"feature": f, "label": FEATURE_META[f][0] + (" (" + FEATURE_META[f][1].lower() + ")" if "sem" in f else ""),
                          "importance": float(m), "std": float(s)}
                         for f, m, s in zip(FEATURES, pi.importances_mean, pi.importances_std)),
                        key=lambda d: -d["importance"])

    fairness = {}
    for gname, gval in (("Female", 0), ("Male", 1)):
        mask = (X_te["gender"] == gval).values
        p = (proba_te[mask] >= DECISION_THRESHOLD).astype(int)
        fairness[gname] = {"n": int(mask.sum()), "actual_dropout_rate": float(y_te[mask].mean()),
                           "predicted_dropout_rate": float(p.mean()), "recall": float(recall_score(y_te[mask], p)),
                           "precision": float(precision_score(y_te[mask], p, zero_division=0))}

    cfg = {"seed": SEED, "test_size": TEST_SIZE, "cv_folds": CV_FOLDS, "decision_threshold": DECISION_THRESHOLD,
           "selection_rule": "highest mean 5-fold CV F1 (dropout class) on training split; ties by CV ROC-AUC",
           "estimator_params": {k: str(v) for k, v in candidates()[best_name].get_params().items()}}
    digest = hashlib.sha256((info["sha256"] + json.dumps(cfg, sort_keys=True) + best_name).encode()).hexdigest()[:8]
    trained_at = datetime.now(timezone.utc)
    version = f"{best_name.lower().replace(' ', '-')}-{trained_at:%Y%m%d}-{digest}"

    meta = {"version": version, "model_type": best_name, "trained_at": trained_at.isoformat(),
            "sklearn_version": sklearn.__version__, "dataset": {**DATASET_INFO, **info,
            "binary_target": "target = 1 if raw outcome is 'Dropout'; 0 if 'Graduate' or 'Enrolled'",
            "mirror_note": "File obtained from a public GitHub mirror of the UCI file; verify sha256 against the UCI download."},
            "n_features": len(FEATURES), "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
            "train_dropout_rate": float(y_tr.mean()), "config": cfg, "schema": schema,
            "comparison": comparison, "metrics": final, "feature_importance": importance, "fairness_by_gender": fairness,
            "baseline_mean_probability": float(proba_te.mean()), "eda": eda}

    out = MODELS_DIR / version
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out / "model.joblib", compress=3)
    (out / "metadata.json").write_text(json.dumps(meta, indent=2))
    (MODELS_DIR / "current.json").write_text(json.dumps({"version": version}))

    sample = X_te.sample(40, random_state=SEED).copy()          # real held-out records, no labels
    sample.insert(0, "student_id", [f"HOLDOUT-{i:03d}" for i in range(1, len(sample) + 1)])
    sample.to_csv(ROOT / "data" / "processed" / "holdout_sample.csv", index=False)
    write_report(meta)
    print(f"\nSelected: {best_name}  version={version}")
    print({k: round(v, 3) for k, v in final.items() if isinstance(v, float)})


def write_report(m):
    L = [f"# Model report: {m['version']}", "", f"Trained: {m['trained_at']}  |  Selected: **{m['model_type']}**", "",
         "## Held-out test metrics (dropout = positive class)", ""]
    L += ["| Model | CV F1 | CV ROC-AUC | Test Acc | Test Precision | Test Recall | Test F1 | Test ROC-AUC |", "|---|---|---|---|---|---|---|---|"]
    for r in m["comparison"]:
        t = r["test"]
        L.append(f"| {r['model']} | {r['cv_f1']:.3f} | {r['cv_roc_auc']:.3f} | {t['accuracy']:.3f} | {t['precision']:.3f} | "
                 f"{t['recall']:.3f} | {t['f1']:.3f} | {t['roc_auc']:.3f} |")
    L += ["", "## Top permutation importances (test ROC-AUC drop)", ""]
    L += [f"- {d['label']}: {d['importance']:.4f}" for d in m["feature_importance"][:10]]
    L += ["", "## EDA insights", ""] + [f"- {s}" for s in m["eda"]["insights"]]
    (ROOT / "reports" / "model_report.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
