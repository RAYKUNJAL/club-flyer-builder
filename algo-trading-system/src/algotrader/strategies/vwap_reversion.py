"""VWAP Reversion -- intraday mean reversion to the session-anchored VWAP.

Complements ORB (the other intraday archetype): ORB trades the breakout of the
opening range, this strategy fades intraday stretches away from "fair value".
The session VWAP is the classic institutional fair-value benchmark -- it is the
price the average participant paid since the open (Berkowitz, Logue & Noser,
"The Total Cost of Transactions on the NYSE", Journal of Finance, 1988, which
introduced VWAP as the standard execution benchmark; see also Madhavan, "VWAP
Strategies", Transaction Performance, 2002). When price stretches far from
VWAP intraday, execution desks and market makers lean against the move, which
produces the well-documented intraday reversion toward VWAP that prop-desk
band-fade systems exploit (the "VWAP bands" construction is described in
Kissell & Glantz, "Optimal Trading Strategies", 2003, and is the intraday
analogue of the Bollinger fade in ``mean_reversion.py``).

Mechanics:
- Session-anchored VWAP: cumulative sum of typical_price * volume divided by
  cumulative volume since ``session_open``, re-anchored every trading day.
- Stretch unit: rolling standard deviation of (close - VWAP) over
  ``dev_period`` bars within the session.
- ENTRY LONG when close < VWAP - entry_dev * stretch_std (mirror for SHORT),
  only after ``warmup_bars`` bars of the session have printed and strictly
  before ``no_new_entries_after`` exchange time.
- TARGET: the VWAP itself (exit when the close crosses back through it).
- STOP: entry -/+ stop_dev * stretch_std -- the stretch continuing to a
  larger extreme falsifies the fade.
- Time stop after ``max_hold_bars`` bars, and a mandatory flat at
  ``session_eod_flat`` -- no overnight holds.

Best suited to liquid index/commodity futures intraday bars (ES, NQ, CL, GC
on 1-5 minute or 15-minute bars) where the VWAP magnet effect is strongest.
"""
from __future__ import annotations

from datetime import time

from .base import Order, OrderAction, Strategy, StrategyContext


def _to_time(value: time | str) -> time:
    if isinstance(value, time):
        return value
    hour, minute = str(value).split(":")
    return time(int(hour), int(minute))


class VwapReversion(Strategy):
    name = "vwap_reversion"

    def __init__(
        self,
        entry_dev: float = 2.0,
        stop_dev: float = 3.5,
        dev_period: int = 30,
        warmup_bars: int = 30,
        max_hold_bars: int = 60,
        session_open: time | str = time(9, 30),
        no_new_entries_after: time | str = time(14, 30),
        session_eod_flat: time | str = time(15, 55),
    ):
        session_open = _to_time(session_open)
        no_new_entries_after = _to_time(no_new_entries_after)
        session_eod_flat = _to_time(session_eod_flat)
        super().__init__(
            entry_dev=entry_dev,
            stop_dev=stop_dev,
            dev_period=dev_period,
            warmup_bars=warmup_bars,
            max_hold_bars=max_hold_bars,
            session_open=session_open,
            no_new_entries_after=no_new_entries_after,
            session_eod_flat=session_eod_flat,
        )
        self.entry_dev = entry_dev
        self.stop_dev = stop_dev
        self.dev_period = dev_period
        self.warmup_bars = warmup_bars
        self.max_hold_bars = max_hold_bars
        self.session_open = session_open
        self.no_new_entries_after = no_new_entries_after
        self.session_eod_flat = session_eod_flat

    def reset(self) -> None:
        pass  # VWAP is re-anchored from history each bar; no carried state.

    def _session_slice(self, ctx: StrategyContext):
        """Rows of the current trading day at/after session_open, up to the current bar only."""
        history = ctx.history
        ts = ctx.ts
        idx = history.index
        mask = (idx.normalize() == ts.normalize()) & (idx.time >= self.session_open)
        return history.loc[mask]

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        ts = ctx.ts
        pos = ctx.position

        session = self._session_slice(ctx)
        if session.empty:
            # Outside the session (e.g. premarket bars): never hold overnight.
            if pos.side is not None:
                return [Order(OrderAction.EXIT, reason="outside_session_flat")]
            return []

        # Session-anchored VWAP (cumulative typical-price * volume / cumulative volume).
        typical = (session["high"] + session["low"] + session["close"]) / 3.0
        cum_volume = session["volume"].cumsum()
        if cum_volume.iloc[-1] <= 0:
            return []
        vwap = (typical * session["volume"]).cumsum() / cum_volume
        vwap_now = vwap.iloc[-1]

        deviation = session["close"] - vwap
        stretch_std = deviation.rolling(self.dev_period).std().iloc[-1]

        close = ctx.bar["close"]

        # ---- manage an open position ----
        if pos.side is not None:
            if ts.time() >= self.session_eod_flat:
                return [Order(OrderAction.EXIT, reason="session_eod_flat")]
            if pos.side == "long":
                if pos.stop_price is not None and close <= pos.stop_price:
                    return [Order(OrderAction.EXIT, reason="stop_hit")]
                if close >= vwap_now:
                    return [Order(OrderAction.EXIT, reason="vwap_target_touch")]
            else:  # short
                if pos.stop_price is not None and close >= pos.stop_price:
                    return [Order(OrderAction.EXIT, reason="stop_hit")]
                if close <= vwap_now:
                    return [Order(OrderAction.EXIT, reason="vwap_target_touch")]
            if pos.bars_held >= self.max_hold_bars:
                return [Order(OrderAction.EXIT, reason="max_hold_time_stop")]
            return []

        # ---- flat: look for a new fade ----
        if len(session) < self.warmup_bars:
            return []  # too early in the session for a stable VWAP/stretch estimate
        if not (self.session_open <= ts.time() < self.no_new_entries_after):
            return []
        if stretch_std != stretch_std or stretch_std <= 0:  # NaN / degenerate guard
            return []

        if close < vwap_now - self.entry_dev * stretch_std:
            return [
                Order(
                    OrderAction.ENTER_LONG,
                    reason="vwap_stretch_fade_long",
                    stop_price=close - self.stop_dev * stretch_std,
                    target_price=vwap_now,
                )
            ]
        if close > vwap_now + self.entry_dev * stretch_std:
            return [
                Order(
                    OrderAction.ENTER_SHORT,
                    reason="vwap_stretch_fade_short",
                    stop_price=close + self.stop_dev * stretch_std,
                    target_price=vwap_now,
                )
            ]
        return []
