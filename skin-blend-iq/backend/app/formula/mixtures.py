"""Empirical mixture model (spec section 9, "Practical MVP" tier).

The model is driven by a measured swatch library for a specific kit:
nearest-neighbor retrieval over recorded (ratios -> L*a*b*) samples,
combined with local interpolation. Pure-pigment samples anchor an
approximate XYZ interpolation used between measured points.

Data source is tracked per kit: 'measured' (studio swatch data) or
'synthetic' (demo/prototype values). Synthetic kits can exercise the
full workflow but their formulas are never treatment-grade
(non-negotiable rules 1 and 12; Appendix B warning 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..colorscience import delta_e_2000, lab_to_xyz, xyz_to_lab


@dataclass
class MixtureSample:
    ratios: dict[str, float]  # pigment code -> proportion, sums to 1
    lab: tuple[float, float, float]
    source: str = "measured"  # measured | synthetic


@dataclass
class KitModel:
    """Mixture model for one pigment kit + dataset version."""

    codes: list[str]
    samples: list[MixtureSample]
    dataset_version: str
    data_source: str = "measured"
    _pure_xyz: dict[str, tuple[float, float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for s in self.samples:
            active = [c for c, v in s.ratios.items() if v > 1e-9]
            if len(active) == 1:
                self._pure_xyz[active[0]] = lab_to_xyz(s.lab)
        missing = [c for c in self.codes if c not in self._pure_xyz]
        if missing:
            raise ValueError(f"Kit dataset missing pure-pigment samples for: {missing}")

    def ratios_vector(self, ratios: dict[str, float]) -> list[float]:
        return [ratios.get(c, 0.0) for c in self.codes]

    def predict_lab(self, ratios: dict[str, float]) -> tuple[float, float, float]:
        """Predict mixed color for the given proportions.

        Blend of (a) inverse-distance-weighted measured samples near the
        candidate in ratio space and (b) concentration-weighted XYZ
        interpolation of the pure pigments. Measured neighbors dominate
        when the candidate sits inside the sampled region.
        """
        total = sum(ratios.values())
        if total <= 0:
            raise ValueError("ratios must have positive sum")
        norm = {c: v / total for c, v in ratios.items() if v > 0}

        base_xyz = [0.0, 0.0, 0.0]
        for code, frac in norm.items():
            xyz = self._pure_xyz[code]
            for i in range(3):
                base_xyz[i] += frac * xyz[i]
        base_lab = xyz_to_lab(tuple(base_xyz))

        vec = self.ratios_vector(norm)
        weighted: list[tuple[float, MixtureSample]] = []
        for s in self.samples:
            svec = self.ratios_vector(s.ratios)
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec, svec)))
            if d < 1e-9:
                return s.lab
            weighted.append((d, s))
        weighted.sort(key=lambda t: t[0])
        neighbors = weighted[: min(4, len(weighted))]

        wsum = sum(1.0 / d for d, _ in neighbors)
        nn_lab = [0.0, 0.0, 0.0]
        for d, s in neighbors:
            w = (1.0 / d) / wsum
            for i in range(3):
                nn_lab[i] += w * s.lab[i]

        # Trust measured neighbors more when they are close in ratio space.
        nearest_d = neighbors[0][0]
        alpha = max(0.0, min(1.0, 1.0 - nearest_d / 0.5))
        return tuple(
            alpha * nn_lab[i] + (1.0 - alpha) * base_lab[i] for i in range(3)
        )  # type: ignore[return-value]

    def gamut_distance(self, target_lab: tuple[float, float, float]) -> float:
        """ΔE00 from the target to the nearest measured sample.

        Small distance means the target is inside the well-sampled
        region; large distance means the solver is extrapolating.
        """
        return min(delta_e_2000(target_lab, s.lab) for s in self.samples)

    def nearest_samples(
        self, target_lab: tuple[float, float, float], n: int = 5
    ) -> list[tuple[float, MixtureSample]]:
        scored = [(delta_e_2000(target_lab, s.lab), s) for s in self.samples]
        scored.sort(key=lambda t: t[0])
        return scored[:n]


# ---------------------------------------------------------------------------
# Synthetic demo kit (prototype only — Appendix B warning 1). These invented
# values validate the software flow; they never represent real pigments.
# ---------------------------------------------------------------------------

SYNTHETIC_KIT_DATASET_VERSION = "kit-synthetic-demo-001"

_SYNTHETIC_PURE_LAB: dict[str, tuple[float, float, float]] = {
    "P-Y": (85.0, 5.0, 78.0),    # primary yellow
    "P-R": (45.0, 62.0, 38.0),   # primary red
    "P-B": (35.0, 12.0, -48.0),  # primary blue
    "P-W": (96.0, 0.5, 2.0),     # white
    "P-K": (12.0, 0.5, -1.0),    # black
}


def synthetic_demo_samples() -> list[MixtureSample]:
    """Pure pigments plus binary/ternary ladders (spec section 9 sampling design)."""
    codes = list(_SYNTHETIC_PURE_LAB)
    pure_xyz = {c: lab_to_xyz(lab) for c, lab in _SYNTHETIC_PURE_LAB.items()}

    def synth_lab(ratios: dict[str, float]) -> tuple[float, float, float]:
        xyz = [0.0, 0.0, 0.0]
        for c, f in ratios.items():
            for i in range(3):
                xyz[i] += f * pure_xyz[c][i]
        # Mild darkening term mimics subtractive behavior of real mixtures.
        lab = list(xyz_to_lab(tuple(xyz)))
        n_active = sum(1 for f in ratios.values() if f > 1e-9)
        lab[0] -= 1.5 * (n_active - 1)
        return tuple(lab)  # type: ignore[return-value]

    samples = [
        MixtureSample(ratios={c: 1.0}, lab=_SYNTHETIC_PURE_LAB[c], source="synthetic")
        for c in codes
    ]
    # Binary ladders.
    for i, a in enumerate(codes):
        for b in codes[i + 1 :]:
            for fa in (0.25, 0.5, 0.75):
                r = {a: fa, b: 1.0 - fa}
                samples.append(MixtureSample(ratios=r, lab=synth_lab(r), source="synthetic"))
    # Ternary mixtures concentrated in skin-relevant regions.
    ternaries = [
        {"P-Y": 0.4, "P-R": 0.2, "P-W": 0.4},
        {"P-Y": 0.3, "P-R": 0.2, "P-W": 0.5},
        {"P-Y": 0.3, "P-R": 0.3, "P-K": 0.4},
        {"P-Y": 0.2, "P-R": 0.2, "P-K": 0.6},
        {"P-Y": 0.25, "P-R": 0.25, "P-B": 0.5},
        {"P-R": 0.3, "P-W": 0.4, "P-K": 0.3},
        {"P-Y": 0.35, "P-R": 0.15, "P-B": 0.1, "P-W": 0.4},
        {"P-Y": 0.25, "P-R": 0.2, "P-B": 0.1, "P-K": 0.45},
        {"P-Y": 0.2, "P-R": 0.15, "P-B": 0.05, "P-W": 0.25, "P-K": 0.35},
    ]
    for r in ternaries:
        samples.append(MixtureSample(ratios=r, lab=synth_lab(r), source="synthetic"))
    return samples


def synthetic_demo_kit() -> KitModel:
    return KitModel(
        codes=list(_SYNTHETIC_PURE_LAB),
        samples=synthetic_demo_samples(),
        dataset_version=SYNTHETIC_KIT_DATASET_VERSION,
        data_source="synthetic",
    )
