import logging

from database.models import Batch, Student, db, utcnow
from services.audit import audit
from services.model_service import active_model_version, get_predictor
from services.prediction_service import save_prediction

log = logging.getLogger(__name__)


def run_batch(user, filename: str, parsed: dict) -> Batch:
    """Predict every valid row with the serialized production pipeline and persist everything atomically."""
    pred = get_predictor()
    mv = active_model_version()
    rows = parsed["rows"]
    batch = Batch(user_id=user.id, filename=filename[:255], status="processing", total_rows=parsed["total"],
                  valid_rows=len(rows), rejected_rows=len(parsed["rejected"]), rejected_detail=parsed["rejected"],
                  model_version_id=mv.id)
    db.session.add(batch)
    db.session.flush()
    try:
        probs = pred.predict_proba([r["features"] for r in rows])
        refs = [r["ref"] or f"B{batch.id}-{r['row']}" for r in rows]
        existing = {s.student_ref: s for s in Student.query.filter(Student.user_id == user.id, Student.student_ref.in_(refs))}
        students = []
        for r, ref in zip(rows, refs):
            s = existing.get(ref)
            if s is None:
                s = Student(user_id=user.id, student_ref=ref, features=r["features"], course_code=r["features"]["course"])
                db.session.add(s)
            else:
                s.features, s.course_code, s.updated_at = r["features"], r["features"]["course"], utcnow()
            students.append(s)
        db.session.flush()
        for s, r, p in zip(students, rows, probs):
            save_prediction(s, p, r["warnings"], None, batch.id)
        batch.status, batch.completed_at = "completed", utcnow()
        audit("csv_upload", f"batch={batch.id} rows={parsed['total']} valid={len(rows)} rejected={len(parsed['rejected'])}", user)
        db.session.commit()
        log.info("Batch %s completed: %s valid, %s rejected", batch.id, len(rows), len(parsed["rejected"]))
        return batch
    except Exception as exc:
        db.session.rollback()
        log.exception("Batch prediction failed")
        failed = Batch(user_id=user.id, filename=filename[:255], status="failed", total_rows=parsed["total"],
                       valid_rows=0, rejected_rows=len(parsed["rejected"]), rejected_detail=parsed["rejected"],
                       model_version_id=mv.id, error_message="Prediction or database error; see server log.",
                       completed_at=utcnow())
        db.session.add(failed)
        db.session.commit()
        raise
