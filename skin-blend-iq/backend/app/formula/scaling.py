"""Formula scaling and batch calculator (expansion spec).

Internal standard unit: milliliters. Supports drop counts, US fluid
ounce presets, and custom mL, with studio-default or pigment-specific
drop volumes. Scaled formulas preserve the exact requested total volume;
per-ingredient rounding differences are reported, never hidden.
"""

from __future__ import annotations

ML_PER_US_FL_OZ = 29.5735
DEFAULT_DROP_VOLUME_ML = 0.05

VOLUME_PRESETS_ML = {
    "10_drops": None,  # resolved via drop volume
    "1/8_fl_oz": ML_PER_US_FL_OZ / 8,
    "1/4_fl_oz": ML_PER_US_FL_OZ / 4,
    "1/2_fl_oz": ML_PER_US_FL_OZ / 2,
    "1_fl_oz": ML_PER_US_FL_OZ,
    "2_fl_oz": ML_PER_US_FL_OZ * 2,
    "4_fl_oz": ML_PER_US_FL_OZ * 4,
}


def scale_to_volume(
    ratios: dict[str, float],
    total_ml: float,
    precision: int = 4,
) -> dict:
    """Scale master proportions to an exact total volume in mL.

    The last ingredient absorbs the rounding remainder so the printed
    total always matches the requested volume exactly; the per-ingredient
    rounding difference is reported.
    """
    if total_ml <= 0:
        raise ValueError("total_ml must be positive")
    total_ml = round(total_ml, precision)  # reconcile against the reported total
    s = sum(ratios.values())
    if s <= 0:
        raise ValueError("ratios must have positive sum")
    norm = {c: v / s for c, v in ratios.items() if v > 0}

    codes = sorted(norm, key=lambda c: norm[c], reverse=True)
    exact = {c: norm[c] * total_ml for c in codes}
    rounded = {c: round(exact[c], precision) for c in codes}
    drift = round(total_ml - sum(rounded.values()), precision + 2)
    last = codes[-1]
    rounded[last] = round(rounded[last] + drift, precision)

    return {
        "total_ml": round(total_ml, precision),
        "ingredients_ml": rounded,
        "rounding_differences_ml": {
            c: round(rounded[c] - exact[c], precision + 2) for c in codes
        },
    }


def drops_to_ml(
    drops: dict[str, int],
    drop_volume_ml: float = DEFAULT_DROP_VOLUME_ML,
    per_pigment_drop_volume: dict[str, float] | None = None,
) -> dict:
    per = per_pigment_drop_volume or {}
    ml = {
        c: round(n * per.get(c, drop_volume_ml), 6) for c, n in drops.items() if n > 0
    }
    return {"ingredients_ml": ml, "total_ml": round(sum(ml.values()), 6)}


def ml_to_drops_estimate(
    total_ml: float, drop_volume_ml: float = DEFAULT_DROP_VOLUME_ML
) -> int:
    return max(1, round(total_ml / drop_volume_ml))


def coverage_estimate_ml(
    area_sq_cm: float,
    ml_per_sq_cm: float,
    passes: int = 1,
    texture_factor: float = 1.0,
    reserve_factor: float = 1.2,
) -> float:
    """estimated volume = area x artist volume/area x passes x texture x reserve."""
    if min(area_sq_cm, ml_per_sq_cm, passes, texture_factor, reserve_factor) <= 0:
        raise ValueError("all coverage inputs must be positive")
    return round(area_sq_cm * ml_per_sq_cm * passes * texture_factor * reserve_factor, 4)
