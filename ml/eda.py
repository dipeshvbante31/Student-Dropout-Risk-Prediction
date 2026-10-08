"""Exploratory data analysis: produces JSON-serialisable summaries and data-derived insight sentences."""
import numpy as np
import pandas as pd

from ml.labels import COURSE_NAMES


def _rate_by(df, y, col, labels=None):
    g = pd.DataFrame({"k": df[col], "y": y}).groupby("k")["y"].agg(["mean", "count"])
    return [{"group": (labels or {}).get(k, str(k)), "dropout_rate": float(r["mean"]), "n": int(r["count"])} for k, r in g.iterrows()]


def run_eda(df: pd.DataFrame, y: pd.Series) -> dict:
    d = df.copy()
    d["_age"] = pd.cut(d["age_at_enrollment"], [0, 19, 24, 29, 100], labels=["<=19", "20-24", "25-29", "30+"])
    d["_appr2"] = pd.cut(d["curricular_units_2nd_sem_approved"], [-1, 0, 2, 4, 6, 100], labels=["0", "1-2", "3-4", "5-6", "7+"])
    d["_adm"] = pd.qcut(d["admission_grade"], 4, labels=["Q1 (lowest)", "Q2", "Q3", "Q4 (highest)"])
    yn = {1: "Yes", 0: "No"}
    sections = {
        "tuition_up_to_date": _rate_by(d, y, "tuition_fees_up_to_date", yn),
        "debtor": _rate_by(d, y, "debtor", yn),
        "scholarship_holder": _rate_by(d, y, "scholarship_holder", yn),
        "gender": _rate_by(d, y, "gender", {1: "Male", 0: "Female"}),
        "attendance": _rate_by(d, y, "daytime_evening_attendance", {1: "Daytime", 0: "Evening"}),
        "age_group": _rate_by(d, y, "_age"),
        "second_sem_units_approved": _rate_by(d, y, "_appr2"),
        "admission_grade_quartile": _rate_by(d, y, "_adm"),
    }
    course = _rate_by(d, y, "course", {k: v for k, v in COURSE_NAMES.items()})
    sections["course"] = sorted(course, key=lambda r: -r["n"])
    num = d.drop(columns=["target", "_age", "_appr2", "_adm"]).select_dtypes("number")
    corr = num.corrwith(y).dropna().sort_values(key=abs, ascending=False).head(10)
    q1, q3 = num.quantile(0.25), num.quantile(0.75)
    iqr = q3 - q1
    outlier_share = (((num < q1 - 1.5 * iqr) | (num > q3 + 1.5 * iqr)).mean()).sort_values(ascending=False).head(5)

    def rate(key, grp):
        return next(r["dropout_rate"] for r in sections[key] if r["group"] == grp) * 100

    insights = [
        f"Class balance: {int((df.target == 'Graduate').sum())} graduates, {int((df.target == 'Dropout').sum())} dropouts and "
        f"{int((df.target == 'Enrolled').sum())} still enrolled; the binary dropout rate is {y.mean() * 100:.1f}%.",
        f"Students whose tuition fees are not up to date have a {rate('tuition_up_to_date', 'No'):.0f}% dropout rate versus "
        f"{rate('tuition_up_to_date', 'Yes'):.0f}% for those up to date.",
        f"Students with no approved units in the 2nd semester have a {rate('second_sem_units_approved', '0'):.0f}% dropout rate versus "
        f"{rate('second_sem_units_approved', '7+'):.0f}% for those with 7 or more approved units.",
        f"Scholarship holders: {rate('scholarship_holder', 'Yes'):.0f}% dropout; non-holders: {rate('scholarship_holder', 'No'):.0f}%.",
        f"Students aged 30+ at enrollment: {rate('age_group', '30+'):.0f}% dropout versus {rate('age_group', '<=19'):.0f}% for those aged 19 or younger.",
        "These are associations in historical data from one institution, not evidence of causation.",
    ]
    return {"class_distribution": {k: int(v) for k, v in df["target"].value_counts().items()},
            "binary_dropout_rate": float(y.mean()), "dropout_rate_by": sections,
            "top_correlations": [{"feature": k, "correlation": float(v)} for k, v in corr.items()],
            "outlier_share_top": {k: float(v) for k, v in outlier_share.items()},
            "missing_values": int(df.isna().sum().sum()), "insights": insights}
