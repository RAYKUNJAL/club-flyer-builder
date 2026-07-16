"""Opening Range Breakout -- the "BLITZ" / "ORB" archetype.

Build the opening N minutes into a high/low range, then trade the break of either side.
Matches the vendor's public description: "Builds the 9:30-9:45 opening range then fires
on the breakout." ATR-based stop, capped dollar/point risk (the $1,000 / 50-pt convention
commonly used for NQ ORB systems), one breakout trade per side per session.
"""
from __future__ import annotations

from datetime import time

from .base import Order, OrderAction, Strategy, StrategyContext, atr, minutes_since_session_open


class OpeningRangeBreakout(Strategy):
    name = "orb"

    def __init__(
        self,
        range_minutes: int = 30,
        session_open: time = time(9, 30),
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        reward_risk: float = 2.0,
        max_risk_points: float = 50.0,
        session_close: time = time(16, 0),
    ):
        super().__init__(
            range_minutes=range_minutes,
            session_open=session_open,
            atr_period=atr_period,
            atr_stop_mult=atr_stop_mult,
            reward_risk=reward_risk,
            max_risk_points=max_risk_points,
            session_close=session_close,
        )
        self.range_minutes = range_minutes
        self.session_open = session_open
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.reward_risk = reward_risk
        self.max_risk_points = max_risk_points
        self.session_close = session_close
        self._day_state: dict = {}

    def reset(self) -> None:
        self._day_state = {}

    def _day_key(self, ts) -> str:
        return ts.strftime("%Y-%m-%d")

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        ts = ctx.ts
        bar = ctx.bar
        day_key = self._day_key(ts)
        state = self._day_state.setdefault(
            day_key, {"range_high": None, "range_low": None, "traded": False}
        )

        mins = minutes_since_session_open(ts, self.session_open)
        in_range_window = 0 <= mins < self.range_minutes

        # Still inside the opening range window: extend the range.
        if in_range_window:
            state["range_high"] = bar["high"] if state["range_high"] is None else max(state["range_high"], bar["high"])
            state["range_low"] = bar["low"] if state["range_low"] is None else min(state["range_low"], bar["low"])

        pos = ctx.position

        # Manage any open position on EVERY bar -- including the next day's opening-range
        # window -- before the no-trade early returns below.
        if pos.side is not None:
            # Force-flat at session close.
            if ts.time() >= self.session_close:
                return [Order(OrderAction.EXIT, reason="session_close")]
            # If the data's last session bar was stamped before session_close, the position
            # carried overnight: flatten on the first bar of the next session instead of
            # holding an intraday-breakout position across days.
            if pos.entry_time is not None and self._day_key(pos.entry_time) != day_key:
                return [Order(OrderAction.EXIT, reason="overnight_carry_flat")]

        if in_range_window:
            return []  # never open a new trade while the range is still forming

        if state["range_high"] is None or state["range_low"] is None:
            return []  # no range formed yet (e.g. data starts mid-session)

        if pos.side is not None or state["traded"]:
            return []

        history = ctx.history
        if len(history) < self.atr_period + 1:
            return []
        current_atr = atr(history, self.atr_period).iloc[-1]
        if current_atr != current_atr:  # NaN guard
            return []

        close = bar["close"]
        if close > state["range_high"]:
            stop_distance = min(self.atr_stop_mult * current_atr, self.max_risk_points)
            state["traded"] = True
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="orb_breakout_long",
                    stop_price=close - stop_distance,
                    target_price=close + stop_distance * self.reward_risk,
                )
            ]
        if close < state["range_low"]:
            stop_distance = min(self.atr_stop_mult * current_atr, self.max_risk_points)
            state["traded"] = True
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="orb_breakout_short",
                    stop_price=close + stop_distance,
                    target_price=close - stop_distance * self.reward_risk,
                )
            ]
        return []
