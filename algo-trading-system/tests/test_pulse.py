import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.pulse import Pulse


def _bars(closes):
    idx = pd.date_range("2024-01-02 09:30", periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + 0.3, "low": closes - 0.3, "close": closes, "volume": 100}, index=idx
    )


def test_sustained_uptrend_eventually_enters_long():
    strat = Pulse(fast_period=5, slow_period=10, atr_period=5, min_spread_atr_mult=0.05)
    strat.reset()
    flat = [100.0] * 15
    uptrend = [100.0 + i * 1.5 for i in range(1, 20)]
    data = _bars(flat + uptrend)

    entered = False
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        if orders and orders[0].action == OrderAction.ENTER_LONG:
            entered = True
            break
    assert entered


def test_trailing_stop_ratchets_up_and_never_down():
    strat = Pulse(fast_period=5, slow_period=10, atr_period=5, trail_atr_mult=2.0)
    strat.reset()
    uptrend = [100.0 + i for i in range(30)]
    data = _bars(uptrend)
    pos = PositionState(side="long", entry_price=105.0, stop_price=90.0)

    stops = []
    for i in range(15, len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)
        for o in orders:
            if o.action == OrderAction.UPDATE_STOP:
                assert o.stop_price >= pos.stop_price
                pos.stop_price = o.stop_price
                stops.append(o.stop_price)
    assert len(stops) > 0
    assert stops == sorted(stops)
