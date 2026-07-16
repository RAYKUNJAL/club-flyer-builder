"""Deterministic color-space conversions.

Working space: sRGB (IEC 61966-2-1), converted to CIE XYZ and CIE L*a*b*
under illuminant D65, 2-degree standard observer. Declared on every
stored measurement per the Skin Blend IQ spec (sections 7 and 15).
"""

from __future__ import annotations

import math

# D65 reference white, 2-degree observer, Y normalized to 100.
D65_WHITE = (95.047, 100.0, 108.883)

ILLUMINANT = "D65"
OBSERVER = "2deg"

# sRGB (linear) -> XYZ matrix, D65.
_M_RGB_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
# XYZ -> sRGB (linear) matrix, D65.
_M_XYZ_RGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)


def srgb_to_linear(c: float) -> float:
    """One sRGB channel in [0, 1] to linear light."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    if c <= 0.0031308:
        return c * 12.92
    return 1.055 * (c ** (1 / 2.4)) - 0.055


def srgb_to_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB 0-255 channels to XYZ scaled so that Y of white = 100."""
    r, g, b = (srgb_to_linear(c / 255.0) for c in rgb)
    return tuple(
        100.0 * (m[0] * r + m[1] * g + m[2] * b) for m in _M_RGB_XYZ
    )  # type: ignore[return-value]


def xyz_to_srgb(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = (v / 100.0 for v in xyz)
    lin = [m[0] * x + m[1] * y + m[2] * z for m in _M_XYZ_RGB]
    return tuple(round(linear_to_srgb(c) * 255.0, 4) for c in lin)  # type: ignore[return-value]


def _f(t: float) -> float:
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    if t > eps:
        return t ** (1.0 / 3.0)
    return (kappa * t + 16.0) / 116.0


def _f_inv(t: float) -> float:
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    t3 = t**3
    if t3 > eps:
        return t3
    return (116.0 * t - 16.0) / kappa


def xyz_to_lab(
    xyz: tuple[float, float, float], white: tuple[float, float, float] = D65_WHITE
) -> tuple[float, float, float]:
    fx, fy, fz = (_f(v / w) for v, w in zip(xyz, white))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def lab_to_xyz(
    lab: tuple[float, float, float], white: tuple[float, float, float] = D65_WHITE
) -> tuple[float, float, float]:
    L, a, b = lab
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    return (
        _f_inv(fx) * white[0],
        _f_inv(fy) * white[1],
        _f_inv(fz) * white[2],
    )


def srgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    return xyz_to_lab(srgb_to_xyz(rgb))


def lab_to_srgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    return xyz_to_srgb(lab_to_xyz(lab))


def lab_to_lch(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    L, a, b = lab
    c = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0
    return (L, c, h)


def rgb_to_hsv(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB 0-255 to HSV with H in degrees, S and V in [0, 1]."""
    r, g, b = (c / 255.0 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = 60.0 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60.0 * ((b - r) / d + 2)
    else:
        h = 60.0 * ((r - g) / d + 4)
    s = 0.0 if mx == 0 else d / mx
    return (h, s, mx)


def ita_degrees(lab: tuple[float, float, float]) -> float | None:
    """Individual Typology Angle. Undefined when b* is 0."""
    L, _a, b = lab
    if b == 0:
        return None
    return math.degrees(math.atan((L - 50.0) / b))


def classify_undertone(lab: tuple[float, float, float]) -> tuple[str, float]:
    """Heuristic undertone descriptor from the L*a*b* hue angle.

    Returns (label, confidence). This is a descriptive aid for the artist,
    never a diagnosis. Confidence falls near band boundaries.
    """
    _L, chroma, hue = lab_to_lch(lab)
    if chroma < 3.0:
        return ("neutral", 0.5)
    # Skin hue angles typically fall between ~30 (red, cool) and ~80 (yellow, warm).
    bands = [
        (0.0, 40.0, "cool"),
        (40.0, 55.0, "cool-neutral"),
        (55.0, 65.0, "warm-neutral"),
        (65.0, 360.0, "warm"),
    ]
    for lo, hi, label in bands:
        if lo <= hue < hi:
            center = (lo + hi) / 2.0
            half = (hi - lo) / 2.0
            dist = abs(hue - center) / half if half else 1.0
            confidence = round(max(0.5, 1.0 - 0.5 * dist), 3)
            return (label, confidence)
    return ("neutral", 0.5)
