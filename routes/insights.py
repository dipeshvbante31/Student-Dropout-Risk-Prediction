from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user, login_required

from database.models import AuditLog, ModelVersion, User, db
from ml.predict import ModelUnavailable
from routes.utils import admin_required, scope_uid
from services import analytics_service
from services.audit import audit
from services.model_service import get_predictor

bp = Blueprint("insights", __name__)


@bp.route("/analytics")
@login_required
def analytics():
    try:
        meta = get_predictor().metadata
    except ModelUnavailable:
        meta = None
    charts = {}
    if meta:
        by = meta["eda"]["dropout_rate_by"]
        conv = lambda k: [{"label": r["group"], "value": round(r["dropout_rate"] * 100, 1), "n": r["n"]} for r in by[k]]
        charts = {"importance": [{"label": d["label"], "value": round(d["importance"], 4)} for d in meta["feature_importance"][:12]],
                  "tuition": conv("tuition_up_to_date"), "units": conv("second_sem_units_approved"),
                  "age": conv("age_group"), "scholarship": conv("scholarship_holder"),
                  "classes": [{"label": k, "value": v} for k, v in meta["eda"]["class_distribution"].items()]}
    return render_template("analytics.html", a=analytics_service.analytics(scope_uid()), meta=meta, charts=charts)


@bp.route("/model")
@login_required
def model():
    try:
        pred = get_predictor()
    except ModelUnavailable:
        return render_template("model_unavailable.html"), 503
    from services.model_service import active_model_version
    active_model_version()
    mon = analytics_service.monitoring(scope_uid(), pred)
    n_preds = db.session.query(db.func.count()).select_from(__import__("database.models", fromlist=["Prediction"]).Prediction).scalar()
    versions = ModelVersion.query.order_by(ModelVersion.id.desc()).all()
    m = pred.metadata
    imp = [{"label": d["label"], "value": round(d["importance"], 4)} for d in m["feature_importance"][:12]]
    return render_template("model.html", m=m, mon=mon, versions=versions, n_preds=n_preds, imp=imp)


@bp.route("/admin/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        u = db.session.get(User, request.form.get("user_id", type=int))
        action = request.form.get("action")
        admins = User.query.filter_by(role="admin", is_active_user=True).count()
        if not u or u.id == current_user.id:
            flash("You cannot change your own role or status here.", "error")
        elif action == "toggle_role":
            u.role = "analyst" if u.role == "admin" else "admin"
            audit("role_change", f"user_id={u.id} role={u.role}")
            db.session.commit()
        elif action == "toggle_active":
            if u.role == "admin" and u.is_active_user and admins <= 1:
                flash("Cannot deactivate the last administrator.", "error")
            else:
                u.is_active_user = not u.is_active_user
                audit("user_status", f"user_id={u.id} active={u.is_active_user}")
                db.session.commit()
        return redirect(url_for("insights.users"))
    return render_template("admin_users.html", users=User.query.order_by(User.id).all())


@bp.route("/admin/audit")
@admin_required
def audit_log():
    page = AuditLog.query.order_by(AuditLog.id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=50, error_out=False)
    return render_template("admin_audit.html", page=page)
