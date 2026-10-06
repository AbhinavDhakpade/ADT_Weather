"""
advisory/ml/inference.py

Loads trained models (if present) and exposes simple predict_* functions used by
the API views. If a model hasn't been trained yet, these functions return None
rather than raising, so the API degrades gracefully to deterministic-only output.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "trained_models"


@lru_cache(maxsize=1)
def _load_disease_model():
    path = MODEL_DIR / "disease_risk_model.joblib"
    if not path.exists():
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def _load_irrigation_model():
    path = MODEL_DIR / "irrigation_model.joblib"
    if not path.exists():
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def _load_yield_model():
    path = MODEL_DIR / "yield_model.joblib"
    if not path.exists():
        return None
    return joblib.load(path)


def clear_model_cache():
    """Call after retraining so the API picks up fresh models without a restart."""
    _load_disease_model.cache_clear()
    _load_irrigation_model.cache_clear()
    _load_yield_model.cache_clear()


def predict_disease_risk(
    disease_type: str,
    temp_max_c: float,
    temp_min_c: float,
    humidity_pct: float,
    rainfall_week_mm: float,
    leaf_wetness_hrs: float,
    vpd_kpa: float,
    gdd_cumulative: float,
) -> dict | None:
    """
    Returns {'risk_probability': 0-1 float, 'risk_pct': 0-100 int, 'confidence': 0-1}
    or None if the model isn't trained / disease_type unknown to the model.
    """
    bundle = _load_disease_model()
    if bundle is None:
        return None

    models = bundle["models"]
    model = models.get(disease_type)
    if model is None:
        return None

    temp_mean_c = (temp_max_c + temp_min_c) / 2
    features = np.array([[
        temp_max_c, temp_min_c, temp_mean_c, humidity_pct,
        rainfall_week_mm, leaf_wetness_hrs, vpd_kpa, gdd_cumulative,
    ]])

    proba = model.predict_proba(features)[0]
    # proba is [P(class=0), P(class=1)] — class 1 = "favorable for outbreak"
    risk_prob = float(proba[1]) if len(proba) > 1 else float(proba[0])
    # Confidence: how far the prediction is from the 50/50 uncertainty point
    confidence = float(abs(risk_prob - 0.5) * 2)

    return {
        "risk_probability": round(risk_prob, 4),
        "risk_pct": round(risk_prob * 100),
        "confidence": round(confidence, 3),
    }


def predict_irrigation_requirement(
    soil_type: str,
    crop_stage: str,
    et0_mm: float,
    rainfall_week_mm: float,
    temp_mean_c: float,
    humidity_pct: float,
    vpd_kpa: float,
) -> dict | None:
    bundle = _load_irrigation_model()
    if bundle is None:
        return None

    model = bundle["model"]
    encoder = bundle["encoder"]

    cat_features = encoder.transform(pd.DataFrame([[soil_type, crop_stage]], columns=["soil_type", "crop_stage"]))
    num_features = np.array([[et0_mm, rainfall_week_mm, temp_mean_c, humidity_pct, vpd_kpa]])
    X = np.hstack([num_features, cat_features])

    prediction = float(model.predict(X)[0])
    # Estimate prediction spread from the ensemble's individual trees as a simple
    # uncertainty signal (standard RandomForest technique)
    tree_preds = np.array([t.predict(X)[0] for t in model.estimators_])
    std = float(tree_preds.std())

    return {
        "requirement_l_plant": round(max(0.0, prediction), 1),
        "uncertainty_l_plant": round(std, 2),
    }


def predict_yield(
    gdd_at_harvest: float,
    avg_disease_risk_pct: float,
    irrigation_adequacy_pct: float,
    soil_type: str,
) -> dict | None:
    bundle = _load_yield_model()
    if bundle is None:
        return None

    model = bundle["model"]
    encoder = bundle["encoder"]

    cat_features = encoder.transform(pd.DataFrame([[soil_type]], columns=["soil_type"]))
    num_features = np.array([[gdd_at_harvest, avg_disease_risk_pct, irrigation_adequacy_pct]])
    X = np.hstack([num_features, cat_features])

    prediction = float(model.predict(X)[0])

    return {
        "yield_t_ha": round(prediction, 1),
    }


def models_available() -> dict:
    """Quick status check used by a health-check endpoint / admin view."""
    return {
        "disease_risk": _load_disease_model() is not None,
        "irrigation": _load_irrigation_model() is not None,
        "yield": _load_yield_model() is not None,
    }
