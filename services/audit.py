from flask import has_request_context, request
from flask_login import current_user

from database.models import AuditLog, db


def audit(action: str, detail: str = "", user=None, commit: bool = False):
    """Record an accountability entry. Never pass passwords or student feature values in `detail`."""
    u = user or (current_user if has_request_context() and current_user.is_authenticated else None)
    db.session.add(AuditLog(user_id=getattr(u, "id", None), actor_email=getattr(u, "email", None), action=action,
                            detail=detail[:500], ip=(request.remote_addr if has_request_context() else None)))
    if commit:
        db.session.commit()
