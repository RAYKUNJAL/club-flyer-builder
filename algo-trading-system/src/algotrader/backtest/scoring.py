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


def wilson_lower(wins: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the 95% Wilson score interval for a win rate.

    This is the law of large numbers made operational: a 60% win rate over 10
    trades has a lower bound near 31% (meaningless), while 60% over 200 trades
    has a lower bound near 53% (actually solid). Never judge a win rate without
    its trade count -- this function is how the app enforces that.
    """
    if n <= 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, (center - margin) / denom)


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
