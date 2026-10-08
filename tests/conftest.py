import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import create_app  # noqa: E402
from config import TestConfig  # noqa: E402
from database.models import db  # noqa: E402
from services import model_service  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "processed" / "holdout_sample.csv"


def make_app(uri):
    class Cfg(TestConfig):
        SQLALCHEMY_DATABASE_URI = uri
    model_service.reset_cache()
    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture()
def db_uri(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture()
def app(db_uri):
    return make_app(db_uri)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def sample_df():
    return pd.read_csv(SAMPLE)


def register(client, email="a@example.com", pw="password123", name="Tester"):
    return client.post("/register", data={"name": name, "email": email, "password": pw}, follow_redirects=True)


def csv_bytes(df):
    return df.to_csv(index=False).encode()


def upload(client, content: bytes, name="students.csv", mode="predict"):
    return client.post("/batch", data={"file": (io.BytesIO(content), name), "mode": mode},
                       content_type="multipart/form-data", follow_redirects=False)
