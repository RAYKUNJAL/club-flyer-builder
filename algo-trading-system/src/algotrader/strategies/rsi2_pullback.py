"""RSI-2 pullback -- trend-filtered short-term mean reversion on daily bars.

Archetype: buy sharp, short-lived pullbacks *within* an established long-term uptrend
(and optionally fade sharp rallies within a downtrend), then exit as soon as price
snaps back to its short-term mean. This is the classic "RSI(2)" system published by
Larry Connors and Cesar Alvarez in *Short Term Trading Strategies That Work* (2008)
and *High Probability ETF Trading* (2009):

* ENTRY (long):  close > SMA(trend_period=200)  AND  RSI(rsi_period=2) < oversold (10)
                 -> enter long at the close.
* ENTRY (short, optional via ``enable_shorts``):
                 close < SMA(200)  AND  RSI(2) > overbought (90) -> enter short.
* EXIT:          close crosses back above SMA(exit_ma_period=5) for longs
                 (below for shorts) -- i.e. price has snapped back to the short-term
                 mean; plus a hard time stop after ``max_hold_bars`` (10) bars.
* STOP:          entry -/+ ``stop_atr_mult`` (3.0) * ATR(atr_period=14). The stop is
                 deliberately wide: Connors' research shows tight stops destroy this
                 edge (the whole point is buying temporary weakness), so the *time
                 stop* is the real risk control and the ATR stop is only disaster
                 insurance.

It complements the existing Bollinger-band ``MeanReversion`` archetype: that one fades
statistical extremes in any regime, while this one only fades WITH the 200-day trend.
Historically strongest on liquid index products (ES/NQ daily) and high-beta large caps
such as TSLA on daily bars.
"""
from __future__ import annotations

import pandas as pd

from .base import Order, OrderAction, Strategy, StrategyContext, atr


def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder-smoothed RSI, as used in the original Connors RSI(2) research."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    # No losses in the window -> RSI pegs at 100; no gains -> 0.
    rsi = rsi.where(avg_loss > 0, 100.0)
    rsi = rsi.where((avg_gain > 0) | (avg_loss > 0), 50.0)
    return rsi


class Rsi2Pullback(Strategy):
    name = "rsi2_pullback"

    def __init__(
        self,
        rsi_period: int = 2,
        oversold: float = 10.0,
        overbought: float = 90.0,
        trend_period: int = 200,
        exit_ma_period: int = 5,
        max_hold_bars: int = 10,
        stop_atr_mult: float = 3.0,
        atr_period: int = 14,
        enable_shorts: bool = False,
    ):
        super().__init__(
            rsi_period=rsi_period,
            oversold=oversold,
            overbought=overbought,
            trend_period=trend_period,
            exit_ma_period=exit_ma_period,
            max_hold_bars=max_hold_bars,
            stop_atr_mult=stop_atr_mult,
            atr_period=atr_period,
            enable_shorts=enable_shorts,
        )
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.trend_period = trend_period
        self.exit_ma_period = exit_ma_period
        self.max_hold_bars = max_hold_bars
        self.stop_atr_mult = stop_atr_mult
        self.atr_period = atr_period
        self.enable_shorts = enable_shorts

    def reset(self) -> None:
        pass

    def _bars_since_entry(self, ctx: StrategyContext) -> int:
        pos = ctx.position
        if pos.entry_time is not None:
            return int((ctx.history.index > pos.entry_time).sum())
        return pos.bars_held

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        history = ctx.history
        close = history["close"]
        price = ctx.bar["close"]
        pos = ctx.position

        # ---- manage an open position ------------------------------------
        if pos.side is not None:
            if self._bars_since_entry(ctx) >= self.max_hold_bars:
                return [Order(OrderAction.EXIT, reason="time_stop")]
            if len(history) < self.exit_ma_period:
                return []
            exit_ma = close.rolling(self.exit_ma_period).mean().iloc[-1]
            if exit_ma != exit_ma:  # NaN guard
                return []
            if pos.side == "long" and price > exit_ma:
                return [Order(OrderAction.EXIT, reason="snapback_above_exit_ma")]
            if pos.side == "short" and price < exit_ma:
                return [Order(OrderAction.EXIT, reason="snapback_below_exit_ma")]
            return []

        # ---- look for a new entry (uses only history up to current bar) --
        warmup = max(self.trend_period, self.atr_period + 1, self.rsi_period + 1)
        if len(history) < warmup:
            return []

        trend_ma = close.rolling(self.trend_period).mean().iloc[-1]
        rsi_now = wilder_rsi(close, self.rsi_period).iloc[-1]
        atr_now = atr(history, self.atr_period).iloc[-1]
        if trend_ma != trend_ma or rsi_now != rsi_now or atr_now != atr_now:
            return []

        if price > trend_ma and rsi_now < self.oversold:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="rsi2_pullback_long",
                    stop_price=price - self.stop_atr_mult * atr_now,
                )
            ]
        if self.enable_shorts and price < trend_ma and rsi_now > self.overbought:
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="rsi2_pullback_short",
                    stop_price=price + self.stop_atr_mult * atr_now,
                )
            ]
        return []
