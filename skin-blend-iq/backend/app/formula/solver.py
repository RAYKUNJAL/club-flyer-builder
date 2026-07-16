"""Constrained formula solver (spec section 10).

Deterministic: nearest measured mixtures seed candidate proportions;
projected coordinate descent refines them on the simplex (nonnegative,
sum to one); candidates are quantized to whole drops; predicted color is
recalculated after rounding; candidates are ranked by the spec's
objective function. AI never controls measurement or scoring here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..colorscience import delta_e_76, delta_e_2000
from .mixtures import KitModel
from .quantize import drops_to_ratios, quantize_drops

WEIGHTS = {
    "color": 1.0,
    "uncertainty": 0.5,
    "complexity": 0.15,
    "extrapolation": 0.3,
    "inventory": 1000.0,  # unavailable lots are effectively blocked
    "quantization": 0.5,
}

GAMUT_INSIDE_THRESHOLD = 8.0   # max ΔE00 to nearest measured sample
TOLERANCE_DELTA_E00 = 2.0      # "good match" tolerance for gamut_status
MAX_ROUNDING_PENALTY_DE = 3.0  # UI blocks cap sizes beyond this added error


@dataclass
class Candidate:
    ratios: dict[str, float]
    drops: dict[str, int]
    total_drops: int
    predicted_lab: tuple[float, float, float]
    predicted_lab_continuous: tuple[float, float, float]
    delta_e_2000: float
    delta_e_76: float
    delta_e_2000_continuous: float
    rounding_delta_e: float
    score: float
    confidence: float
    n_pigments: int
    quantization_error: dict[str, float] = field(default_factory=dict)


def _project_simplex(v: list[float]) -> list[float]:
    """Euclidean projection onto {x >= 0, sum x = 1}."""
    n = len(v)
    u = sorted(v, reverse=True)
    css = 0.0
    rho = -1
    theta = 0.0
    for i in range(n):
        css += u[i]
        t = (css - 1.0) / (i + 1)
        if u[i] - t > 0:
            rho = i
            theta = t
    if rho < 0:
        return [1.0 / n] * n
    return [max(0.0, x - theta) for x in v]


def _refine(
    kit: KitModel,
    target: tuple[float, float, float],
    start: dict[str, float],
    allowed: list[str],
    locked: dict[str, float],
    iterations: int = 60,
) -> dict[str, float]:
    codes = allowed
    free_budget = 1.0 - sum(locked.values())
    x = [start.get(c, 0.0) for c in codes]
    s = sum(x)
    x = [v / s * free_budget if s > 0 else free_budget / len(codes) for v in x]

    def loss(vec: list[float]) -> float:
        ratios = {c: v for c, v in zip(codes, vec)}
        ratios.update(locked)
        if sum(ratios.values()) <= 0:
            return 1e9
        return delta_e_2000(kit.predict_lab(ratios), target)

    step = 0.12
    best = loss(x)
    for _ in range(iterations):
        improved = False
        for i in range(len(codes)):
            for direction in (1.0, -1.0):
                trial = list(x)
                trial[i] += direction * step
                trial = _project_simplex([v / max(free_budget, 1e-9) for v in trial])
                trial = [v * free_budget for v in trial]
                l = loss(trial)
                if l < best - 1e-6:
                    x, best = trial, l
                    improved = True
        if not improved:
            step /= 2.0
            if step < 0.002:
                break
    result = {c: v for c, v in zip(codes, x) if v > 1e-4}
    result.update({c: v for c, v in locked.items() if v > 0})
    return result


def solve(
    kit: KitModel,
    target_lab: tuple[float, float, float],
    total_drops: int = 20,
    target_uncertainty: float = 0.0,
    excluded: list[str] | None = None,
    locked: dict[str, float] | None = None,
    max_pigments: int | None = None,
    unavailable: list[str] | None = None,
    n_alternatives: int = 3,
) -> dict:
    """Return the ranked candidate list plus gamut assessment."""
    excluded = excluded or []
    locked = locked or {}
    unavailable = unavailable or []
    blocked = set(excluded) | set(unavailable)
    allowed = [c for c in kit.codes if c not in blocked and c not in locked]
    if not allowed and not locked:
        raise ValueError("No pigments available after exclusions")

    gamut_distance = kit.gamut_distance(target_lab)

    # Seed candidates from the nearest measured mixtures plus a uniform start.
    seeds: list[dict[str, float]] = []
    for _, sample in kit.nearest_samples(target_lab, n=4):
        seed = {c: v for c, v in sample.ratios.items() if c in allowed}
        if seed:
            seeds.append(seed)
    seeds.append({c: 1.0 / len(allowed) for c in allowed} if allowed else dict(locked))

    candidates: list[Candidate] = []
    seen: set[tuple] = set()
    for seed in seeds:
        ratios = _refine(kit, target_lab, seed, allowed, locked)
        if max_pigments is not None:
            while sum(1 for v in ratios.values() if v > 1e-4) > max_pigments:
                smallest = min(
                    (c for c in ratios if c not in locked and ratios[c] > 0),
                    key=lambda c: ratios[c],
                    default=None,
                )
                if smallest is None:
                    break
                ratios.pop(smallest)
                ratios = _refine(kit, target_lab, ratios, [c for c in ratios if c not in locked], locked)

        drops = quantize_drops(ratios, total_drops)
        key = tuple(sorted(drops.items()))
        if key in seen:
            continue
        seen.add(key)

        pred_cont = kit.predict_lab(ratios)
        de_cont = delta_e_2000(pred_cont, target_lab)
        quant_ratios = drops_to_ratios(drops)
        pred = kit.predict_lab(quant_ratios)
        de00 = delta_e_2000(pred, target_lab)
        de76 = delta_e_76(pred, target_lab)
        rounding_de = de00 - de_cont
        n_pig = sum(1 for v in drops.values() if v > 0)

        model_uncertainty = min(1.0, gamut_distance / 10.0) + target_uncertainty / 10.0
        score = (
            WEIGHTS["color"] * de00
            + WEIGHTS["uncertainty"] * model_uncertainty
            + WEIGHTS["complexity"] * n_pig
            + WEIGHTS["extrapolation"] * max(0.0, gamut_distance - GAMUT_INSIDE_THRESHOLD)
            + WEIGHTS["quantization"] * max(0.0, rounding_de)
        )
        confidence = round(
            max(0.0, min(1.0, 1.0 - de00 / 10.0 - gamut_distance / 20.0 - target_uncertainty / 10.0)),
            3,
        )
        from .quantize import quantization_error

        candidates.append(
            Candidate(
                ratios={c: round(v, 6) for c, v in ratios.items()},
                drops=drops,
                total_drops=total_drops,
                predicted_lab=tuple(round(v, 3) for v in pred),
                predicted_lab_continuous=tuple(round(v, 3) for v in pred_cont),
                delta_e_2000=round(de00, 3),
                delta_e_76=round(de76, 3),
                delta_e_2000_continuous=round(de_cont, 3),
                rounding_delta_e=round(rounding_de, 3),
                score=round(score, 4),
                confidence=confidence,
                n_pigments=n_pig,
                quantization_error=quantization_error(ratios, drops),
            )
        )

    candidates.sort(key=lambda c: c.score)
    best = candidates[0]
    # Inside the calibrated gamut when the target sits near measured data
    # AND the best continuous solution reaches tolerance, AND rounding did
    # not push the quantized recipe unacceptably far.
    inside = (
        gamut_distance <= GAMUT_INSIDE_THRESHOLD
        and best.delta_e_2000_continuous <= TOLERANCE_DELTA_E00
        and best.rounding_delta_e <= MAX_ROUNDING_PENALTY_DE
    )
    gamut_status = "inside" if inside else "outside"
    return {
        "gamut_status": gamut_status,
        "gamut_distance": round(gamut_distance, 3),
        "candidates": candidates[: 1 + n_alternatives],
        "warnings": (
            []
            if gamut_status == "inside"
            else ["Target is outside the calibrated gamut; showing best achievable match."]
        ),
    }
