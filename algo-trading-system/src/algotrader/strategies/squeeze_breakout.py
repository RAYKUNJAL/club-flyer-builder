"""Volatility-compression breakout -- the "Squeeze" archetype.

Trades the volatility cycle itself rather than trend or mean reversion: periods of unusually
low volatility tend to be followed by explosive directional expansion. The canonical setups are
John Bollinger's "Squeeze" (Bollinger, *Bollinger on Bollinger Bands*, 2001, ch. 15) and John
Carter's TTM Squeeze indicator (Carter, *Mastering the Trade*, 2005), which formalizes the
compression test as Bollinger Bands trading fully inside a Keltner Channel.

Mechanics:
- SQUEEZE ON: the 20-period / 2-sigma Bollinger Bands sit entirely inside the Keltner Channel
  (20-period EMA midline +/- kc_atr_mult * ATR) for at least ``min_squeeze_bars`` consecutive
  bars. That is the compression phase -- energy is being stored.
- FIRE: the bands re-expand outside the Keltner Channel. Enter in the direction of momentum,
  measured TTM-style as close minus the average of the Donchian midpoint and the SMA over
  ``mom_period`` bars (a de-trended momentum proxy; positive -> long, negative -> short).
- RISK: initial stop at entry -/+ ``stop_atr_mult`` * ATR (engine-level via stop_price on the
  entry order); thereafter the stop trails the best close by ``trail_atr_mult`` * ATR
  (ratcheting only, via UPDATE_STOP). Also exit if momentum flips against the position for
  ``exit_mom_flip_bars`` consecutive bars -- the expansion has failed.

This fills the volatility archetype in the book: it needs no pre-existing trend (unlike the
trend/pulse sleeve) and trades expansion away from the mean rather than reversion to it
(unlike the mean-reversion sleeve), so it diversifies against both. Works on daily and
intraday bars alike since every input is expressed in bars and ATR units.
"""
from __future__ import annotations

from .base import Order, OrderAction, Strategy, StrategyContext, atr


class SqueezeBreakout(Strategy):
    name = "squeeze_breakout"

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_period: int = 20,
        kc_atr_mult: float = 1.5,
        min_squeeze_bars: int = 5,
        mom_period: int = 12,
        atr_period: int = 14,
        stop_atr_mult: float = 2.0,
        trail_atr_mult: float = 2.5,
        exit_mom_flip_bars: int = 2,
    ):
        super().__init__(
            bb_period=bb_period,
            bb_std=bb_std,
            kc_period=kc_period,
            kc_atr_mult=kc_atr_mult,
            min_squeeze_bars=min_squeeze_bars,
            mom_period=mom_period,
            atr_period=atr_period,
            stop_atr_mult=stop_atr_mult,
            trail_atr_mult=trail_atr_mult,
            exit_mom_flip_bars=exit_mom_flip_bars,
        )
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.kc_period = kc_period
        self.kc_atr_mult = kc_atr_mult
        self.min_squeeze_bars = min_squeeze_bars
        self.mom_period = mom_period
        self.atr_period = atr_period
        self.stop_atr_mult = stop_atr_mult
        self.trail_atr_mult = trail_atr_mult
        self.exit_mom_flip_bars = exit_mom_flip_bars
        self.reset()

    def reset(self) -> None:
        self._squeeze_run = 0  # consecutive bars with the squeeze on
        self._armed = False  # squeeze has lasted >= min_squeeze_bars, waiting for the fire
        self._flip_run = 0  # consecutive bars momentum has pointed against the open position
        self._best_close = None  # best close since entry, for the ATR trail

    def _min_bars(self) -> int:
        return max(self.bb_period, self.kc_period, self.atr_period, self.mom_period) + 1

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        history = ctx.history
        if len(history) < self._min_bars():
            return []

        close = history["close"]
        high = history["high"]
        low = history["low"]

        current_atr = atr(history, self.atr_period).iloc[-1]
        if current_atr != current_atr:  # NaN guard
            return []

        # Bollinger Bands
        bb_mid = close.rolling(self.bb_period).mean().iloc[-1]
        bb_sd = close.rolling(self.bb_period).std().iloc[-1]
        if bb_sd != bb_sd:
            return []
        bb_upper = bb_mid + self.bb_std * bb_sd
        bb_lower = bb_mid - self.bb_std * bb_sd

        # Keltner Channel: EMA midline +/- ATR envelope
        kc_mid = close.ewm(span=self.kc_period, adjust=False).mean().iloc[-1]
        kc_upper = kc_mid + self.kc_atr_mult * current_atr
        kc_lower = kc_mid - self.kc_atr_mult * current_atr

        squeeze_on = bb_upper < kc_upper and bb_lower > kc_lower

        # TTM-style momentum: close minus the average of Donchian midpoint and SMA.
        don_mid = (high.rolling(self.mom_period).max().iloc[-1] + low.rolling(self.mom_period).min().iloc[-1]) / 2.0
        sma = close.rolling(self.mom_period).mean().iloc[-1]
        momentum = close.iloc[-1] - (don_mid + sma) / 2.0

        bar = ctx.bar
        pos = ctx.position
        price = bar["close"]

        if pos.side is not None:
            return self._manage_position(pos, price, current_atr, momentum)

        # Flat: track the compression phase.
        self._flip_run = 0
        self._best_close = None
        if squeeze_on:
            self._squeeze_run += 1
            if self._squeeze_run >= self.min_squeeze_bars:
                self._armed = True
            return []

        # Squeeze is off on this bar.
        fired = self._armed  # bands re-expanded after a qualifying squeeze
        self._squeeze_run = 0
        self._armed = False
        if not fired or momentum == 0:
            return []

        if momentum > 0:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="squeeze_fire_long",
                    stop_price=price - self.stop_atr_mult * current_atr,
                )
            ]
        return [
            Order(
                OrderAction.ENTER_SHORT,
                reason="squeeze_fire_short",
                stop_price=price + self.stop_atr_mult * current_atr,
            )
        ]

    def _manage_position(self, pos, price: float, current_atr: float, momentum: float) -> list[Order]:
        # Momentum-flip exit: expansion failed if momentum points the wrong way for
        # exit_mom_flip_bars consecutive bars.
        against = (pos.side == "long" and momentum < 0) or (pos.side == "short" and momentum > 0)
        self._flip_run = self._flip_run + 1 if against else 0
        if self._flip_run >= self.exit_mom_flip_bars:
            self._flip_run = 0
            self._best_close = None
            return [Order(OrderAction.EXIT, reason="momentum_flip")]

        # Trail the stop off the best close since entry (ratchet only, never loosen).
        if pos.side == "long":
            self._best_close = price if self._best_close is None else max(self._best_close, price)
            new_stop = self._best_close - self.trail_atr_mult * current_atr
            if pos.stop_price is None or new_stop > pos.stop_price:
                return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
            return []

        self._best_close = price if self._best_close is None else min(self._best_close, price)
        new_stop = self._best_close + self.trail_atr_mult * current_atr
        if pos.stop_price is None or new_stop < pos.stop_price:
            return [Order(OrderAction.UPDATE_STOP, stop_price=new_stop, reason="trail_ratchet")]
        return []
