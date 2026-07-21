"""Live trading loop: feed real-time bars into a Strategy and route its orders to a Broker.

Data-feed-agnostic by design -- you supply a `fetch_latest_bar()` callable (poll yfinance,
a Tradovate/NinjaTrader market-data bridge, whatever you actually have live-tick access to).
The runner handles the strategy/position/order bookkeeping, identically to the backtest engine
(same engine-level stop/target enforcement against each new bar), so a strategy behaves the
same live as it did in the backtest.

Safety model:
- On entry a protective stop order is rested BROKER-SIDE (if the broker supports it), so the
  position stays protected even if this process crashes, the data feed stalls, or the network
  drops. The polled bar-by-bar stop check below is a backup/manager, not the only line of
  defense.
- Stop updates from the strategy are accepted only if they keep or tighten risk; a widened or
  removed stop would silently exceed the configured per-trade risk cap.
- A daily loss cap (risk_sizer.daily_loss_limit_hit) halts new entries for the rest of the day.
- The polling loop never dies on a single bad bar/broker hiccup: exceptions are logged and the
  loop continues (the broker-side stop is what bounds risk in the meantime).
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import pandas as pd

TradeCallback = Callable[[dict], None]

from ..risk.position_sizing import PositionSizer
from ..strategies.base import OrderAction, PositionState, Strategy, StrategyContext
from .broker_base import Broker

logger = logging.getLogger(__name__)

FetchBarFn = Callable[[], Optional[tuple[pd.Timestamp, pd.Series]]]


class LiveRunner:
    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        risk_sizer: PositionSizer,
        symbol: str,
        max_history_bars: int = 500,
        on_trade_closed: Optional[TradeCallback] = None,
    ):
        self.strategy = strategy
        self.broker = broker
        self.risk_sizer = risk_sizer
        self.symbol = symbol
        self.max_history_bars = max_history_bars
        self.on_trade_closed = on_trade_closed
        self._history = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self._pos = PositionState()
        self._stop_order_id: Optional[str] = None
        self._current_day: Optional[pd.Timestamp] = None
        self._day_start_equity: Optional[float] = None

    def on_new_bar(self, ts: pd.Timestamp, bar: pd.Series) -> None:
        if hasattr(self.broker, "update_quote"):
            self.broker.update_quote(self.symbol, bar["close"])  # e.g. PaperBroker needs a quote before it can fill

        self._history.loc[ts] = bar
        if len(self._history) > self.max_history_bars:
            self._history = self._history.iloc[-self.max_history_bars :]

        # New trading day: reset the daily-loss-cap baseline.
        day = ts.normalize()
        if self._current_day is None or day != self._current_day:
            self._current_day = day
            self._day_start_equity = self.broker.get_equity()

        if self._pos.side is not None:
            self._pos.bars_held += 1
            hit_price, reason = self._check_stop_target(bar)
            if hit_price is not None:
                self._exit(reason, hit_price, ts)
                return

        ctx = StrategyContext(history=self._history, position=self._pos)
        for order in self.strategy.on_bar(ctx):
            if order.action == OrderAction.UPDATE_STOP and self._pos.side is not None:
                self._update_stop(order.stop_price)
            elif order.action == OrderAction.EXIT and self._pos.side is not None:
                self._exit(order.reason, bar["close"], ts)
            elif order.action in (OrderAction.ENTER_LONG, OrderAction.ENTER_SHORT) and self._pos.side is None:
                self._enter(order, bar["close"], ts)

    def _enter(self, order, price: float, ts: pd.Timestamp) -> None:
        side = "long" if order.action == OrderAction.ENTER_LONG else "short"
        equity = self.broker.get_equity()
        if self._day_start_equity is not None and self.risk_sizer.daily_loss_limit_hit(
            self._day_start_equity, equity
        ):
            logger.info(
                "skip entry: daily loss cap hit (day_start=%.2f, current=%.2f)",
                self._day_start_equity, equity,
            )
            return
        contracts = self.risk_sizer.size(equity, price, order.stop_price) if order.stop_price is not None else 0
        if contracts <= 0:
            logger.info("skip entry: risk sizing returned 0 contracts (equity=%.2f, stop=%s)", equity, order.stop_price)
            return
        broker_side = "buy" if side == "long" else "sell"
        self.broker.place_market_order(self.symbol, broker_side, contracts)
        self._pos = PositionState(
            side=side,
            entry_price=price,
            stop_price=order.stop_price,
            target_price=order.target_price,
            entry_time=ts,
            meta={"entry_reason": order.reason, "contracts": contracts},
        )
        self._place_protective_stop(contracts, order.stop_price)
        logger.info("ENTER %s %s x%d @ %.2f (%s)", side, self.symbol, contracts, price, order.reason)

    def _place_protective_stop(self, contracts: int, stop_price: Optional[float]) -> None:
        """Rest the stop at the broker so the position is protected even if this process dies."""
        if stop_price is None:
            return
        stop_side = "sell" if self._pos.side == "long" else "buy"
        try:
            self._stop_order_id = self.broker.place_stop_order(self.symbol, stop_side, contracts, stop_price)
        except NotImplementedError:
            self._stop_order_id = None
            logger.warning(
                "broker %s does not support resting stop orders -- position is only "
                "protected by this process's polled stop check",
                type(self.broker).__name__,
            )

    def _cancel_protective_stop(self) -> None:
        if self._stop_order_id is None:
            return
        try:
            self.broker.cancel_order(self._stop_order_id)
        except NotImplementedError:
            pass
        self._stop_order_id = None

    def _update_stop(self, new_stop: Optional[float]) -> None:
        pos = self._pos
        # Accept only updates that keep or tighten risk (trailing-stop ratchets); a widened
        # or removed stop would exceed the configured per-trade risk cap unchecked.
        if new_stop is None or new_stop != new_stop:  # None or NaN
            logger.warning("rejected stop update to %s: stop may not be removed", new_stop)
            return
        if pos.stop_price is not None:
            loosens = (pos.side == "long" and new_stop < pos.stop_price) or (
                pos.side == "short" and new_stop > pos.stop_price
            )
            if loosens:
                logger.warning(
                    "rejected stop update %s -> %s: widening the stop would exceed the per-trade risk cap",
                    pos.stop_price, new_stop,
                )
                return
        pos.stop_price = new_stop
        # Cancel/replace the broker-side stop to match.
        contracts = pos.meta.get("contracts", 0)
        self._cancel_protective_stop()
        self._place_protective_stop(contracts, new_stop)

    def _exit(self, reason: str, exit_price: float, ts: Optional[pd.Timestamp] = None) -> None:
        self._cancel_protective_stop()
        self.broker.flatten(self.symbol)
        pos = self._pos
        logger.info("EXIT %s %s (%s)", pos.side, self.symbol, reason)
        if self.on_trade_closed is not None and pos.side is not None:
            direction = 1 if pos.side == "long" else -1
            contracts = pos.meta.get("contracts", 0)
            point_value = getattr(self.risk_sizer.config, "point_value", 1.0)
            self.on_trade_closed({
                "side": pos.side,
                "entry_time": str(pos.entry_time),
                "exit_time": str(ts) if ts is not None else None,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "contracts": contracts,
                "pnl": (exit_price - pos.entry_price) * direction * contracts * point_value,
                "entry_reason": pos.meta.get("entry_reason", ""),
                "exit_reason": reason,
            })
        self._pos = PositionState()

    def _check_stop_target(self, bar: pd.Series) -> tuple[Optional[float], str]:
        # Gap-aware, mirroring the backtest engine: a bar that OPENS through the stop fills
        # at the worse of open vs stop (the trigger price is unreachable after a gap).
        pos = self._pos
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

    def run_forever(self, fetch_latest_bar: FetchBarFn, poll_interval_seconds: float = 60.0) -> None:
        logger.info("live runner starting for %s using strategy=%s", self.symbol, self.strategy.name)
        while True:
            try:
                result = fetch_latest_bar()
                if result is not None:
                    ts, bar = result
                    self.on_new_bar(ts, bar)
            except Exception:
                # Never let one bad bar / transient broker error kill the live loop and
                # orphan an open position. The broker-side stop bounds risk meanwhile.
                logger.exception("error handling bar; continuing (broker-side stop still resting)")
            time.sleep(poll_interval_seconds)
