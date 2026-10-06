"""
Central agronomy constants for AgriAura (single source of truth).

Sugarcane (Co 86032) crop coefficients — single-Kc approach, used directly in
the deterministic irrigation rule:

        ETc = ET0 * Kc

Values are taken from ET_and_Kc.docx (FAO-56, sugarcane): Kc_ini = 0.15,
Kc_mid = 1.20, Kc_end = 0.70. These three are used as-is in ETc = ET0 * Kc
(single Kc only — no separate Ke / dual-coefficient step). The intermediate
project growth stages are filled in along the FAO-56 linear ramps between the
initial, mid and end anchors.

Stage names match the CropGrowthStage rows seeded in seed_data.py
(Sprouting / Tillering / Grand Growth / Maturity / Harvest Ready), plus
"Vegetative" and "Any" which the ML training generator uses.
"""

# Single crop coefficient (Kc) per growth stage — values from ET_and_Kc.docx.
#   Sprouting     = Kc_ini  (0.15, exact from doc)
#   Grand Growth  = Kc_mid  (1.20, exact from doc)
#   Harvest Ready = Kc_end  (0.70, exact from doc)
# Tillering / Vegetative / Maturity are interpolated along the FAO-56 ramps.
CROP_STAGE_KC = {
    "Sprouting":     0.15,   # initial stage (Kc_ini, from doc)
    "Tillering":     0.50,   # crop development (ramp ini -> mid)
    "Vegetative":    0.90,   # late development (ramp toward mid)
    "Grand Growth":  1.20,   # mid-season (Kc_mid, from doc)
    "Maturity":      0.95,   # late season (ramp mid -> end)
    "Harvest Ready": 0.70,   # end of season (Kc_end, from doc)
    "Any":           0.90,   # fallback when stage is unknown
}

# Fallback Kc used when a stage name is not recognised.
DEFAULT_KC = 0.90

# Fraction of weekly rainfall assumed to be usable by the crop (FAO effective
# rainfall assumption). Kept here so the deterministic rule and the ML training
# generator stay consistent.
EFFECTIVE_RAINFALL_FRACTION = 0.80


def kc_for_stage(crop_stage: str) -> float:
    """Return the single crop coefficient (Kc) for a growth stage."""
    return CROP_STAGE_KC.get(crop_stage, DEFAULT_KC)
