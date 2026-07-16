import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.mean_reversion import MeanReversion


def _bars(closes):
    idx = pd.date_range("2024-01-02", periods=len(closes), freq="B")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.2, "low": closes - 0.2, "close": closes, "volume": 100}, index=idx
    )


def test_sharp_drop_below_lower_band_fades_long():
    strat = MeanReversion(band_period=10, band_std=2.0, stop_std=3.0)
    strat.reset()
    stable = [100.0] * 15
    plunge = [95.0, 90.0, 85.0]  # sharp drop well outside a tight band built on stable prices
    data = _bars(stable + plunge)

    ctx = StrategyContext(history=data, position=PositionState())
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.ENTER_LONG
    assert orders[0].target_price > data["close"].iloc[-1]


def test_exit_on_reversion_to_mean():
    strat = MeanReversion(band_period=10, band_std=2.0)
    strat.reset()
    stable = [100.0, 100.1, 99.9, 100.2, 99.8, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.1, 99.9, 100.0, 100.0]
    data = _bars(stable)
    pos = PositionState(side="long", entry_price=90.0, stop_price=80.0, target_price=100.0)
    ctx = StrategyContext(history=data, position=pos)  # close (100) has reached/crossed the mean
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
