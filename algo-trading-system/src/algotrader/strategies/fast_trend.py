"""Opening momentum burst -- the "MONEYBAGS" / "fast trend" archetype.

Vendor description: "Jumps on the explosive NQ momentum right at market open. One trade.
Defined target. Done before most people finish their coffee." That's a single opening-drive
momentum trade: measure the size/direction of the first few minutes off the open, and if it
clears a threshold, take one trade with a fixed point target and a tight time-boxed exit.
"""
from __future__ import annotations

from datetime import time

from .base import Order, OrderAction, Strategy, StrategyContext, minutes_since_session_open


class FastTrend(Strategy):
    name = "fast_trend"

    def __init__(
        self,
        drive_minutes: int = 5,
        session_open: time = time(9, 30),
        momentum_threshold_points: float = 15.0,
        target_points: float = 20.0,
        stop_points: float = 10.0,
        max_hold_minutes: int = 30,
    ):
        super().__init__(
            drive_minutes=drive_minutes,
            session_open=session_open,
            momentum_threshold_points=momentum_threshold_points,
            target_points=target_points,
            stop_points=stop_points,
            max_hold_minutes=max_hold_minutes,
        )
        self.drive_minutes = drive_minutes
        self.session_open = session_open
        self.momentum_threshold_points = momentum_threshold_points
        self.target_points = target_points
        self.stop_points = stop_points
        self.max_hold_minutes = max_hold_minutes
        self._day_state: dict = {}

    def reset(self) -> None:
        self._day_state = {}

    def _day_key(self, ts) -> str:
        return ts.strftime("%Y-%m-%d")

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        ts = ctx.ts
        bar = ctx.bar
        day_key = self._day_key(ts)
        state = self._day_state.setdefault(day_key, {"open_price": None, "traded": False})

        mins = minutes_since_session_open(ts, self.session_open)
        if mins < 0:
            return []

        if state["open_price"] is None:
            state["open_price"] = bar["open"]

        pos = ctx.position

        if pos.side is not None:
            entry_time = pos.entry_time
            held_minutes = (ts - entry_time).total_seconds() / 60 if entry_time is not None else 0
            if held_minutes >= self.max_hold_minutes:
                return [Order(OrderAction.EXIT, reason="max_hold_timeout")]
            return []

        # Only one shot per day, and only within the opening drive window.
        if state["traded"] or mins > self.drive_minutes:
            return []

        move = bar["close"] - state["open_price"]
        if abs(move) < self.momentum_threshold_points:
            return []

        state["traded"] = True
        close = bar["close"]
        if move > 0:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="opening_drive_long",
                    stop_price=close - self.stop_points,
                    target_price=close + self.target_points,
                )
            ]
        return [
            Order(
                OrderAction.ENTER_SHORT,
                reason="opening_drive_short",
                stop_price=close + self.stop_points,
                target_price=close - self.target_points,
            )
        ]
