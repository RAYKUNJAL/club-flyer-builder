"""Position sizing: convert a stop distance into a contract/share count under a risk cap.

Mirrors the "$1,000 / 50-pt risk cap" convention referenced for NQ ORB systems: risk a fixed
dollar amount (or a fixed % of equity) per trade, sized off the actual stop distance, plus a
daily loss cap that halts new entries once tripped -- the discipline layer the vendor's copy
("removes emotion", "rule-based execution") is selling.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.01  # 1% of equity per trade
    max_risk_per_trade_dollars: float | None = None  # hard cap regardless of equity
    point_value: float = 20.0  # e.g. NQ e-mini = $20/point; MNQ = $2/point
    daily_loss_cap_pct: float = 0.03  # halt new entries once daily loss exceeds 3% of equity
    max_contracts: int = 10


class PositionSizer:
    def __init__(self, config: RiskConfig):
        self.config = config

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        costs_per_contract: float = 0.0,
    ) -> int:
        """Contracts to trade so a clean stop-out loses at most the configured risk.

        ``costs_per_contract`` covers known per-contract frictions (round-trip commission,
        expected exit slippage) so the realized loss on a stop-out stays within the cap.
        A NaN/inf entry or stop (e.g. an indicator with insufficient history) sizes to 0
        instead of raising.
        """
        if (
            entry_price is None
            or stop_price is None
            or not math.isfinite(entry_price)
            or not math.isfinite(stop_price)
            or not math.isfinite(equity)
        ):
            return 0
        stop_points = abs(entry_price - stop_price)
        if stop_points <= 0:
            return 0
        risk_dollars = equity * self.config.risk_per_trade_pct
        if self.config.max_risk_per_trade_dollars is not None:
            risk_dollars = min(risk_dollars, self.config.max_risk_per_trade_dollars)
        risk_per_contract = stop_points * self.config.point_value + max(costs_per_contract, 0.0)
        if risk_per_contract <= 0:
            return 0
        contracts = int(risk_dollars // risk_per_contract)
        return max(0, min(contracts, self.config.max_contracts))

    def daily_loss_limit_hit(self, equity_at_day_start: float, current_equity: float) -> bool:
        loss = equity_at_day_start - current_equity
        return loss >= equity_at_day_start * self.config.daily_loss_cap_pct
