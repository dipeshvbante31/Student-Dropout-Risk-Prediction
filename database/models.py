from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, UniqueConstraint

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="analyst")  # admin | analyst
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    @property
    def is_active(self):  # Flask-Login
        return self.is_active_user

    @property
    def is_admin(self):
        return self.role == "admin"


class ModelVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.String(120), unique=True, nullable=False)
    model_type = db.Column(db.String(80), nullable=False)
    trained_at = db.Column(db.DateTime, nullable=False)
    dataset_name = db.Column(db.String(200))
    dataset_sha256 = db.Column(db.String(64))
    metrics = db.Column(JSON)
    config = db.Column(JSON)
    artifact_path = db.Column(db.String(300))
    is_active = db.Column(db.Boolean, default=False, nullable=False)
    registered_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="processing")  # processing | completed | failed
    total_rows = db.Column(db.Integer, default=0, nullable=False)
    valid_rows = db.Column(db.Integer, default=0, nullable=False)
    rejected_rows = db.Column(db.Integer, default=0, nullable=False)
    rejected_detail = db.Column(JSON)  # [{row, student_id, errors}] -- no raw values stored
    model_version_id = db.Column(db.Integer, db.ForeignKey("model_version.id"), nullable=False)
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    user = db.relationship("User")
    model_version = db.relationship("ModelVersion")
    predictions = db.relationship("Prediction", back_populates="batch", cascade="all, delete-orphan")


class Student(db.Model):
    __table_args__ = (UniqueConstraint("user_id", "student_ref", name="uq_student_owner_ref"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    student_ref = db.Column(db.String(64), nullable=False, index=True)
    features = db.Column(JSON, nullable=False)  # exactly the model's input schema
    course_code = db.Column(db.Integer, index=True)  # denormalised model feature for grouping
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    user = db.relationship("User")
    predictions = db.relationship("Prediction", back_populates="student", cascade="all, delete-orphan",
                                  order_by="Prediction.id.desc()")


class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batch.id"), index=True)
    model_version_id = db.Column(db.Integer, db.ForeignKey("model_version.id"), nullable=False)
    probability = db.Column(db.Float, nullable=False)
    predicted_dropout = db.Column(db.Boolean, nullable=False)
    risk_level = db.Column(db.String(10), nullable=False, index=True)  # LOW | MEDIUM | HIGH
    explanation = db.Column(JSON)
    warnings = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    student = db.relationship("Student", back_populates="predictions")
    batch = db.relationship("Batch", back_populates="predictions")
    model_version = db.relationship("ModelVersion")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    actor_email = db.Column(db.String(255))
    action = db.Column(db.String(60), nullable=False, index=True)
    detail = db.Column(db.String(500))
    ip = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
