import logging
import re
from datetime import timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from database.models import AuditLog, User, db, utcnow
from services.audit import audit

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


def locked_out(email):
    since = utcnow() - timedelta(minutes=15)
    n = AuditLog.query.filter(AuditLog.action == "login_failed", AuditLog.actor_email == email, AuditLog.created_at >= since).count()
    return n >= 5


def password_problem(pw):
    if len(pw) < 10:
        return "Password must be at least 10 characters."
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "Password must contain letters and digits."
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if locked_out(email):
            flash("Too many failed attempts. Try again in 15 minutes.", "error")
            return render_template("login.html"), 429
        user = User.query.filter_by(email=email).first()
        if user and user.is_active and check_password_hash(user.password_hash, pw):
            login_user(user)
            audit("login", "", user)
            db.session.commit()
            log.info("Login success user_id=%s", user.id)
            return redirect(safe_next(request.args.get("next")) or url_for("main.dashboard"))
        db.session.add(AuditLog(actor_email=email[:255], action="login_failed", ip=request.remote_addr))
        db.session.commit()
        log.warning("Login failed for an account (ip=%s)", request.remote_addr)
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["ALLOW_REGISTRATION"] and User.query.count() > 0:
        flash("Registration is disabled. Ask an administrator for an account.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        err = (None if 1 <= len(name) <= 120 else "Name is required.") or \
              (None if EMAIL_RE.match(email) and len(email) <= 255 else "Enter a valid email address.") or password_problem(pw) or \
              ("An account with this email already exists." if User.query.filter_by(email=email).first() else None)
        if err:
            flash(err, "error")
            return render_template("register.html", name=name, email=email), 400
        role = "admin" if User.query.count() == 0 else "analyst"   # first account becomes the administrator
        user = User(name=name, email=email, password_hash=generate_password_hash(pw), role=role)
        db.session.add(user)
        db.session.flush()
        audit("register", f"role={role}", user)
        db.session.commit()
        login_user(user)
        flash("Account created." + (" You are the administrator." if role == "admin" else ""), "success")
        return redirect(url_for("main.dashboard"))
    return render_template("register.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit("logout")
    db.session.commit()
    logout_user()
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        cur, new = request.form.get("current_password", ""), request.form.get("new_password", "")
        if not check_password_hash(current_user.password_hash, cur):
            flash("Current password is incorrect.", "error")
        elif password_problem(new):
            flash(password_problem(new), "error")
        else:
            current_user.password_hash = generate_password_hash(new)
            audit("password_change")
            db.session.commit()
            flash("Password updated.", "success")
    return render_template("profile.html")


@bp.route("/profile/delete", methods=["POST"])
@login_required
def delete_account():
    """Data deletion: removes the user and all their students, predictions and batches."""
    from database.models import Batch, Student
    if current_user.is_admin and User.query.filter_by(role="admin", is_active_user=True).count() <= 1:
        flash("The only administrator cannot delete their account.", "error")
        return redirect(url_for("auth.profile"))
    if not check_password_hash(current_user.password_hash, request.form.get("password", "")):
        flash("Password is incorrect; account not deleted.", "error")
        return redirect(url_for("auth.profile"))
    uid, email = current_user.id, current_user.email
    for b in Batch.query.filter_by(user_id=uid).all():
        db.session.delete(b)
    for s in Student.query.filter_by(user_id=uid).all():
        db.session.delete(s)
    u = db.session.get(User, uid)
    audit("account_deleted", f"user_id={uid}", u)
    AuditLog.query.filter_by(user_id=uid).update({"user_id": None, "actor_email": None})
    logout_user()
    db.session.delete(u)
    db.session.commit()
    log.info("Account deleted user_id=%s", uid)
    flash("Your account and all associated data were deleted.", "success")
    return redirect(url_for("main.index"))
