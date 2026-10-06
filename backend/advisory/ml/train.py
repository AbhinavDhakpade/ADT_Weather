"""
advisory/ml/train.py

Trains and serializes AgriAura's three ML models:
  1. Disease risk classifier   — RandomForestClassifier (+ predict_proba for risk %)
  2. Irrigation requirement    — RandomForestRegressor (L/plant)
  3. Yield prediction          — GradientBoostingRegressor (t/ha)

Consistent with AgriAura's established architecture: these models are a *second
opinion* layered on top of deterministic agronomy (GDD/VPD/ET0 stay closed-form
equations in weather_service.py). ML is used only where the relationship is
genuinely uncertain — disease outbreak likelihood, irrigation timing/quantity,
and yield — never for the physics itself.

Run directly:
    python manage.py shell -c "from advisory.ml.train import train_all; train_all()"
or via the management command:
    python manage.py train_ml_models
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder

from .data_generation import (
    generate_disease_training_frame,
    generate_irrigation_training_frame,
    generate_yield_training_frame,
)

MODEL_DIR = Path(__file__).resolve().parent / "trained_models"
MODEL_DIR.mkdir(exist_ok=True)

DISEASE_FEATURES = [
    "temp_max_c", "temp_min_c", "temp_mean_c", "humidity_pct",
    "rainfall_week_mm", "leaf_wetness_hrs", "vpd_kpa", "gdd_cumulative",
]
IRRIGATION_NUMERIC_FEATURES = ["et0_mm", "rainfall_week_mm", "temp_mean_c", "humidity_pct", "vpd_kpa"]
YIELD_FEATURES = ["gdd_at_harvest", "avg_disease_risk_pct", "irrigation_adequacy_pct"]


def _save_metrics(name: str, metrics: dict):
    path = MODEL_DIR / f"{name}_metrics.json"
    path.write_text(json.dumps(metrics, indent=2))


# ---------------------------------------------------------------------------
# 1. Disease risk classifier — one model per disease_type, sharing one file
# ---------------------------------------------------------------------------

def train_disease_model(n_samples: int = 6000) -> dict:
    df = generate_disease_training_frame(n_samples)

    models = {}
    metrics = {}
    for disease_type in df["disease_type"].unique():
        subset = df[df["disease_type"] == disease_type]
        X = subset[DISEASE_FEATURES].values
        y = subset["risk_label"].values

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        clf = RandomForestClassifier(
            n_estimators=80, max_depth=9, min_samples_leaf=5, random_state=42, n_jobs=-1
        )
        clf.fit(X_train, y_train)

        y_pred = clf.predict(X_test)
        y_proba = clf.predict_proba(X_test)[:, 1]
        acc = accuracy_score(y_test, y_pred)
        try:
            auc = roc_auc_score(y_test, y_proba)
        except ValueError:
            auc = None

        models[disease_type] = clf
        metrics[disease_type] = {"accuracy": round(float(acc), 4), "roc_auc": round(float(auc), 4) if auc else None}

    joblib.dump({"models": models, "features": DISEASE_FEATURES}, MODEL_DIR / "disease_risk_model.joblib")
    _save_metrics("disease_risk", metrics)
    return metrics


# ---------------------------------------------------------------------------
# 2. Irrigation requirement regressor
# ---------------------------------------------------------------------------

def train_irrigation_model(n_samples: int = 5000) -> dict:
    df = generate_irrigation_training_frame(n_samples)

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    cat_features = encoder.fit_transform(df[["soil_type", "crop_stage"]])
    num_features = df[IRRIGATION_NUMERIC_FEATURES].values
    X = np.hstack([num_features, cat_features])
    y = df["requirement_l_plant"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    reg = RandomForestRegressor(n_estimators=100, max_depth=10, min_samples_leaf=4, random_state=42, n_jobs=-1)
    reg.fit(X_train, y_train)

    y_pred = reg.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    joblib.dump(
        {"model": reg, "encoder": encoder, "numeric_features": IRRIGATION_NUMERIC_FEATURES},
        MODEL_DIR / "irrigation_model.joblib",
    )
    metrics = {"mae_l_per_plant": round(float(mae), 3), "r2": round(float(r2), 4)}
    _save_metrics("irrigation", metrics)
    return metrics


# ---------------------------------------------------------------------------
# 3. Yield prediction regressor
# ---------------------------------------------------------------------------

def train_yield_model(n_samples: int = 4000) -> dict:
    df = generate_yield_training_frame(n_samples)

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    cat_features = encoder.fit_transform(df[["soil_type"]])
    num_features = df[YIELD_FEATURES].values
    X = np.hstack([num_features, cat_features])
    y = df["yield_t_ha"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    reg = GradientBoostingRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05, random_state=42
    )
    reg.fit(X_train, y_train)

    y_pred = reg.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    joblib.dump(
        {"model": reg, "encoder": encoder, "numeric_features": YIELD_FEATURES},
        MODEL_DIR / "yield_model.joblib",
    )
    metrics = {"mae_t_per_ha": round(float(mae), 3), "r2": round(float(r2), 4)}
    _save_metrics("yield", metrics)
    return metrics


def train_all() -> dict:
    results = {
        "disease_risk": train_disease_model(),
        "irrigation": train_irrigation_model(),
        "yield": train_yield_model(),
    }
    return results
