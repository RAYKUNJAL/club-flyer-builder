"""Image quality scoring (spec section 6).

Every capture image is scored deterministically. Images that fail the
quality gate stay in the record but can never feed a treatment-ready
formula.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image

QUALITY_THRESHOLDS = {
    "min_focus_score": 60.0,       # variance of Laplacian on luma
    "max_overexposed_pct": 1.0,    # % pixels with any channel >= 254
    "max_underexposed_pct": 5.0,   # % pixels with all channels <= 4
    "max_glare_pct": 2.0,          # % near-white low-saturation pixels
    "min_width": 640,
    "min_height": 480,
}

_LAPLACIAN = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float64)


def load_image_array(data: bytes) -> np.ndarray:
    img = Image.open(BytesIO(data)).convert("RGB")
    return np.asarray(img, dtype=np.float64)


def _convolve2d_valid(arr: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    kh, kw = kernel.shape
    h, w = arr.shape
    out = np.zeros((h - kh + 1, w - kw + 1))
    for i in range(kh):
        for j in range(kw):
            out += kernel[i, j] * arr[i : i + h - kh + 1, j : j + w - kw + 1]
    return out


def score_image(data: bytes) -> dict:
    arr = load_image_array(data)
    h, w = arr.shape[:2]
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]

    # Downsample very large images for the focus metric to keep it fast.
    step = max(1, max(h, w) // 1024)
    luma_s = luma[::step, ::step]
    focus_score = float(_convolve2d_valid(luma_s, _LAPLACIAN).var())

    n = arr.shape[0] * arr.shape[1]
    overexposed_pct = float((arr >= 254).any(axis=2).sum()) / n * 100.0
    underexposed_pct = float((arr <= 4).all(axis=2).sum()) / n * 100.0

    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    glare_pct = float(((mx >= 250) & (sat < 0.08)).sum()) / n * 100.0

    t = QUALITY_THRESHOLDS
    failures = []
    if focus_score < t["min_focus_score"]:
        failures.append("focus")
    if overexposed_pct > t["max_overexposed_pct"]:
        failures.append("overexposure")
    if underexposed_pct > t["max_underexposed_pct"]:
        failures.append("underexposure")
    if glare_pct > t["max_glare_pct"]:
        failures.append("glare")
    if w < t["min_width"] or h < t["min_height"]:
        failures.append("resolution")

    if not failures:
        grade = "pass"
    elif len(failures) == 1 and failures[0] in ("glare", "underexposure"):
        grade = "marginal"
    else:
        grade = "fail"

    return {
        "width": w,
        "height": h,
        "focus_score": round(focus_score, 3),
        "overexposed_pct": round(overexposed_pct, 4),
        "underexposed_pct": round(underexposed_pct, 4),
        "glare_pct": round(glare_pct, 4),
        "failures": failures,
        "grade": grade,
    }


def patch_statistics(data: bytes, patches: list[dict]) -> list[dict]:
    """Robust per-patch statistics for artist-selected skin regions.

    Each patch is a rectangle {x, y, w, h} in image pixel coordinates.
    Returns median RGB, robust spread, and pixel count. Median (not mean)
    per the target-sampling rules in spec section 7.
    """
    arr = load_image_array(data)
    h, w = arr.shape[:2]
    out = []
    for p in patches:
        x0 = max(0, int(p["x"]))
        y0 = max(0, int(p["y"]))
        x1 = min(w, x0 + max(1, int(p["w"])))
        y1 = min(h, y0 + max(1, int(p["h"])))
        region = arr[y0:y1, x0:x1].reshape(-1, 3)
        if region.size == 0:
            out.append({"pixel_count": 0, "median_rgb": None, "spread": None})
            continue
        median = np.median(region, axis=0)
        mad = np.median(np.abs(region - median), axis=0)
        out.append(
            {
                "pixel_count": int(region.shape[0]),
                "median_rgb": [round(float(v), 3) for v in median],
                "spread": round(float(mad.mean()) * 1.4826, 3),
            }
        )
    return out
