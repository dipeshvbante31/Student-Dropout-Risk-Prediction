import pandas as pd
import pytest

from database.models import Batch, Prediction, Student, db
from tests.conftest import csv_bytes, make_app, register, upload


def form_from_row(row):
    d = {k: str(v) for k, v in row.items()}
    return d


def test_pages_public_and_protected(client):
    for path in ("/", "/about", "/privacy", "/cookies", "/login", "/register"):
        assert client.get(path).status_code == 200
    for path in ("/dashboard", "/predict", "/students", "/batch", "/batches", "/analytics", "/model"):
        r = client.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert client.get("/nope").status_code == 404


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json["database"] == "ok" and r.json["model"] == "ok"


def test_register_login_logout_and_first_user_admin(client):
    r = register(client)
    assert b"administrator" in r.data.lower()
    client.post("/logout")
    assert client.get("/dashboard").status_code == 302
    bad = client.post("/login", data={"email": "a@example.com", "password": "wrong"})
    assert b"Invalid email or password" in bad.data
    ok = client.post("/login", data={"email": "a@example.com", "password": "password123"}, follow_redirects=True)
    assert ok.status_code == 200 and b"Dashboard" in ok.data


def test_weak_password_and_duplicate_email(client):
    assert register(client, pw="short").status_code == 400
    register(client)
    client.post("/logout")
    assert register(client).status_code == 400


def test_empty_states(client):
    register(client)
    assert b"No student records available yet." in client.get("/dashboard").data
    assert b"No student records available yet." in client.get("/students").data
    assert b"No CSV prediction batches have been uploaded." in client.get("/batches").data
    assert b"Analytics will appear after prediction data is available." in client.get("/analytics").data


def test_individual_prediction_flow_and_persistence_across_restart(db_uri, sample_df):
    app = make_app(db_uri)
    c = app.test_client()
    register(c)
    data = form_from_row(sample_df.iloc[1].drop("student_id")) | {"student_id": "S-100"}
    r = c.post("/predict", data=data)
    assert r.status_code == 302
    page = c.get(r.headers["Location"])
    assert b"The model predicts a" in page.data and b"This student will drop out" not in page.data
    with app.app_context():
        p = Prediction.query.one()
        prob, version = p.probability, p.model_version.version
        assert 0 <= prob <= 1
    # restart: brand-new application instance on the same database
    app2 = make_app(db_uri)
    c2 = app2.test_client()
    c2.post("/login", data={"email": "a@example.com", "password": "password123"})
    with app2.app_context():
        s = Student.query.filter_by(student_ref="S-100").one()
        assert s.predictions[0].probability == prob and s.predictions[0].model_version.version == version
        sid = s.id
    assert b"S-100" in c2.get(f"/students/{sid}").data
    assert b"S-100" in c2.get("/students").data
    # edit + re-predict keeps history
    c2.post(f"/students/{sid}/repredict")
    with app2.app_context():
        assert Prediction.query.count() == 2


def test_prediction_validation_errors_are_shown(client, sample_df):
    register(client)
    data = form_from_row(sample_df.iloc[0].drop("student_id")) | {"course": "1", "gdp": ""}
    r = client.post("/predict", data=data)
    assert r.status_code == 400 and b"not an allowed value" in r.data and b"value is required" in r.data
    with client.application.app_context():
        assert Student.query.count() == 0


def test_csv_template_matches_model_schema(client):
    register(client)
    from services.model_service import get_predictor
    with client.application.app_context():
        names = [s["name"] for s in get_predictor().schema]
    header = client.get("/batch/template.csv").data.decode().strip().split(",")
    assert header == ["student_id"] + names


def test_csv_batch_end_to_end(db_uri, sample_df):
    app = make_app(db_uri)
    c = app.test_client()
    register(c)
    r = upload(c, csv_bytes(sample_df))
    assert r.status_code == 302
    batch_page = c.get(r.headers["Location"])
    assert b"HOLDOUT-001" in batch_page.data
    with app.app_context():
        b = Batch.query.one()
        assert b.status == "completed" and b.valid_rows == len(sample_df) and b.rejected_rows == 0
        assert Prediction.query.filter_by(batch_id=b.id).count() == len(sample_df)
        bid = b.id
        probs = {p.student.student_ref: p.probability for p in Prediction.query.all()}
    # consistency with the individual path
    row = sample_df.iloc[2]
    form = form_from_row(row.drop("student_id")) | {"student_id": "INDIV-1"}
    c.post("/predict", data=form)
    with app.app_context():
        indiv = Student.query.filter_by(student_ref="INDIV-1").one().predictions[0].probability
    assert indiv == pytest.approx(probs[row["student_id"]], abs=1e-9)
    # download contains the real predictions
    dl = c.get(f"/batches/{bid}/download.csv")
    out = pd.read_csv(pd.io.common.BytesIO(dl.data))
    assert {"student_id", "predicted_outcome", "dropout_probability", "risk_percentage", "risk_category"} <= set(out.columns)
    assert len(out) == len(sample_df)
    got = dict(zip(out.student_id, out.dropout_probability))
    assert all(abs(got[k] - round(v, 4)) < 1e-4 for k, v in probs.items() if k in got)
    # history + dashboard reflect the database
    assert b"students.csv" in c.get("/batches").data
    dash = c.get("/dashboard").data.decode()
    assert str(len(sample_df) + 1) in dash
    # restart: batch history persists
    app2 = make_app(db_uri)
    c2 = app2.test_client()
    c2.post("/login", data={"email": "a@example.com", "password": "password123"})
    assert b"students.csv" in c2.get("/batches").data
    assert b"HOLDOUT-001" in c2.get(f"/batches/{bid}").data


