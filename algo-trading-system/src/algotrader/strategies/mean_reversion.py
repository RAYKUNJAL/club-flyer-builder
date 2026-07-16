"""Mean reversion -- one of the five core system types the vendor's "Alpha Engine" advertises
(trend following, breakout, reversal, mean reversion, fast trend). Classic Bollinger Band fade:
enter against an extreme close outside the bands, target the mean, stop beyond the extreme.
"""
from __future__ import annotations

from .base import Order, OrderAction, Strategy, StrategyContext


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(
        self,
        band_period: int = 20,
        band_std: float = 2.0,
        stop_std: float = 3.0,
    ):
        super().__init__(band_period=band_period, band_std=band_std, stop_std=stop_std)
        self.band_period = band_period
        self.band_std = band_std
        self.stop_std = stop_std

    def reset(self) -> None:
        pass

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        history = ctx.history
        if len(history) < self.band_period + 1:
            return []

        close = history["close"]
        mid = close.rolling(self.band_period).mean()
        std = close.rolling(self.band_period).std()
        mid_now, std_now = mid.iloc[-1], std.iloc[-1]
        if std_now != std_now or std_now == 0:
            return []

        upper = mid_now + self.band_std * std_now
        lower = mid_now - self.band_std * std_now
        stop_upper = mid_now + self.stop_std * std_now
        stop_lower = mid_now - self.stop_std * std_now

        bar = ctx.bar
        pos = ctx.position
        price = bar["close"]

        if pos.side == "long":
            if price >= mid_now or price <= pos.stop_price:
                return [Order(OrderAction.EXIT, reason="reverted_to_mean_or_stop")]
            return []
        if pos.side == "short":
            if price <= mid_now or price >= pos.stop_price:
                return [Order(OrderAction.EXIT, reason="reverted_to_mean_or_stop")]
            return []

        if price <= lower:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="band_fade_long",
                    stop_price=stop_lower,
                    target_price=mid_now,
                )
            ]
        if price >= upper:
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="band_fade_short",
                    stop_price=stop_upper,
                    target_price=mid_now,
                )
            ]
        return []
