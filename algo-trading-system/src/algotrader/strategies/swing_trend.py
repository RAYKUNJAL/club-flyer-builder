"""Long-term daily trend following -- the "TradingBoss Trend/Swing" archetype.

Vendor description: "Daily chart indicator. One signal. Let it run for days -- sometimes
weeks. Works on NQ, ES, Gold, Tesla, anything that trends." That's classic Donchian-channel
(turtle-style) breakout trend following on daily bars: enter on an N-day high/low breakout,
exit on the opposite M-day breakout (M < N so it gives back less than it captured), with an
ATR stop as a hard drawdown cap -- which is exactly how a system tames the 80%+ drawdowns of
raw buy-and-hold while still capturing most of a multi-decade trend.
"""
from __future__ import annotations

from .base import Order, OrderAction, Strategy, StrategyContext, atr


class SwingTrend(Strategy):
    name = "swing_trend"

    def __init__(
        self,
        entry_period: int = 55,
        exit_period: int = 20,
        atr_period: int = 20,
        atr_stop_mult: float = 3.0,
        allow_short: bool = True,
    ):
        super().__init__(
            entry_period=entry_period,
            exit_period=exit_period,
            atr_period=atr_period,
            atr_stop_mult=atr_stop_mult,
            allow_short=allow_short,
        )
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.allow_short = allow_short

    def reset(self) -> None:
        pass

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        history = ctx.history
        min_bars = max(self.entry_period, self.atr_period) + 1
        if len(history) < min_bars:
            return []

        # Use prior bars only -- don't peek at today's own high/low to define today's breakout level.
        prior = history.iloc[:-1]
        entry_high = prior["high"].rolling(self.entry_period).max().iloc[-1]
        entry_low = prior["low"].rolling(self.entry_period).min().iloc[-1]
        exit_high = prior["high"].rolling(self.exit_period).max().iloc[-1]
        exit_low = prior["low"].rolling(self.exit_period).min().iloc[-1]
        current_atr = atr(history, self.atr_period).iloc[-1]
        if current_atr != current_atr:
            return []

        bar = ctx.bar
        pos = ctx.position
        price = bar["close"]

        if pos.side == "long":
            if price <= pos.stop_price or price < exit_low:
                return [Order(OrderAction.EXIT, reason="swing_exit_breakdown_or_stop")]
            new_stop = price - self.atr_stop_mult * current_atr
            if new_stop > pos.stop_price:
                return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
            return []

        if pos.side == "short":
            if price >= pos.stop_price or price > exit_high:
                return [Order(OrderAction.EXIT, reason="swing_exit_breakout_or_stop")]
            new_stop = price + self.atr_stop_mult * current_atr
            if new_stop < pos.stop_price:
                return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
            return []

        if price > entry_high:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="swing_breakout_long",
                    stop_price=price - self.atr_stop_mult * current_atr,
                )
            ]
        if self.allow_short and price < entry_low:
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="swing_breakout_short",
                    stop_price=price + self.atr_stop_mult * current_atr,
                )
            ]
        return []
