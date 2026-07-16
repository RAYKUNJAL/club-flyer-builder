"""Strategy contract shared by every archetype (ORB, fast-trend, pulse, mean-reversion, swing-trend).

None of these reproduce a specific vendor's tuned parameters -- those aren't public. Each implements
the well-documented technical-analysis pattern the vendor's marketing copy describes, with parameters
exposed so they can be fit/tuned against real data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Optional

import pandas as pd


class OrderAction(Enum):
    ENTER_LONG = "enter_long"
    ENTER_SHORT = "enter_short"
    EXIT = "exit"
    UPDATE_STOP = "update_stop"


@dataclass
class Order:
    action: OrderAction
    reason: str = ""
    stop_price: Optional[float] = None
    target_price: Optional[float] = None


@dataclass
class PositionState:
    side: Optional[str] = None  # "long" | "short" | None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    entry_time: Optional[pd.Timestamp] = None
    bars_held: int = 0
    meta: dict = field(default_factory=dict)


class StrategyContext:
    """Read-only view the strategy gets each bar: rolling history + current position state."""

    def __init__(self, history: pd.DataFrame, position: PositionState):
        self.history = history  # includes the current bar as the last row
        self.position = position

    @property
    def bar(self) -> pd.Series:
        return self.history.iloc[-1]

    @property
    def ts(self) -> pd.Timestamp:
        return self.history.index[-1]

    def lookback(self, n: int) -> pd.DataFrame:
        return self.history.iloc[-n:]


def minutes_since_session_open(ts: pd.Timestamp, session_open: time) -> int:
    open_dt = ts.replace(hour=session_open.hour, minute=session_open.minute, second=0, microsecond=0)
    return int((ts - open_dt).total_seconds() // 60)


def true_range(history: pd.DataFrame) -> pd.Series:
    high, low, close = history["high"], history["low"], history["close"]
    prev_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(history: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(history).rolling(period).mean()


class Strategy:
    """Base class. Subclasses implement on_bar and return a list of Orders (usually 0 or 1)."""

    name = "base"

    def __init__(self, **params):
        self.params = params

    def reset(self) -> None:
        """Called at the start of each backtest run / trading day where relevant."""

    def on_bar(self, ctx: StrategyContext) -> list[Order]:
        raise NotImplementedError
