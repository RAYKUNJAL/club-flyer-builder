"""Color-difference formulas.

CIEDE2000 is the treatment-grade comparison metric. ΔE76 is stored for
debugging and legacy comparison only (spec section 7). The CIEDE2000
implementation follows Sharma, Wu & Dalal (2005) and is validated in the
test suite against the published reference pairs.
"""

from __future__ import annotations

import math


def delta_e_76(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(lab1, lab2)))


def delta_e_2000(
    lab1: tuple[float, float, float],
    lab2: tuple[float, float, float],
    k_l: float = 1.0,
    k_c: float = 1.0,
    k_h: float = 1.0,
) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0

    g = 0.5 * (1.0 - math.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = math.hypot(a1p, b1)
    c2p = math.hypot(a2p, b2)

    def hp(ap: float, b: float) -> float:
        if ap == 0.0 and b == 0.0:
            return 0.0
        h = math.degrees(math.atan2(b, ap))
        return h + 360.0 if h < 0 else h

    h1p = hp(a1p, b1)
    h2p = hp(a2p, b2)

    dLp = L2 - L1
    dCp = c2p - c1p

    if c1p * c2p == 0.0:
        dhp = 0.0
    else:
        diff = h2p - h1p
        if abs(diff) <= 180.0:
            dhp = diff
        elif diff > 180.0:
            dhp = diff - 360.0
        else:
            dhp = diff + 360.0
    dHp = 2.0 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2.0)

    Lbp = (L1 + L2) / 2.0
    Cbp = (c1p + c2p) / 2.0

    if c1p * c2p == 0.0:
        hbp = h1p + h2p
    else:
        s = h1p + h2p
        diff = abs(h1p - h2p)
        if diff <= 180.0:
            hbp = s / 2.0
        elif s < 360.0:
            hbp = (s + 360.0) / 2.0
        else:
            hbp = (s - 360.0) / 2.0

    t = (
        1.0
        - 0.17 * math.cos(math.radians(hbp - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * hbp))
        + 0.32 * math.cos(math.radians(3.0 * hbp + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * hbp - 63.0))
    )
    d_theta = 30.0 * math.exp(-(((hbp - 275.0) / 25.0) ** 2))
    r_c = 2.0 * math.sqrt(Cbp**7 / (Cbp**7 + 25.0**7))
    s_l = 1.0 + (0.015 * (Lbp - 50.0) ** 2) / math.sqrt(20.0 + (Lbp - 50.0) ** 2)
    s_c = 1.0 + 0.045 * Cbp
    s_h = 1.0 + 0.015 * Cbp * t
    r_t = -math.sin(math.radians(2.0 * d_theta)) * r_c

    return math.sqrt(
        (dLp / (k_l * s_l)) ** 2
        + (dCp / (k_c * s_c)) ** 2
        + (dHp / (k_h * s_h)) ** 2
        + r_t * (dCp / (k_c * s_c)) * (dHp / (k_h * s_h))
    )
