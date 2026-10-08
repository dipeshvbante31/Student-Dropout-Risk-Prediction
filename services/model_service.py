import logging

from flask import current_app

from database.models import ModelVersion, db
from ml.predict import ModelUnavailable, Predictor
from services.audit import audit

log = logging.getLogger(__name__)
_cache: dict = {}


def get_predictor() -> Predictor:
    """Load the serialized production model once per process. Never trains."""
    path = current_app.config["MODEL_DIR"]
    if _cache.get("path") != path:
        _cache.clear()
        _cache["predictor"] = Predictor.load(__import__("pathlib").Path(path))
        _cache["path"] = path
    return _cache["predictor"]


def reset_cache():
    _cache.clear()


def active_model_version() -> ModelVersion:
    """Return the DB row for the loaded model, registering it (and auditing) on first use."""
    pred = get_predictor()
    mv = ModelVersion.query.filter_by(version=pred.version).first()
    if mv is None:
        from datetime import datetime
        m = pred.metadata
        ModelVersion.query.update({"is_active": False})
        mv = ModelVersion(version=pred.version, model_type=m["model_type"],
                          trained_at=datetime.fromisoformat(m["trained_at"]).replace(tzinfo=None),
                          dataset_name=m["dataset"]["name"], dataset_sha256=m["dataset"]["sha256"],
                          metrics={k: v for k, v in m["metrics"].items() if isinstance(v, float)},
                          config=m["config"], artifact_path=f"models/{pred.version}/model.joblib", is_active=True)
        db.session.add(mv)
        db.session.flush()
        audit("model_registered", f"version={pred.version}")
        db.session.commit()
        log.info("Registered model version %s", pred.version)
    return mv


def model_status() -> dict:
    try:
        p = get_predictor()
        return {"ok": True, "version": p.version}
    except ModelUnavailable as exc:
        return {"ok": False, "error": str(exc)}
