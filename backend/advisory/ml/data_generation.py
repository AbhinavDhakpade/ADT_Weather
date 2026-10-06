"""
advisory/ml/data_generation.py

Generates training data for AgriAura's ML models.

IMPORTANT — data provenance: AgriAura does not yet have a historical log of real
field outcomes (confirmed disease incidents, actual irrigation given vs. needed,
measured yields) tied to weather records. Until that log exists, these models are
trained on **physically-grounded synthetic data**: weather conditions are sampled
across realistic ranges for Baramati sugarcane cultivation, and labels are derived
from the same agronomic rules already encoded in the Excel reference data and the
deterministic physics in weather_service.py — plus realistic noise so the models
learn smooth probability surfaces instead of memorizing hard if/else boundaries.

This is a standard, honest way to bootstrap an ML layer in a domain where the
relationships are well understood (e.g. "fungal disease risk rises with humidity
and leaf wetness") but logged ground-truth outcomes don't exist yet. The model
schema and training pipeline below are written so that swapping in a CSV of real
field-confirmed outcomes (`backend/advisory/ml/field_data/*.csv`) requires no
code changes to the model classes themselves — only to `load_training_frame()`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG_SEED = 42


def _sample_uniform(rng, low, high, n):
    return rng.uniform(low, high, n)


def generate_weather_samples(n_samples: int = 6000, seed: int = RNG_SEED) -> pd.DataFrame:
    """
    Sample n_samples synthetic daily weather conditions across the realistic range
    for Baramati's sugarcane-growing climate (roughly: 20-42°C, 35-100% RH,
    0-60mm rainfall/week, 0-5000 cumulative GDD at base 18°C).
    """
    rng = np.random.default_rng(seed)

    temp_max = _sample_uniform(rng, 24, 42, n_samples)
    temp_min = temp_max - _sample_uniform(rng, 4, 12, n_samples)
    temp_mean = (temp_max + temp_min) / 2
    humidity = _sample_uniform(rng, 35, 100, n_samples)
    rainfall_week = rng.gamma(shape=1.5, scale=8.0, size=n_samples)
    rainfall_week = np.clip(rainfall_week, 0, 90)
    leaf_wetness = np.clip(humidity / 5 + rng.normal(0, 2, n_samples), 0, 24)
    gdd_cumulative = _sample_uniform(rng, 0, 5500, n_samples)
    soil_moisture = _sample_uniform(rng, 10, 60, n_samples)

    # Tetens VPD from temp/humidity (same equation as weather_service.py, kept in
    # sync deliberately so ML features match the deterministic features the app
    # actually computes at inference time)
    es_max = 0.6108 * np.exp((17.27 * temp_max) / (temp_max + 237.3))
    es_min = 0.6108 * np.exp((17.27 * temp_min) / (temp_min + 237.3))
    es = (es_max + es_min) / 2
    ea = es * (humidity / 100.0)
    vpd = np.clip(es - ea, 0, None)

    return pd.DataFrame(
        {
            "temp_max_c": temp_max,
            "temp_min_c": temp_min,
            "temp_mean_c": temp_mean,
            "humidity_pct": humidity,
            "rainfall_week_mm": rainfall_week,
            "leaf_wetness_hrs": leaf_wetness,
            "vpd_kpa": vpd,
            "gdd_cumulative": gdd_cumulative,
            "soil_moisture_pct": soil_moisture,
        }
    )


# ---------------------------------------------------------------------------
# Disease risk classifier training data
# ---------------------------------------------------------------------------

# Favorable-condition centers per disease_type, derived from the Excel reference
# ranges (avg_temp_c, relative_humidity_pct, vpd_kpa, leaf_wetness_hrs columns).
DISEASE_TYPE_PROFILE = {
    "fungal": dict(temp_opt=29, temp_tol=5, hum_opt=90, hum_tol=10, vpd_opt=0.6, vpd_tol=0.5, wetness_opt=16, wetness_tol=6),
    "bacterial": dict(temp_opt=30, temp_tol=5, hum_opt=85, hum_tol=10, vpd_opt=0.8, vpd_tol=0.5, wetness_opt=10, wetness_tol=6),
    "viral": dict(temp_opt=28, temp_tol=6, hum_opt=70, hum_tol=15, vpd_opt=1.2, vpd_tol=0.6, wetness_opt=6, wetness_tol=5),
    "phytoplasma": dict(temp_opt=30, temp_tol=6, hum_opt=70, hum_tol=15, vpd_opt=1.2, vpd_tol=0.6, wetness_opt=6, wetness_tol=5),
    "pest": dict(temp_opt=32, temp_tol=6, hum_opt=65, hum_tol=15, vpd_opt=1.5, vpd_tol=0.7, wetness_opt=4, wetness_tol=4),
}


def _gaussian_suitability(value, opt, tol):
    return np.exp(-0.5 * ((value - opt) / tol) ** 2)


def generate_disease_training_frame(n_samples: int = 6000, seed: int = RNG_SEED) -> pd.DataFrame:
    """
    For each weather sample, generate one labeled row per disease_type, where the
    label is a noisy probability that conditions favor that disease type, built
    from a Gaussian suitability function around each type's known optimal
    temp/humidity/VPD/leaf-wetness profile (a standard agroclimatic modeling
    approach for pest/disease forecasting).
    """
    weather = generate_weather_samples(n_samples, seed)
    rng = np.random.default_rng(seed + 1)

    rows = []
    for disease_type, profile in DISEASE_TYPE_PROFILE.items():
        temp_s = _gaussian_suitability(weather["temp_mean_c"], profile["temp_opt"], profile["temp_tol"])
        hum_s = _gaussian_suitability(weather["humidity_pct"], profile["hum_opt"], profile["hum_tol"])
        vpd_s = _gaussian_suitability(weather["vpd_kpa"], profile["vpd_opt"], profile["vpd_tol"])
        wet_s = _gaussian_suitability(weather["leaf_wetness_hrs"], profile["wetness_opt"], profile["wetness_tol"])

        # Weighted combination — humidity and leaf wetness dominate fungal/bacterial
        # risk in the literature; temp/VPD dominate pest risk
        if disease_type == "pest":
            suitability = 0.45 * temp_s + 0.20 * hum_s + 0.25 * vpd_s + 0.10 * wet_s
        else:
            suitability = 0.20 * temp_s + 0.35 * hum_s + 0.15 * vpd_s + 0.30 * wet_s

        noise = rng.normal(0, 0.08, n_samples)
        risk_prob = np.clip(suitability + noise, 0, 1)
        # Binary label: "outbreak-favorable conditions" if probability crosses 0.5,
        # with the probability itself kept for reference/calibration checks
        label = (risk_prob > 0.5).astype(int)

        chunk = weather.copy()
        chunk["disease_type"] = disease_type
        chunk["risk_probability"] = risk_prob
        chunk["risk_label"] = label
        rows.append(chunk)

    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# Irrigation requirement regressor training data
# ---------------------------------------------------------------------------

SOIL_WATER_HOLDING = {
    # mm of plant-available water per unit root depth, relative scale used only
    # to differentiate soils in the synthetic generator (not an absolute value)
    "Sandy": 0.6,
    "Loamy": 1.0,
    "Clay": 1.4,
    "Black Cotton": 1.3,
    "Red Soil": 0.8,
    "Laterite": 0.55,
    "Any Soil": 1.0,
}

# Single crop coefficients (Kc) for sugarcane growth stages now live in one
# place — advisory/agronomy_constants.py — so the deterministic irrigation rule
# and this ML training generator always agree. ETc = ET0 * Kc (FAO-56).
from advisory.agronomy_constants import CROP_STAGE_KC  # noqa: E402


def generate_irrigation_training_frame(n_samples: int = 5000, seed: int = RNG_SEED) -> pd.DataFrame:
    """
    Synthetic irrigation requirement (L/plant/week) labels derived from a standard
    water-balance equation: net requirement = ETc - effective rainfall, scaled by
    soil water-holding capacity, then converted to a per-plant volume. Noise is
    added to represent field variability (microclimate, drainage, plant spacing).
    """
    rng = np.random.default_rng(seed + 2)
    n = n_samples

    soils = list(SOIL_WATER_HOLDING.keys())
    stages = list(CROP_STAGE_KC.keys())

    soil_choice = rng.choice(soils, n)
    stage_choice = rng.choice(stages, n)

    et0 = _sample_uniform(rng, 2.5, 6.5, n)
    rainfall_week = rng.gamma(shape=1.5, scale=7.0, size=n)
    rainfall_week = np.clip(rainfall_week, 0, 80)
    temp_mean = _sample_uniform(rng, 22, 38, n)
    humidity = _sample_uniform(rng, 40, 95, n)
    vpd = np.clip(0.8 + (temp_mean - 28) * 0.05 - (humidity - 70) * 0.01 + rng.normal(0, 0.15, n), 0.1, 3.0)

    kc = np.array([CROP_STAGE_KC[s] for s in stage_choice])
    whc = np.array([SOIL_WATER_HOLDING[s] for s in soil_choice])

    etc_week = et0 * kc * 7
    effective_rainfall = rainfall_week * 0.8  # standard 80% effectiveness assumption
    net_deficit_mm = np.clip(etc_week - effective_rainfall, 0, None)

    # Convert mm deficit to L/plant: soil with higher water-holding capacity buffers
    # more of the deficit, so less irrigation is needed per plant
    requirement_l_plant = np.clip((net_deficit_mm / whc) * 0.45 + rng.normal(0, 1.2, n), 0, 40)

    return pd.DataFrame(
        {
            "soil_type": soil_choice,
            "crop_stage": stage_choice,
            "et0_mm": et0,
            "rainfall_week_mm": rainfall_week,
            "temp_mean_c": temp_mean,
            "humidity_pct": humidity,
            "vpd_kpa": vpd,
            "soil_whc": whc,
            "kc": kc,
            "requirement_l_plant": requirement_l_plant,
        }
    )


# ---------------------------------------------------------------------------
# Yield prediction regressor training data
# ---------------------------------------------------------------------------

def generate_yield_training_frame(n_samples: int = 4000, seed: int = RNG_SEED) -> pd.DataFrame:
    """
    Synthetic yield (t/ha) labels for Co 86032 sugarcane, built from a baseline
    potential yield reduced by GDD adequacy, disease pressure, and irrigation
    adequacy — reflecting the established crop-stress-multiplier modeling
    approach used in agronomic yield forecasting (yield = potential * f(GDD) *
    f(disease) * f(water)), with realistic noise for field variability.
    """
    rng = np.random.default_rng(seed + 3)
    n = n_samples

    base_potential_t_ha = 95.0  # well-managed Co 86032 ceiling yield

    gdd_at_harvest = _sample_uniform(rng, 3000, 5500, n)
    # Yield response to GDD: rises then plateaus past ~4800 GDD (maturity ceiling)
    gdd_factor = np.clip(gdd_at_harvest / 4800, 0.5, 1.05)

    avg_disease_risk_pct = _sample_uniform(rng, 5, 85, n)
    disease_factor = np.clip(1 - (avg_disease_risk_pct / 100) * 0.55, 0.35, 1.0)

    irrigation_adequacy_pct = _sample_uniform(rng, 30, 100, n)
    water_factor = np.clip(0.5 + (irrigation_adequacy_pct / 100) * 0.5, 0.5, 1.0)

    soil_quality = rng.choice(["Black Cotton", "Loamy", "Clay", "Sandy", "Red Soil", "Laterite"], n)
    soil_factor_map = {"Black Cotton": 1.0, "Loamy": 0.97, "Clay": 0.93, "Red Soil": 0.85, "Sandy": 0.78, "Laterite": 0.75}
    soil_factor = np.array([soil_factor_map[s] for s in soil_quality])

    noise = rng.normal(1.0, 0.05, n)

    yield_t_ha = np.clip(
        base_potential_t_ha * gdd_factor * disease_factor * water_factor * soil_factor * noise,
        20,
        110,
    )

    return pd.DataFrame(
        {
            "gdd_at_harvest": gdd_at_harvest,
            "avg_disease_risk_pct": avg_disease_risk_pct,
            "irrigation_adequacy_pct": irrigation_adequacy_pct,
            "soil_type": soil_quality,
            "yield_t_ha": yield_t_ha,
        }
    )
