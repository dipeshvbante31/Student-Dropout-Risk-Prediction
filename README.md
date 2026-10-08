# Student Dropout Risk: a Python machine-learning web application

Flask + scikit-learn application that estimates the risk of student dropout from enrollment, financial and first-year academic data. Supports single-student prediction and CSV batch prediction, stores everything in SQLAlchemy (SQLite for development, PostgreSQL for production), and exposes dashboard, analytics, model-performance and monitoring pages. Frontend is plain HTML, CSS and vanilla JavaScript (no React or other framework).

> The output is an **estimated risk** for decision support, not a statement that a student will drop out. Never use it for disciplinary, admission or expulsion decisions.

## Features
- Individual prediction form with probability, risk level (configurable thresholds), and per-student contributing factors
- **CSV batch prediction**: template download, strict schema validation, validate-only mode, batch run, searchable/sortable/filterable results, results CSV download, rejected-rows report, persisted batch history
- Student management: search, filter, pagination, edit and re-predict (history is kept), delete
- Dashboard and analytics computed from the database (empty states when there is no data)
- Model page: real held-out metrics, model comparison, confusion matrix, ROC curve, permutation importance, group-wise check by gender, basic input-drift monitoring, model versions
- Authentication (Flask-Login, hashed passwords, login lockout), roles (admin / analyst), per-user data isolation, audit trail, CSRF protection, security headers, data deletion
- `/health` endpoint (database + model), Gunicorn, Docker, Alembic migrations

## ML methodology
**Dataset:** *Predict Students' Dropout and Academic Success*, UCI Machine Learning Repository (id 697), Realinho, Machado, Baptista and Martins (2022), *Data* 7(11):146, licence CC BY 4.0. Source page: https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success. 4,424 students, 36 features, 0 missing values, 0 duplicate rows. Raw classes: Graduate 2,209, Dropout 1,421, Enrolled 794.
The file in `data/raw/data.csv` was downloaded from a public GitHub mirror because the UCI host was unreachable from the build environment. Its SHA-256 is `19737f02127e85ef29af536e46888a7721b6c530c3e1c6aedfbb09109c030a71`; verify it against a fresh UCI download before publishing results.

**Prediction problem (binary):** target = 1 when the raw outcome is *Dropout*; 0 for *Graduate* and *Enrolled* (enrolled students have not finished, so they are treated as not dropped out yet). Dropout rate: 32.1% in the training split.

**Pipeline** (one scikit-learn `Pipeline`, serialized as a whole and reused for form and CSV predictions):
`FeatureEngineer` (approval rates, evaluation success, totals, grade/approval change between semesters; ratios are 0 when the denominator is 0) -> `ColumnTransformer` (median impute + standard scaling for numeric; most-frequent impute + one-hot for 9 coded categorical fields) -> classifier. Class imbalance is handled with balanced class weights. Seed 42 everywhere.

**Evaluation protocol:** stratified 80/20 split. Models are compared with 5-fold CV on the 80% training part; the winner is chosen by CV F1 for the dropout class (ROC-AUC as tie-break); the 20% test set is scored once for reporting.

| Model | CV F1 | CV ROC-AUC | Test acc. | Test precision | Test recall | Test F1 | Test ROC-AUC |
|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.786 | 0.920 | 0.878 | 0.791 | 0.842 | 0.816 | 0.933 |
| Decision Tree | 0.761 | 0.892 | 0.862 | 0.748 | 0.859 | 0.800 | 0.920 |
| Random Forest | 0.773 | 0.915 | 0.881 | 0.823 | 0.803 | 0.813 | 0.931 |
| Gradient Boosting | 0.792 | 0.918 | 0.887 | 0.813 | 0.842 | 0.827 | 0.938 |

**Selected: Gradient Boosting** (version `gradient-boosting-20261007-fe58760a`). Held-out test: accuracy 0.887, precision 0.813, recall 0.842, F1 0.827, ROC-AUC 0.938. Confusion matrix: TN 546, FP 55, FN 45, TP 239. Differences between the top models are small; recall and F1 for dropouts mattered more than accuracy.

**Most important features** (permutation importance, drop in test ROC-AUC):
1. Units approved (second semester) (0.167)
2. Tuition fees up to date (0.031)
3. Units approved (first semester) (0.030)
4. Units enrolled (second semester) (0.017)
5. Units enrolled (first semester) (0.011)
6. Course (0.008)
7. Age at enrollment (0.005)
8. Unemployment rate (%) (0.005)

**EDA findings** (computed from the data by `ml/eda.py`; associations, not causes):
- Class balance: 2209 graduates, 1421 dropouts and 794 still enrolled; the binary dropout rate is 32.1%.
- Students whose tuition fees are not up to date have a 87% dropout rate versus 25% for those up to date.
- Students with no approved units in the 2nd semester have a 84% dropout rate versus 8% for those with 7 or more approved units.
- Scholarship holders: 12% dropout; non-holders: 39%.
- Students aged 30+ at enrollment: 54% dropout versus 21% for those aged 19 or younger.
- These are associations in historical data from one institution, not evidence of causation.

