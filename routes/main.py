import logging

from flask import Blueprint, current_app, jsonify, render_template
from flask_login import login_required
from sqlalchemy import text

from database.models import db
from routes.utils import scope_uid
from services import analytics_service
from services.model_service import model_status

bp = Blueprint("main", __name__)
log = logging.getLogger(__name__)


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", d=analytics_service.dashboard(scope_uid()), status=model_status())


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@bp.route("/cookies")
def cookies():
    return render_template("cookies.html")


@bp.route("/health")
def health():
    checks = {"database": "ok", "model": "ok"}
    code = 200
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        log.exception("Health check: database failure")
        checks["database"], code = "unavailable", 503
    st = model_status()
    if not st["ok"]:
        checks["model"], code = "unavailable", 503
    else:
        checks["model_version"] = st["version"]
    return jsonify(status="ok" if code == 200 else "degraded", **checks), code
