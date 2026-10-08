"""All dashboard / analytics numbers are computed from persisted data. Nothing is hardcoded."""
from collections import Counter, defaultdict

from sqlalchemy import func, select

from database.models import Batch, Prediction, Student, db
from ml.labels import COURSE_NAMES

LEVELS = ["LOW", "MEDIUM", "HIGH"]
ROW_LIMIT = 50000


def _scoped(q, model, uid):
    return q.filter(model.user_id == uid) if uid else q


def latest_rows(uid):
    """Latest prediction per student: list of dicts."""
    inner = select(func.max(Prediction.id)).join(Student, Student.id == Prediction.student_id)
    if uid:
        inner = inner.where(Student.user_id == uid)
    inner = inner.group_by(Prediction.student_id)
    q = (db.session.query(Prediction.probability, Prediction.risk_level, Prediction.predicted_dropout,
                          Prediction.created_at, Student.features, Student.course_code)
         .join(Student, Student.id == Prediction.student_id).filter(Prediction.id.in_(inner)).limit(ROW_LIMIT))
    return [dict(p=r[0], level=r[1], dropout=r[2], at=r[3], f=r[4], course=r[5]) for r in q]


def _avg(xs):
    return sum(xs) / len(xs) if xs else None


def dashboard(uid):
    rows = latest_rows(uid)
    total_students = _scoped(db.session.query(func.count(Student.id)), Student, uid).scalar()
    total_preds = (db.session.query(func.count(Prediction.id)).join(Student, Student.id == Prediction.student_id))
    total_preds = (total_preds.filter(Student.user_id == uid) if uid else total_preds).scalar()
    batches = _scoped(db.session.query(func.count(Batch.id)), Batch, uid).scalar()
    lv = Counter(r["level"] for r in rows)
    recent_q = (db.session.query(Prediction, Student).join(Student, Student.id == Prediction.student_id))
    recent_q = recent_q.filter(Student.user_id == uid) if uid else recent_q
    recent = recent_q.order_by(Prediction.id.desc()).limit(8).all()
    return {"total_students": total_students, "total_predictions": total_preds, "batches": batches,
            "low": lv["LOW"], "medium": lv["MEDIUM"], "high": lv["HIGH"],
            "dropout_predicted": sum(1 for r in rows if r["dropout"]),
            "avg_probability": _avg([r["p"] for r in rows]), "recent": recent,
            "risk_distribution": [{"label": l.title(), "value": lv[l], "key": l} for l in LEVELS],
            "trend": trend(uid), "by_course": by_course(rows), "has_data": bool(rows)}


def trend(uid, days=30):
    q = (db.session.query(func.date(Prediction.created_at), func.count(Prediction.id), func.avg(Prediction.probability))
         .join(Student, Student.id == Prediction.student_id))
    q = q.filter(Student.user_id == uid) if uid else q
    data = q.group_by(func.date(Prediction.created_at)).order_by(func.date(Prediction.created_at).desc()).limit(days).all()
    data = sorted(data, key=lambda r: str(r[0]))
    return [{"label": str(d)[5:], "count": int(c), "avg": float(a)} for d, c, a in data]


def by_course(rows, top=10):
    g = defaultdict(list)
    for r in rows:
        g[r["course"]].append(r["p"])
    items = sorted(g.items(), key=lambda kv: -len(kv[1]))[:top]
    return [{"label": COURSE_NAMES.get(c, f"Course {c}"), "value": round(_avg(ps) * 100, 1), "n": len(ps)} for c, ps in items]


def _binned(rows, key, bins):
    """bins: list of (label, predicate on feature value)."""
    out = []
    for label, pred in bins:
        ps = [r["p"] for r in rows if pred(r["f"][key])]
        out.append({"label": label, "value": round(_avg(ps) * 100, 1) if ps else 0, "n": len(ps)})
    return out


def analytics(uid):
    rows = latest_rows(uid)
    hist = [0] * 10
    for r in rows:
        hist[min(int(r["p"] * 10), 9)] += 1
    k2 = "curricular_units_2nd_sem_approved"
    perf = _binned(rows, k2, [("0", lambda v: v == 0), ("1-2", lambda v: 1 <= v <= 2), ("3-4", lambda v: 3 <= v <= 4),
                              ("5-6", lambda v: 5 <= v <= 6), ("7+", lambda v: v >= 7)])
    fin = []
    for key, name in (("tuition_fees_up_to_date", "Tuition up to date"), ("debtor", "Debtor"), ("scholarship_holder", "Scholarship")):
        for val, lab in ((1, "yes"), (0, "no")):
            ps = [r["p"] for r in rows if r["f"][key] == val]
            fin.append({"label": f"{name}: {lab}", "value": round(_avg(ps) * 100, 1) if ps else 0, "n": len(ps)})
    bq = _scoped(db.session.query(Batch), Batch, uid).order_by(Batch.id.desc()).limit(10).all()
    return {"n": len(rows), "histogram": [{"label": f"{i * 10}-{i * 10 + 10}%", "value": v} for i, v in enumerate(hist)],
            "performance": perf, "financial": fin, "by_course": by_course(rows), "trend": trend(uid),
            "risk_distribution": [{"label": l.title(), "value": sum(1 for r in rows if r["level"] == l), "key": l} for l in LEVELS],
            "batches": bq}


def monitoring(uid, predictor, recent=500):
    """Basic, honest monitoring: out-of-training-range inputs, prediction shift, rejection rate."""
    inner = (db.session.query(Prediction.probability, Student.features).join(Student, Student.id == Prediction.student_id))
    inner = inner.filter(Student.user_id == uid) if uid else inner
    rows = inner.order_by(Prediction.id.desc()).limit(recent).all()
    res = {"n": len(rows), "warnings": [], "out_of_range": [], "mean_prob": None,
           "baseline_mean_prob": predictor.metadata["baseline_mean_probability"]}
    if rows:
        res["mean_prob"] = _avg([r[0] for r in rows])
        for s in predictor.schema:
            if s["kind"] in ("integer", "float"):
                n = sum(1 for _, f in rows if not (s["train_min"] <= f[s["name"]] <= s["train_max"]))
                if n:
                    res["out_of_range"].append({"feature": s["label"], "name": s["name"], "share": n / len(rows), "n": n})
        res["out_of_range"].sort(key=lambda d: -d["share"])
        if len(rows) >= 30 and abs(res["mean_prob"] - res["baseline_mean_prob"]) > 0.10:
            res["warnings"].append("Mean predicted probability of recent predictions differs from the held-out test baseline "
                                   "by more than 10 percentage points. Inputs may differ from the training population.")
        if res["out_of_range"] and res["out_of_range"][0]["share"] > 0.05:
            res["warnings"].append("More than 5% of recent records have a value outside the training range for "
                                   f"'{res['out_of_range'][0]['feature']}'.")
    b = _scoped(db.session.query(func.coalesce(func.sum(Batch.total_rows), 0), func.coalesce(func.sum(Batch.rejected_rows), 0)), Batch, uid).one()
    res["batch_rows"], res["batch_rejected"] = int(b[0]), int(b[1])
    if res["batch_rows"] and res["batch_rejected"] / res["batch_rows"] > 0.10:
        res["warnings"].append("More than 10% of uploaded CSV rows were rejected by validation.")
    return res
