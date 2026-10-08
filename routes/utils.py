from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def scope_uid():
    """Admins see all data; analysts only their own."""
    return None if current_user.is_admin else current_user.id


def owned_or_404(model, obj_id):
    from database.models import db
    obj = db.get_or_404(model, obj_id)
    if not current_user.is_admin and obj.user_id != current_user.id:
        abort(404)  # do not reveal existence of other users' records
    return obj


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **k):
        if not current_user.is_admin:
            abort(403)
        return f(*a, **k)
    return wrapper
