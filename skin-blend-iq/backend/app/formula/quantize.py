"""Whole-drop quantization (spec sections 10-11).

Sum-preserving largest-remainder rounding: the drops always total the
requested cap exactly, no negative quantities, deterministic. The
continuous master ratio is preserved by the caller in the audit trail
and predicted color is recalculated after rounding.
"""

from __future__ import annotations

DEFAULT_TOTALS = (10, 20, 40)


def quantize_drops(ratios: dict[str, float], total_drops: int) -> dict[str, int]:
    if total_drops <= 0:
        raise ValueError("total_drops must be positive")
    s = sum(ratios.values())
    if s <= 0:
        raise ValueError("ratios must have positive sum")
    norm = {c: v / s for c, v in ratios.items()}

    raw = {c: v * total_drops for c, v in norm.items()}
    floors = {c: int(v) for c, v in raw.items()}
    assigned = sum(floors.values())
    remainder = total_drops - assigned

    # Distribute leftover drops by largest fractional remainder;
    # ties broken by larger ratio then code for determinism.
    order = sorted(
        raw,
        key=lambda c: (raw[c] - floors[c], norm[c], c),
        reverse=True,
    )
    drops = dict(floors)
    for c in order[:remainder]:
        drops[c] += 1

    assert sum(drops.values()) == total_drops
    assert all(v >= 0 for v in drops.values())
    return drops


def drops_to_ratios(drops: dict[str, int]) -> dict[str, float]:
    total = sum(drops.values())
    if total <= 0:
        raise ValueError("drops must have positive sum")
    return {c: v / total for c, v in drops.items() if v > 0}


def quantization_error(
    ratios: dict[str, float], drops: dict[str, int]
) -> dict[str, float]:
    """Per-pigment proportion error introduced by rounding."""
    s = sum(ratios.values())
    norm = {c: v / s for c, v in ratios.items()}
    total = sum(drops.values())
    return {
        c: round(drops.get(c, 0) / total - norm.get(c, 0.0), 6)
        for c in set(norm) | set(drops)
    }
