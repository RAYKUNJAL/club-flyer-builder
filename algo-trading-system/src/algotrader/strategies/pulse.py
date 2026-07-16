"""All-session momentum/trend-follow -- the "PULSE" archetype.

Vendor description: "All-session momentum and trend following. Fires whenever the conditions
are right -- morning, midday, or afternoon. This is the one that catches the big 50-100 point
trend days." That's an EMA-crossover trend filter held with an ATR trailing stop (so it rides
a move instead of taking a fixed target), re-entering on fresh crossovers throughout the session.
"""
from __future__ import annotations

from datetime import time

from .base import Order, OrderAction, Strategy, StrategyContext, atr


class Pulse(Strategy):
    name = "pulse"

    def __init__(
        self,
        fast_period: int = 9,
        slow_period: int = 21,
        atr_period: int = 14,
        trail_atr_mult: float = 2.0,
        min_spread_atr_mult: float = 0.15,
        session_close: time = time(15, 55),
    ):
        super().__init__(
            fast_period=fast_period,
            slow_period=slow_period,
            atr_period=atr_period,
            trail_atr_mult=trail_atr_mult,
            min_spread_atr_mult=min_spread_atr_mult,
            session_close=session_close,
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_period = atr_period
        self.trail_atr_mult = trail_atr_mult
        self.min_spread_atr_mult = min_spread_atr_mult
        self.session_close = session_close

    def reset(self) -> None:
        pass

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        history = ctx.history
        min_bars = max(self.slow_period, self.atr_period) + 1
        if len(history) < min_bars:
            return []

        close = history["close"]
        fast_ema = close.ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = close.ewm(span=self.slow_period, adjust=False).mean()
        current_atr = atr(history, self.atr_period).iloc[-1]
        if current_atr != current_atr:
            return []

        spread = fast_ema.iloc[-1] - slow_ema.iloc[-1]
        prev_spread = fast_ema.iloc[-2] - slow_ema.iloc[-2]
        bar = ctx.bar
        pos = ctx.position

        # Force-flat into the close -- don't hold trend positions overnight.
        if ctx.ts.time() >= self.session_close and pos.side is not None:
            return [Order(OrderAction.EXIT, reason="session_close")]

        if pos.side == "long":
            new_stop = bar["close"] - self.trail_atr_mult * current_atr
            if bar["close"] <= pos.stop_price:
                return [Order(OrderAction.EXIT, reason="trail_stop_hit")]
            if spread < 0:  # trend flipped
                return [Order(OrderAction.EXIT, reason="trend_flip")]
            if new_stop > pos.stop_price:
                return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
            return []

        if pos.side == "short":
            new_stop = bar["close"] + self.trail_atr_mult * current_atr
            if bar["close"] >= pos.stop_price:
                return [Order(OrderAction.EXIT, reason="trail_stop_hit")]
            if spread > 0:
                return [Order(OrderAction.EXIT, reason="trend_flip")]
            if new_stop < pos.stop_price:
                return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
            return []

        # Flat: look for a fresh crossover with enough separation to avoid whipsaw.
        min_spread = self.min_spread_atr_mult * current_atr
        crossed_up = prev_spread <= 0 and spread > min_spread
        crossed_down = prev_spread >= 0 and spread < -min_spread
        if crossed_up:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="pulse_trend_up",
                    stop_price=bar["close"] - self.trail_atr_mult * current_atr,
                )
            ]
        if crossed_down:
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="pulse_trend_down",
                    stop_price=bar["close"] + self.trail_atr_mult * current_atr,
                )
            ]
        return []
