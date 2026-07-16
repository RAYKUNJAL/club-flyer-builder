"""Event-driven bar-by-bar backtester.

Feeds the strategy an expanding history window one bar at a time (no look-ahead), applies
engine-level stop/target/trailing-stop checks against each bar's high/low (strategies set
stop_price/target_price on the position; the engine is what actually enforces them, since a
strategy may not re-evaluate every bar), and tracks equity, commission, and slippage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..risk.position_sizing import PositionSizer
from ..strategies.base import OrderAction, PositionState, Strategy, StrategyContext


@dataclass
class Trade:
    side: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    contracts: int
    pnl: float
    entry_reason: str
    exit_reason: str


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)


class BacktestEngine:
    def __init__(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        risk_sizer: PositionSizer,
        starting_equity: float = 100_000.0,
        point_value: float | None = None,
        commission_per_contract: float = 2.50,
        slippage_points: float = 0.25,
    ):
        self.data = data
        self.strategy = strategy
        self.risk_sizer = risk_sizer
        self.starting_equity = starting_equity
        self.point_value = point_value if point_value is not None else risk_sizer.config.point_value
        self.commission_per_contract = commission_per_contract
        self.slippage_points = slippage_points

    def run(self) -> BacktestResult:
        self.strategy.reset()
        data = self.data
        equity = self.starting_equity
        equity_points = []
        trades: list[Trade] = []
        pos = PositionState()
        contracts = 0
        current_day = None
        day_start_equity = equity
        # Round-trip commission plus adverse exit slippage are real per-contract costs on a
        # stop-out; include them so a clean stop loses no more than the configured risk %.
        entry_costs_per_contract = (
            self.commission_per_contract * 2 + self.slippage_points * self.point_value
        )

        for i in range(len(data)):
            history = data.iloc[: i + 1]
            bar = history.iloc[-1]
            ts = history.index[-1]

            # New trading day: reset the daily-loss-cap baseline.
            day = ts.normalize()
            if current_day is None or day != current_day:
                current_day = day
                day_start_equity = equity

            # An open position has now been held for one more bar (entry bar counts as 0).
            if pos.side is not None:
                pos.bars_held += 1

            # 1. Enforce any open position's stop/target against this bar's range before
            #    letting the strategy react (mirrors a resting stop/limit order at the broker).
            if pos.side is not None:
                hit_price, reason = self._check_stop_target(pos, bar)
                if hit_price is not None:
                    # A triggered stop becomes a market order: it fills with adverse slippage,
                    # exactly like entries and strategy EXITs. A target is a resting limit
                    # order and fills at its limit price (no slippage through the limit).
                    if reason == "stop_hit":
                        fill = self._apply_slippage(hit_price, pos.side, exiting=True)
                    else:
                        fill = hit_price
                    equity = self._close_trade(trades, pos, contracts, ts, fill, reason, equity)
                    pos = PositionState()
                    contracts = 0

            ctx = StrategyContext(history=history, position=pos)
            orders = self.strategy.on_bar(ctx)

            for order in orders:
                if order.action == OrderAction.UPDATE_STOP and pos.side is not None:
                    # Only accept ratchets that keep or reduce risk -- a widened (or removed)
                    # stop would silently blow through the configured per-trade risk cap.
                    if self._stop_update_is_valid(pos, order.stop_price):
                        pos.stop_price = order.stop_price
                elif order.action == OrderAction.EXIT and pos.side is not None:
                    fill = self._apply_slippage(bar["close"], pos.side, exiting=True)
                    equity = self._close_trade(trades, pos, contracts, ts, fill, order.reason, equity)
                    pos = PositionState()
                    contracts = 0
                elif order.action in (OrderAction.ENTER_LONG, OrderAction.ENTER_SHORT) and pos.side is None:
                    # Daily loss cap: halt new entries once the day's realized loss trips it.
                    if self.risk_sizer.daily_loss_limit_hit(day_start_equity, equity):
                        continue
                    side = "long" if order.action == OrderAction.ENTER_LONG else "short"
                    fill = self._apply_slippage(bar["close"], side, exiting=False)
                    sized = (
                        self.risk_sizer.size(
                            equity, fill, order.stop_price,
                            costs_per_contract=entry_costs_per_contract,
                        )
                        if order.stop_price is not None
                        else 0
                    )
                    if sized <= 0:
                        continue
                    contracts = sized
                    pos = PositionState(
                        side=side,
                        entry_price=fill,
                        stop_price=order.stop_price,
                        target_price=order.target_price,
                        entry_time=ts,
                        meta={"entry_reason": order.reason},
                    )

            # Mark-to-market: include the open position's unrealized PnL at this bar's close,
            # so drawdown/Sharpe see intratrade excursions, not just realized trade closes.
            mark = equity
            if pos.side is not None:
                direction = 1 if pos.side == "long" else -1
                mark += (bar["close"] - pos.entry_price) * direction * self.point_value * contracts
            equity_points.append((ts, mark))

        # Force-close anything left open at the end of the data window.
        if pos.side is not None:
            last_ts = data.index[-1]
            last_close = data.iloc[-1]["close"]
            fill = self._apply_slippage(last_close, pos.side, exiting=True)
            equity = self._close_trade(trades, pos, contracts, last_ts, fill, "end_of_data", equity)
            if equity_points:
                equity_points[-1] = (last_ts, equity)

        equity_curve = pd.Series(
            [e for _, e in equity_points], index=[t for t, _ in equity_points], name="equity"
        )
        return BacktestResult(trades=trades, equity_curve=equity_curve)

    def _check_stop_target(self, pos: PositionState, bar: pd.Series) -> tuple[float | None, str]:
        # Gap handling: if the bar OPENS beyond the stop, the stop order triggers on the open
        # and fills there (the worse of open vs stop) -- it cannot fill at a price the market
        # never traded on the way down/up. Targets are limit orders: filled at the limit.
        if pos.side == "long":
            if pos.stop_price is not None and bar["low"] <= pos.stop_price:
                return min(bar["open"], pos.stop_price), "stop_hit"
            if pos.target_price is not None and bar["high"] >= pos.target_price:
                return pos.target_price, "target_hit"
        elif pos.side == "short":
            if pos.stop_price is not None and bar["high"] >= pos.stop_price:
                return max(bar["open"], pos.stop_price), "stop_hit"
            if pos.target_price is not None and bar["low"] <= pos.target_price:
                return pos.target_price, "target_hit"
        return None, ""

    @staticmethod
    def _stop_update_is_valid(pos: PositionState, new_stop: float | None) -> bool:
        """Accept only stop updates that keep or tighten risk (trailing-stop ratchets)."""
        if new_stop is None or new_stop != new_stop:  # None or NaN
            return False
        if pos.stop_price is None:
            return True  # adding a stop where there was none always reduces risk
        if pos.side == "long":
            return new_stop >= pos.stop_price
        return new_stop <= pos.stop_price

    def _apply_slippage(self, price: float, side: str, exiting: bool) -> float:
        # Slippage always costs the trader: worse fill on both entry and exit.
        adverse = self.slippage_points
        if side == "long":
            return price - adverse if exiting else price + adverse
        return price + adverse if exiting else price - adverse

    def _close_trade(
        self,
        trades: list[Trade],
        pos: PositionState,
        contracts: int,
        exit_time: pd.Timestamp,
        exit_price: float,
        reason: str,
        equity: float,
    ) -> float:
        direction = 1 if pos.side == "long" else -1
        gross = (exit_price - pos.entry_price) * direction * self.point_value * contracts
        commission = self.commission_per_contract * contracts * 2  # entry + exit
        pnl = gross - commission
        trades.append(
            Trade(
                side=pos.side,
                entry_time=pos.entry_time,
                exit_time=exit_time,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                contracts=contracts,
                pnl=pnl,
                entry_reason=pos.meta.get("entry_reason", ""),
                exit_reason=reason,
            )
        )
        return equity + pnl
