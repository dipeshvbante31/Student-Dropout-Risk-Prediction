import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # Hosts hand out postgres:// or postgresql://; pin the psycopg2 driver we ship.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg2://" + url[len(prefix):]
            break
    return url or f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}"


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _db_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MODEL_DIR = os.environ.get("MODEL_DIR", str(BASE_DIR / "models"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024
    MAX_BATCH_ROWS = int(os.environ.get("MAX_BATCH_ROWS", "5000"))
    # Communication thresholds (fractions). LOW: p < RISK_LOW_MAX ; MEDIUM: < RISK_MEDIUM_MAX ; else HIGH.
    RISK_LOW_MAX = float(os.environ.get("RISK_LOW_MAX", "0.40"))
    RISK_MEDIUM_MAX = float(os.environ.get("RISK_MEDIUM_MAX", "0.70"))
    ALLOW_REGISTRATION = os.environ.get("ALLOW_REGISTRATION", "true").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true" if APP_ENV == "production" else "false") == "true"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8
    DEVELOPER_NAME = os.environ.get("DEVELOPER_NAME", "Dipesh Vishnu Bante")
    DEVELOPER_EMAIL = os.environ.get("DEVELOPER_EMAIL", "dipeshbante31@gmail.com")
    DEVELOPER_GITHUB = os.environ.get("DEVELOPER_GITHUB", "https://github.com/dipeshvb31")
    DEVELOPER_INSTAGRAM = os.environ.get("DEVELOPER_INSTAGRAM", "https://www.instagram.com/ok.dipesh/")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