**Explanations:** global permutation importance, plus a per-student occlusion analysis (each value replaced by a training baseline; change in probability reported). Wording is "contributed to the model's estimate", never "caused".

## Limitations
- One institution and period; accuracy on other populations is unknown and likely lower.
- Uses first and second semester results, so it is most useful after the first year has started.
- Demographic fields in the dataset (gender, nationality, marital status, etc.) are model inputs. The model page shows a gender group check, which does not prove fairness.
- Risk levels (low < 40%, medium < 70%, high otherwise; configurable) are communication thresholds, not statistical standards.
- Drift monitoring is basic (out-of-range inputs, mean-prediction shift, rejection rate), not full drift detection.
- Qualification, occupation and nationality fields are shown as UCI codes, not names.

## Architecture
```
Browser (HTML/CSS/vanilla JS)  ->  Flask routes  ->  services  ->  ml.Predictor (saved pipeline)  
                                        |                              
                                  SQLAlchemy ORM  ->  SQLite (dev) / PostgreSQL (prod), Alembic migrations
```
```
app.py, wsgi.py, config.py          application factory, WSGI entry point, environment config
ml/                                  preprocess.py, features.py, eda.py, train.py, predict.py, explain.py, labels.py
models/<version>/                    model.joblib + metadata.json (metrics, schema, importance); models/current.json
data/raw/data.csv                    UCI dataset;  data/processed/holdout_sample.csv = 40 real held-out rows for trying CSV upload
database/models.py, migrations/      SQLAlchemy models, Alembic
services/                            csv_service, batch_service, prediction_service, model_service, analytics_service, audit
routes/                              main, auth, predict, students, batch, insights (analytics, model, admin)
templates/, static/                  Jinja2 pages, CSS, vanilla JS (SVG charts, no external libraries)
tests/                               pytest suite (26 tests)
reports/model_report.md              written by ml/train.py
```
**Database:** `user`, `model_version`, `batch`, `student` (unique per owner + student_ref; stores the exact model input), `prediction` (never overwritten; linked to student, optional batch, and model version), `audit_log`.

## Quick start (local, SQLite)
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional for local use
export FLASK_APP=wsgi
flask db upgrade                # creates instance/app.db
python ml/train.py              # optional: models/ already contains a trained model
flask run                       # http://127.0.0.1:5000 ; first registered user becomes admin
python -m pytest                # run tests
```
Try batch prediction by uploading `data/processed/holdout_sample.csv` on the **Batch CSV** page.

## CSV format
Download the template from the Batch page (`/batch/template.csv`); it is generated from the model's schema, so it can never drift. Columns: optional `student_id` plus the 36 feature columns. Policy: unreadable file, empty file, missing/unexpected/duplicate columns or too many rows reject the **whole file**; a bad row (missing or non-numeric value, code not seen in training, non-integer where an integer is required, value outside valid range, duplicate student_id) is **rejected individually and reported**, never altered or imputed. Values outside the training range but still valid are accepted and flagged. Uploaded files are processed in memory and not kept. Limit: 5 MB and 5,000 rows (configurable).

## Environment variables
See `.env.example`. Required in production: `SECRET_KEY`, `DATABASE_URL`. `APP_ENV=production` enables secure cookies and HSTS and refuses to start without a secret key.

## Production deployment
**Docker Compose (app + PostgreSQL):**
```bash
cat > .env <<'EOT'
SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
POSTGRES_PASSWORD=choose-a-strong-password
EOT
docker compose up --build        # migrations run on start; http://localhost:8000
```
(Write the real values into `.env`; the heredoc above shows the keys.) Behind HTTPS, set `SESSION_COOKIE_SECURE=true` (the compose file sets false only for plain-HTTP localhost).

**Render:** push to GitHub, create a Blueprint from `render.yaml` (web service + PostgreSQL). **Railway / other:** set `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL` and use the `Procfile` command `flask db upgrade && gunicorn wsgi:app`.

**Retraining:** `python ml/train.py` creates a new `models/<version>/` and updates `models/current.json`. The app registers the new version on first use; old predictions keep pointing at the version that produced them. Models are never trained on upload or at request time.

## Security and privacy
Password hashing (Werkzeug), CSRF tokens on every form, HttpOnly/SameSite session cookies, login lockout after 5 failures in 15 minutes, role checks and per-user data scoping on the server (other users' records return 404), parameterised ORM queries, upload type/size/row limits, CSV formula-injection neutralisation on export, CSP and other security headers, no stack traces for users, audit trail without passwords or student values. Privacy and cookie pages describe actual behaviour; no compliance certification is claimed. Real student data should only be processed on a deployment you have secured and are authorised to use.

## Future improvements
Named lookup for qualification/occupation codes, calibration and threshold tuning with institutional data, fairness audits across more groups, scheduled retraining with champion/challenger comparison, email notifications for high-risk students, rate limiting via a shared store.
