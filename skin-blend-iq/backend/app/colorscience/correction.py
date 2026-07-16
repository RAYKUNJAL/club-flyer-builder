"""Reference-card color correction (spec section 7, steps 4-6).

The artist marks the reference-card patches in the captured image. From
the observed patch RGBs and the card's known reference values we fit a
linear correction in linear-RGB space by least squares, apply it, and
report the residual (mean CIEDE2000 across card patches after
correction). The residual is stored with every calibrated measurement;
a high residual fails the calibration gate.
"""

from __future__ import annotations

import numpy as np

from .convert import (
    lab_to_srgb,
    linear_to_srgb,
    srgb_to_lab,
    srgb_to_linear,
)
from .deltae import delta_e_2000

MAX_CORRECTION_RESIDUAL = 3.0  # mean ΔE00 across card patches
MIN_CARD_PATCHES = 4


def _to_linear(rgb_rows: np.ndarray) -> np.ndarray:
    v = np.vectorize(srgb_to_linear)
    return v(np.clip(rgb_rows / 255.0, 0.0, 1.0))


def _to_srgb255(lin_rows: np.ndarray) -> np.ndarray:
    v = np.vectorize(linear_to_srgb)
    return v(lin_rows) * 255.0


def fit_correction(
    observed_rgb: list[list[float]], reference_lab: list[list[float]]
) -> dict:
    """Fit a 3x4 affine correction from observed sRGB to reference colors.

    observed_rgb: card patch medians measured in the image (sRGB 0-255).
    reference_lab: the card's known L*a*b* values for the same patches.
    Returns the matrix and the post-correction residual.
    """
    if len(observed_rgb) < MIN_CARD_PATCHES:
        raise ValueError(
            f"Need at least {MIN_CARD_PATCHES} card patches, got {len(observed_rgb)}"
        )
    if len(observed_rgb) != len(reference_lab):
        raise ValueError("observed and reference patch counts differ")

    obs_lin = _to_linear(np.asarray(observed_rgb, dtype=np.float64))
    ref_rgb = np.asarray([lab_to_srgb(tuple(lab)) for lab in reference_lab])
    ref_lin = _to_linear(ref_rgb)

    ones = np.ones((obs_lin.shape[0], 1))
    x = np.hstack([obs_lin, ones])  # n x 4
    matrix, *_ = np.linalg.lstsq(x, ref_lin, rcond=None)  # 4 x 3

    corrected = np.clip(x @ matrix, 0.0, 1.0)
    corrected_rgb = _to_srgb255(corrected)
    residuals = [
        delta_e_2000(srgb_to_lab(tuple(c)), tuple(r))
        for c, r in zip(corrected_rgb, reference_lab)
    ]
    residual = float(np.mean(residuals))
    return {
        "matrix": matrix.tolist(),
        "residual_delta_e00": round(residual, 4),
        "passed": residual <= MAX_CORRECTION_RESIDUAL,
    }


def apply_correction(rgb: list[float], matrix: list[list[float]]) -> list[float]:
    """Apply a fitted correction to a single sRGB 0-255 color."""
    m = np.asarray(matrix, dtype=np.float64)
    lin = _to_linear(np.asarray([rgb], dtype=np.float64))
    x = np.hstack([lin, np.ones((1, 1))])
    corrected = np.clip(x @ m, 0.0, 1.0)
    return [round(float(v), 4) for v in _to_srgb255(corrected)[0]]
