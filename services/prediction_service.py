import logging

from flask import current_app

from database.models import Prediction, Student, db, utcnow
from services.model_service import active_model_version, get_predictor

log = logging.getLogger(__name__)


def risk_level(p: float) -> str:
    c = current_app.config
    return "LOW" if p < c["RISK_LOW_MAX"] else "MEDIUM" if p < c["RISK_MEDIUM_MAX"] else "HIGH"


def save_prediction(student: Student, prob: float, warnings, explanation=None, batch_id=None) -> Prediction:
    pred = get_predictor()
    mv = active_model_version()
    row = Prediction(student_id=student.id, batch_id=batch_id, model_version_id=mv.id, probability=prob,
                     predicted_dropout=prob >= pred.threshold, risk_level=risk_level(prob),
                     explanation=explanation, warnings=warnings or None)
    db.session.add(row)
    return row


def upsert_student(user_id: int, ref: str | None, features: dict) -> Student:
    s = Student.query.filter_by(user_id=user_id, student_ref=ref).first() if ref else None
    if s is None:
        s = Student(user_id=user_id, student_ref=ref or "pending", features=features, course_code=features["course"])
        db.session.add(s)
    else:
        s.features, s.course_code, s.updated_at = features, features["course"], utcnow()
    db.session.flush()
    if not ref:
        s.student_ref = f"S-{s.id}"
    return s


def predict_single(user_id: int, ref: str | None, features: dict, warnings, student: Student | None = None) -> Prediction:
    """Single-record path: same Predictor, same pipeline as the batch path."""
    pred = get_predictor()
    if student is None:
        student = upsert_student(user_id, ref, features)
    else:
        student.features, student.course_code, student.updated_at = features, features["course"], utcnow()
    prob = pred.predict_proba([features])[0]
    row = save_prediction(student, prob, warnings, pred.explain(features))
    db.session.flush()
    return row
