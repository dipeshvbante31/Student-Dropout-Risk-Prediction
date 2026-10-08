"""Model-agnostic local explanation by occlusion.

For each input feature we replace its value by the training baseline (median / mode) and measure how the
predicted probability changes. A positive delta means the student's actual value raised the model's
estimate relative to a typical value. These are model-based indicators, not causal claims.
"""
import numpy as np


def local_explanation(predictor, record: dict, top_n: int = 5) -> dict:
    base_p = predictor.predict_proba([record])[0]
    variants = []
    for s in predictor.schema:
        alt = dict(record)
        alt[s["name"]] = s["baseline"]
        variants.append(alt)
    probs = np.array(predictor.predict_proba(variants))
    contribs = []
    for s, p in zip(predictor.schema, probs):
        if record[s["name"]] == s["baseline"]:
            continue
        label = s["label"] + (f" ({s['group'].split()[0].lower()} semester)" if "semester" in s["group"] else "")
        contribs.append({"feature": s["name"], "label": label, "value": record[s["name"]], "delta": float(base_p - p)})
    contribs.sort(key=lambda c: -abs(c["delta"]))
    up = [c for c in contribs if c["delta"] > 0.005][:top_n]
    down = [c for c in contribs if c["delta"] < -0.005][:top_n]
    return {"method": "occlusion vs training baseline", "increase": up, "decrease": down}
