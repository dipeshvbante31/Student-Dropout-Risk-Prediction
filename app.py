import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, render_template, request
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import HTTPException

from config import Config
from database.models import User, db

migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    logging.basicConfig(level=app.config["LOG_LEVEL"], format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not app.config.get("SECRET_KEY"):
        if app.config["APP_ENV"] == "production":
            raise RuntimeError("SECRET_KEY must be set in production.")
        app.config["SECRET_KEY"] = "dev-only-insecure-key"
        app.logger.warning("Using insecure development SECRET_KEY")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///") and ":memory:" not in app.config["SQLALCHEMY_DATABASE_URI"]:
        os.makedirs(os.path.dirname(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")), exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(__file__), "database", "migrations"))
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    from routes import auth, batch, insights, main, predict, students
    for m in (main, auth, predict, students, batch, insights):
        app.register_blueprint(m.bp)

    @app.template_filter("pct")
    def pct(v, digits=1):
        return "-" if v is None else f"{v * 100:.{digits}f}%"

    @app.template_filter("dt")
    def dt(v):
        return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else "-"

    @app.template_global()
    def page_url(n):
        from flask import url_for
        return url_for(request.endpoint, **{**(request.view_args or {}), **request.args.to_dict(), "page": n})

    @app.context_processor
    def inject():
        c = app.config
        from ml.labels import COURSE_NAMES
        return {"cfg": c, "course_names": COURSE_NAMES, "low_pct": int(c["RISK_LOW_MAX"] * 100), "med_pct": int(c["RISK_MEDIUM_MAX"] * 100),
                "current_year": datetime.now(timezone.utc).year}

    @app.after_request
    def headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                                  "script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if app.config["APP_ENV"] == "production":
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.endpoint and request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    MESSAGES = {400: "The request could not be understood.", 401: "Please sign in to continue.",
                403: "You do not have permission to view this page.", 404: "The page you requested was not found.",
                413: "The uploaded file is too large.", 429: "Too many requests. Please try again later.",
                500: "Something went wrong on our side. The error has been logged."}

    def render_error(code, message=None):
        return render_template("errors/error.html", code=code, message=message or MESSAGES.get(code, "An error occurred.")), code

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_error(400, "Your session expired or the form was invalid. Reload the page and try again.")

    @app.errorhandler(HTTPException)
    def http_error(e):
        return render_error(e.code)

    @app.errorhandler(Exception)
    def unhandled(e):
        ref = uuid.uuid4().hex[:8]
        app.logger.exception("Unhandled error ref=%s", ref)
        db.session.rollback()
        return render_error(500, f"{MESSAGES[500]} Reference: {ref}")

    return app
