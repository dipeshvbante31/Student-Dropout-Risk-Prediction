import csv
import io
import logging

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from database.models import Prediction, Student, db
from ml.labels import COURSE_NAMES, VALUE_LABELS
from ml.predict import ModelUnavailable
from routes.utils import owned_or_404, scope_uid
from services.audit import audit
from services.csv_service import safe_cell
from services.model_service import get_predictor
from services.prediction_service import predict_single

bp = Blueprint("students", __name__)
log = logging.getLogger(__name__)


def latest_query(uid):
    last = select(func.max(Prediction.id)).where(Prediction.student_id == Student.id).correlate(Student).scalar_subquery()
    q = db.session.query(Student, Prediction).outerjoin(Prediction, Prediction.id == last)
    return q.filter(Student.user_id == uid) if uid else q


@bp.route("/students")
@login_required
def index():
    q = latest_query(scope_uid())
    term = request.args.get("q", "").strip()
    risk = request.args.get("risk", "")
    course = request.args.get("course", type=int)
    sort = request.args.get("sort", "recent")
    if term:
        q = q.filter(Student.student_ref.ilike(f"%{term[:64]}%"))
    if risk in ("LOW", "MEDIUM", "HIGH"):
        q = q.filter(Prediction.risk_level == risk)
    elif risk == "NONE":
        q = q.filter(Prediction.id.is_(None))
    if course:
        q = q.filter(Student.course_code == course)
    order = {"risk": Prediction.probability.desc().nullslast(), "ref": Student.student_ref.asc(),
             "recent": Student.updated_at.desc()}.get(sort, Student.updated_at.desc())
    page = q.order_by(order, Student.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    cq = db.session.query(Student.course_code).distinct()
    if scope_uid():
        cq = cq.filter(Student.user_id == scope_uid())
    courses = [c for (c,) in cq.order_by(Student.course_code)]
    return render_template("students.html", page=page, term=term, risk=risk, course=course, sort=sort,
                           courses=[(c, COURSE_NAMES.get(c, f"Course {c}")) for c in courses])


@bp.route("/students/<int:student_id>")
@login_required
def detail(student_id):
    s = owned_or_404(Student, student_id)
    latest = s.predictions[0] if s.predictions else None
    if latest and latest.explanation is None:
        try:
            pred = get_predictor()
            if latest.model_version.version == pred.version:
                latest.explanation = pred.explain(s.features)
                db.session.commit()
        except ModelUnavailable:
            pass
    schema = {}
    try:
        schema = {f["name"]: f for f in get_predictor().schema}
    except ModelUnavailable:
        pass
    rows = []
    for name, f in schema.items():
        v = s.features.get(name)
        names = VALUE_LABELS.get(name, {})
        rows.append({"group": f["group"], "label": f["label"], "value": names.get(v, v)})
    return render_template("student_detail.html", s=s, latest=latest, rows=rows)


@bp.route("/students/<int:student_id>/repredict", methods=["POST"])
@login_required
def repredict(student_id):
    s = owned_or_404(Student, student_id)
    try:
        row = predict_single(current_user.id, None, s.features, None, s)
        audit("prediction", f"prediction={row.id} repredict")
        db.session.commit()
    except ModelUnavailable:
        db.session.rollback()
        log.exception("Re-prediction failed")
        return render_template("model_unavailable.html"), 503
    flash("New prediction added to the history.", "success")
    return redirect(url_for("students.detail", student_id=s.id))


@bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
def delete(student_id):
    s = owned_or_404(Student, student_id)
    audit("student_deleted", f"student_id={s.id}")
    db.session.delete(s)
    db.session.commit()
    flash("Student and their predictions were deleted.", "success")
    return redirect(url_for("students.index"))


def _csv_response(name, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([safe_cell(c) for c in r])
    audit("csv_export", name)
    db.session.commit()
    return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


def prediction_rows(uid, high_only=False, latest_only=True):
    pred = get_predictor()
    names = [s["name"] for s in pred.schema]
    q = latest_query(uid) if latest_only else (db.session.query(Student, Prediction).join(Prediction, Prediction.student_id == Student.id))
    q = q.filter(Prediction.id.isnot(None))
    if uid and not latest_only:
        q = q.filter(Student.user_id == uid)
    if high_only:
        q = q.filter(Prediction.risk_level == "HIGH")
    header = ["student_id"] + names + ["predicted_outcome", "dropout_probability", "risk_percentage", "risk_category", "model_version", "predicted_at"]
    rows = [[s.student_ref] + [s.features[n] for n in names] +
            ["dropout_risk" if p.predicted_dropout else "not_at_risk", f"{p.probability:.4f}", f"{p.probability * 100:.1f}",
             p.risk_level, p.model_version.version, p.created_at.isoformat(timespec="seconds")]
            for s, p in q.order_by(Prediction.probability.desc())]
    return header, rows


@bp.route("/export/<kind>.csv")
@login_required
def export(kind):
    if kind not in ("students", "predictions", "high-risk"):
        abort(404)
    try:
        header, rows = prediction_rows(scope_uid(), high_only=kind == "high-risk", latest_only=kind != "predictions")
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    if kind == "students":
        pass
    return _csv_response(f"{kind}.csv", header, rows)
