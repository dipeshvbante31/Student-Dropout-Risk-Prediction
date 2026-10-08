import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database.models import Prediction, Student, db
from ml.predict import ModelUnavailable
from ml.preprocess import group_schema
from routes.utils import owned_or_404
from services.audit import audit
from services.csv_service import REF_RE
from services.model_service import get_predictor
from services.prediction_service import predict_single

bp = Blueprint("predict", __name__)
log = logging.getLogger(__name__)


def _form(student=None, values=None, errors=None, status=200):
    try:
        pred = get_predictor()
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    return render_template("predict.html", groups=group_schema(pred.schema), student=student,
                           values=values or (student.features if student else {}), errors=errors or {}), status


def _handle(student=None):
    try:
        pred = get_predictor()
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    ref = request.form.get("student_id", "").strip() or None
    clean, errs, warns = pred.validate_record(request.form)
    errors = {}
    for e in errs:
        k, _, msg = e.partition(": ")
        errors[k] = msg
    if ref and not REF_RE.match(ref):
        errors["student_id"] = "Use 1-64 letters, digits, space or . _ - /"
    if student is None and ref and Student.query.filter_by(user_id=current_user.id, student_ref=ref).first():
        errors["student_id"] = "A student with this ID already exists. Open it and use Edit to add a new prediction."
    if errors:
        flash("Please correct the highlighted fields.", "error")
        return _form(student, {**request.form}, errors, 400)
    try:
        row = predict_single(current_user.id, ref if student is None else None, clean, warns, student)
        audit("prediction", f"prediction={row.id}")
        db.session.commit()
    except ModelUnavailable:
        db.session.rollback()
        log.exception("Prediction failed")
        return render_template("model_unavailable.html"), 503
    log.info("Prediction %s generated", row.id)
    return redirect(url_for("predict.result", prediction_id=row.id))


@bp.route("/predict", methods=["GET", "POST"])
@login_required
def new():
    return _handle() if request.method == "POST" else _form()


@bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
def edit(student_id):
    s = owned_or_404(Student, student_id)
    return _handle(s) if request.method == "POST" else _form(s)


@bp.route("/predictions/<int:prediction_id>")
@login_required
def result(prediction_id):
    p = db.get_or_404(Prediction, prediction_id)
    if not current_user.is_admin and p.student.user_id != current_user.id:
        abort(404)
    return render_template("result.html", p=p, s=p.student)
