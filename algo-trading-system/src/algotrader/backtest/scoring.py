"""Composite, risk-adjusted ranking score for backtested strategy configs.

Ranking by raw win rate alone is misleading: a strategy that wins 70% of the
time with tiny wins and huge losses is worse than one that wins 52% with a 3x
profit factor. Copy-trading leaderboards (dub, eToro, etc.) rank on blended
risk-adjusted metrics for the same reason -- dub surfaces volatility, max
drawdown, and beta alongside returns rather than returns alone.

The score blends four components, each clamped to a sane range and normalized
to [0, 1], so no single metric can dominate:

    0.35 * profit factor   (clamped at 3.0 -- beyond that is usually overfit)
    0.25 * win rate        (already in [0, 1])
    0.20 * Sharpe ratio    (clamped at 2.0)
    0.20 * drawdown        (1.0 at zero drawdown, 0.0 at -40% or worse)

The result is a number in [0, 1]; higher is better. The weights are a
documented editorial choice, not an optimized fit -- change them in one place
here if you disagree with the emphasis.
"""
from __future__ import annotations


def composite_score(
    win_rate: float,
    profit_factor: float,
    sharpe: float,
    max_drawdown_pct: float,
) -> float:
    pf = min(max(profit_factor, 0.0), 3.0) / 3.0
    wr = min(max(win_rate, 0.0), 1.0)
    sr = min(max(sharpe, 0.0), 2.0) / 2.0
    dd = 1.0 - min(abs(max_drawdown_pct), 0.4) / 0.4
    return round(0.35 * pf + 0.25 * wr + 0.20 * sr + 0.20 * dd, 4)
