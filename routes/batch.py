import csv
import io
import logging

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from database.models import Batch, Prediction, Student, db
from ml.predict import ModelUnavailable
from routes.students import _csv_response
from routes.utils import owned_or_404, scope_uid
from services.audit import audit
from services.batch_service import run_batch
from services.csv_service import parse_and_validate, safe_cell, template_csv
from services.model_service import get_predictor

bp = Blueprint("batch", __name__)
log = logging.getLogger(__name__)


@bp.route("/batch", methods=["GET", "POST"])
@login_required
def upload():
    try:
        pred = get_predictor()
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    from flask import current_app
    ctx = {"required": [s["name"] for s in pred.schema], "max_rows": current_app.config["MAX_BATCH_ROWS"],
           "max_mb": current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)}
    if request.method == "GET":
        return render_template("batch_predict.html", **ctx)
    f = request.files.get("file")
    name = secure_filename(f.filename) if f and f.filename else ""
    if not f or not name:
        flash("Choose a CSV file to upload.", "error")
        return render_template("batch_predict.html", **ctx), 400
    if not name.lower().endswith(".csv"):
        flash("Only .csv files are accepted.", "error")
        return render_template("batch_predict.html", **ctx), 400
    if f.mimetype not in ("text/csv", "application/vnd.ms-excel", "application/csv", "text/plain", "application/octet-stream"):
        flash("The file type is not accepted as CSV.", "error")
        return render_template("batch_predict.html", **ctx), 400
    parsed = parse_and_validate(f.read(), pred, ctx["max_rows"])   # nothing is written to disk
    dry = request.form.get("mode") == "validate"
    if parsed["file_errors"]:
        audit("csv_rejected", f"file={name} errors={len(parsed['file_errors'])}")
        db.session.commit()
        return render_template("batch_predict.html", parsed=parsed, filename=name, **ctx), 400
    if dry:
        preview = parsed["rows"][:10]
        return render_template("batch_predict.html", parsed=parsed, preview=preview, filename=name, dry=True,
                               warn_rows=sum(1 for r in parsed["rows"] if r["warnings"]), **ctx)
    try:
        batch = run_batch(current_user, name, parsed)
    except Exception:
        flash("The prediction job failed and was recorded as failed. Technical details were logged.", "error")
        return redirect(url_for("batch.history"))
    flash(f"{batch.valid_rows} records predicted" + (f", {batch.rejected_rows} rejected." if batch.rejected_rows else "."), "success")
    return redirect(url_for("batch.results", batch_id=batch.id))


@bp.route("/batch/template.csv")
@login_required
def template():
    try:
        content = template_csv(get_predictor())
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    return Response(content, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=student_batch_template.csv"})


@bp.route("/batches")
@login_required
def history():
    q = Batch.query
    if scope_uid():
        q = q.filter_by(user_id=scope_uid())
    page = q.order_by(Batch.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    summaries = {}
    for b in page.items:
        counts = dict(db.session.query(Prediction.risk_level, db.func.count()).filter(Prediction.batch_id == b.id)
                      .group_by(Prediction.risk_level).all())
        summaries[b.id] = counts
    return render_template("history.html", page=page, summaries=summaries)


@bp.route("/batches/<int:batch_id>")
@login_required
def results(batch_id):
    b = owned_or_404(Batch, batch_id)
    q = db.session.query(Prediction, Student).join(Student, Student.id == Prediction.student_id).filter(Prediction.batch_id == b.id)
    term, risk, outcome = request.args.get("q", "").strip(), request.args.get("risk", ""), request.args.get("outcome", "")
    sort = request.args.get("sort", "prob_desc")
    if term:
        q = q.filter(Student.student_ref.ilike(f"%{term[:64]}%"))
    if risk in ("LOW", "MEDIUM", "HIGH"):
        q = q.filter(Prediction.risk_level == risk)
    if outcome in ("dropout", "not"):
        q = q.filter(Prediction.predicted_dropout.is_(outcome == "dropout"))
    order = {"prob_desc": Prediction.probability.desc(), "prob_asc": Prediction.probability.asc(),
             "ref": Student.student_ref.asc()}.get(sort, Prediction.probability.desc())
    page = q.order_by(order, Prediction.id).paginate(page=request.args.get("page", 1, type=int), per_page=25, error_out=False)
    counts = dict(db.session.query(Prediction.risk_level, db.func.count()).filter(Prediction.batch_id == b.id)
                  .group_by(Prediction.risk_level).all())
    avg = db.session.query(db.func.avg(Prediction.probability)).filter(Prediction.batch_id == b.id).scalar()
    return render_template("results.html", b=b, page=page, counts=counts, avg=avg, term=term, risk=risk, outcome=outcome, sort=sort)


@bp.route("/batches/<int:batch_id>/download.csv")
@login_required
def download(batch_id):
    b = owned_or_404(Batch, batch_id)
    try:
        names = [s["name"] for s in get_predictor().schema]
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    rows = (db.session.query(Prediction, Student).join(Student, Student.id == Prediction.student_id)
            .filter(Prediction.batch_id == b.id).order_by(Prediction.id))
    header = ["student_id"] + names + ["predicted_outcome", "dropout_probability", "risk_percentage", "risk_category", "model_version"]
    body = [[s.student_ref] + [s.features[n] for n in names] +
            ["dropout_risk" if p.predicted_dropout else "not_at_risk", f"{p.probability:.4f}", f"{p.probability * 100:.1f}",
             p.risk_level, p.model_version.version] for p, s in rows]
    return _csv_response(f"batch_{b.id}_results.csv", header, body)


@bp.route("/batches/<int:batch_id>/rejected.csv")
@login_required
def rejected(batch_id):
    b = owned_or_404(Batch, batch_id)
    body = [[r["row"], r.get("student_id") or "", "; ".join(r["errors"])] for r in (b.rejected_detail or [])]
    return _csv_response(f"batch_{b.id}_rejected_rows.csv", ["row", "student_id", "errors"], body)


@bp.route("/batches/<int:batch_id>/delete", methods=["POST"])
@login_required
def delete(batch_id):
    b = owned_or_404(Batch, batch_id)
    audit("batch_deleted", f"batch={b.id}")
    db.session.delete(b)
    db.session.commit()
    flash("Batch and its predictions were deleted. Student records are kept.", "success")
    return redirect(url_for("batch.history"))