def test_csv_validation_errors(client, sample_df):
    register(client)
    cases = {
        "empty": (b"", b"empty"),
        "missing col": (csv_bytes(sample_df.drop(columns=["gdp"])), b"Missing required column"),
        "extra col": (csv_bytes(sample_df.assign(target="x")), b"Unexpected column"),
        "header only": (csv_bytes(sample_df.head(0)), b"no data rows"),
        "binary": (b"\x00\x01\x02\xff\xfe", b"not"),
    }
    for name, (content, expect) in cases.items():
        r = upload(client, content)
        assert r.status_code == 400 and expect in r.data, name
    assert upload(client, b"a,b\n1,2\n", name="x.txt").status_code == 400
    with client.application.app_context():
        assert Batch.query.count() == 0 and Student.query.count() == 0


def test_csv_row_level_rejections_are_reported_not_silenced(client, sample_df):
    register(client)
    df = sample_df.head(6).copy().astype(object)
    df.loc[1, "course"] = 1            # invalid category
    df.loc[2, "age_at_enrollment"] = "x"
    df.loc[3, "gdp"] = ""
    df.loc[5, "student_id"] = df.loc[4, "student_id"]   # duplicate id
    r = upload(client, csv_bytes(df))
    assert r.status_code == 302
    with client.application.app_context():
        b = Batch.query.one()
        assert b.valid_rows == 2 and b.rejected_rows == 4 and b.total_rows == 6
        assert Student.query.count() == 2
        rows = {d["row"] for d in b.rejected_detail}
        assert rows == {2, 3, 4, 6}
    page = client.get(r.headers["Location"])
    assert b"rejected rows" in page.data


def test_validate_only_saves_nothing(client, sample_df):
    register(client)
    r = upload(client, csv_bytes(sample_df.head(5)), mode="validate")
    assert r.status_code == 200 and b"Nothing has been saved" in r.data
    with client.application.app_context():
        assert Batch.query.count() == 0


def test_users_cannot_see_each_others_data(db_uri, sample_df):
    app = make_app(db_uri)
    a, b = app.test_client(), app.test_client()
    register(a)
    register(b, email="b@example.com")
    r = upload(a, csv_bytes(sample_df.head(5)))
    loc = r.headers["Location"]
    assert a.get(loc).status_code == 200
    assert b.get(loc).status_code == 404                     # analyst B cannot open A's batch
    assert b.get(loc.replace("/batches/", "/batches/") + "/download.csv").status_code == 404
    assert b.get("/admin/users").status_code == 403           # B is not an admin
    assert a.get("/admin/users").status_code == 200
    assert b"HOLDOUT" not in b.get("/students").data
    with app.app_context():
        sid = Student.query.first().id
    assert b.get(f"/students/{sid}").status_code == 404
    assert b.post(f"/students/{sid}/delete").status_code == 404


def test_delete_student_and_account(client, sample_df):
    register(client)
    upload(client, csv_bytes(sample_df.head(3)))
    with client.application.app_context():
        sid = Student.query.first().id
    client.post(f"/students/{sid}/delete")
    with client.application.app_context():
        assert Student.query.count() == 2 and Prediction.query.count() == 2


def test_exports_are_generated_from_database(client, sample_df):
    register(client)
    upload(client, csv_bytes(sample_df.head(8)))
    for kind in ("students", "predictions", "high-risk"):
        r = client.get(f"/export/{kind}.csv")
        assert r.status_code == 200 and r.mimetype == "text/csv"
    assert client.get("/export/unknown.csv").status_code == 404


def test_csv_formula_injection_is_neutralised(client, sample_df):
    register(client)
    df = sample_df.head(2).copy()
    df.loc[0, "student_id"] = "=CMD"
    upload(client, csv_bytes(df))        # '=' is not an allowed id character -> row rejected
    with client.application.app_context():
        assert Batch.query.one().rejected_rows == 1
    from services.csv_service import safe_cell
    assert safe_cell("=1+1").startswith("'")


def test_error_pages_hide_internals(client):
    r = client.get("/definitely-missing")
    assert r.status_code == 404 and b"Traceback" not in r.data


def test_navbar_structure_and_theme_toggle(client):
    register(client)
    html = client.get("/dashboard").data.decode()
    assert html.count("<header") == 1 and 'class="navbar-main"' in html and 'class="navbar-actions"' in html
    nav = html.split('class="navbar-main"')[1].split("</nav>")[0]
    for label in ("Home", "Dashboard", "Predict", "Batch CSV", "Students", "History", "Analytics", "Model", "About"):
        assert f">{label}</a>" in nav, label
    actions = html.split('class="navbar-actions"')[1].split("</header>")[0]
    for label in ("Users", "Audit", "Profile", "Logout"):
        assert label in actions, label
    assert 'id="theme-toggle"' in html and 'aria-label="Toggle dark mode"' in html and ">Theme<" not in html


def test_navbar_hides_admin_links_for_analysts(db_uri):
    app = make_app(db_uri)
    a, b = app.test_client(), app.test_client()
    register(a)
    register(b, email="b@example.com")
    html = b.get("/dashboard").data.decode()
    assert ">Users<" not in html and ">Audit<" not in html and ">Logout<" in html


def test_about_page_developer_links(client):
    html = client.get("/about").data.decode()
    assert "Dipesh Vishnu Bante" in html
    assert 'href="mailto:dipeshbante31@gmail.com"' in html
    for url in ("https://github.com/dipeshvb31", "https://www.instagram.com/ok.dipesh/"):
        assert f'href="{url}" target="_blank" rel="noopener noreferrer"' in html


def test_static_assets_load(client):
    for path in ("/static/css/style.css", "/static/js/app.js", "/static/js/theme.js", "/static/js/charts.js"):
        assert client.get(path).status_code == 200, path
