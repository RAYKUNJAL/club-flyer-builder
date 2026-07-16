from datetime import time

import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.orb import OpeningRangeBreakout


def _session_bars(closes, start="2024-01-02 09:30"):
    idx = pd.date_range(start, periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.25,
            "low": closes - 0.25,
            "close": closes,
            "volume": 100,
        },
        index=idx,
    )


def test_no_trade_while_range_still_forming():
    strat = OpeningRangeBreakout(range_minutes=30, atr_period=5)
    strat.reset()
    closes = [100 + i * 0.1 for i in range(20)]  # only 20 minutes in, range window is 30
    data = _session_bars(closes)
    ctx = StrategyContext(history=data, position=PositionState())
    orders = strat.on_bar(ctx)
    assert orders == []


def test_breakout_above_range_enters_long():
    strat = OpeningRangeBreakout(range_minutes=15, atr_period=5, atr_stop_mult=1.5, reward_risk=2.0)
    strat.reset()
    # 15 minutes of tight chop around 100 to form the range, then a clean breakout bar.
    range_closes = [100.0, 100.2, 99.9, 100.1, 100.0] * 3
    breakout_closes = [100.0] * 6 + [105.0]  # need >= atr_period+1 bars total after range for ATR
    data = _session_bars(range_closes + breakout_closes)

    orders = []
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        if orders:
            break

    assert len(orders) == 1
    order = orders[0]
    assert order.action == OrderAction.ENTER_LONG
    assert order.stop_price < 105.0 < order.target_price


def test_force_flat_at_session_close():
    strat = OpeningRangeBreakout(range_minutes=15, session_close=time(9, 50))
    strat.reset()
    data = _session_bars([100.0] * 25, start="2024-01-02 09:30")
    pos = PositionState(side="long", entry_price=100.0, stop_price=95.0, target_price=110.0)

    orders = []
    for i in range(len(data)):  # walk bar-by-bar like the real engine does, to populate the day's range state
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)

    # last bar is at 09:54, past session_close (09:50)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "session_close"
