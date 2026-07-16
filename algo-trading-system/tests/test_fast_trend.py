import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.fast_trend import FastTrend


def _session_bars(closes):
    idx = pd.date_range("2024-01-02 09:30", periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.1, "low": closes - 0.1, "close": closes, "volume": 100}, index=idx
    )


def test_strong_opening_drive_triggers_one_long_trade():
    strat = FastTrend(drive_minutes=5, momentum_threshold_points=15, target_points=20, stop_points=10)
    strat.reset()
    closes = [100.0, 105.0, 110.0, 118.0, 122.0]  # +22 points in 5 minutes -- clears the 15pt threshold
    data = _session_bars(closes)

    orders = []
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        if orders:
            break

    assert len(orders) == 1
    assert orders[0].action == OrderAction.ENTER_LONG
    entry_close = data["close"].iloc[i]
    assert orders[0].target_price == entry_close + 20
    assert orders[0].stop_price == entry_close - 10


def test_weak_open_does_not_trade():
    strat = FastTrend(drive_minutes=5, momentum_threshold_points=15)
    strat.reset()
    closes = [100.0, 100.5, 101.0, 100.8, 101.2]  # well under threshold
    data = _session_bars(closes)
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        assert strat.on_bar(ctx) == []


def test_timeout_exit_after_max_hold():
    strat = FastTrend(max_hold_minutes=10)
    strat.reset()
    data = _session_bars([100.0] * 20)
    entry_time = data.index[0]
    pos = PositionState(side="long", entry_price=100.0, stop_price=90.0, target_price=120.0, entry_time=entry_time)
    ctx = StrategyContext(history=data, position=pos)  # 19 minutes elapsed > max_hold_minutes
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "max_hold_timeout"
