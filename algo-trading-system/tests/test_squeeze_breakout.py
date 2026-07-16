import numpy as np
import pandas as pd
import pytest

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext, atr
from algotrader.strategies.squeeze_breakout import SqueezeBreakout


def _bars(closes, spread=0.3):
    idx = pd.date_range("2024-01-02 09:30", periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + spread, "low": closes - spread, "close": closes, "volume": 100},
        index=idx,
    )


def _squeeze_then_breakout(direction=1):
    """Long flat compression (BB inside KC), then a violent expansion in `direction`."""
    flat = [100.0] * 60
    breakout = [100.0 + direction * 4.0 * i for i in range(1, 8)]
    return _bars(flat + breakout)


def _run_flat(strat, data):
    """Feed bars one at a time while flat; return (bar_index, first_order) or (None, None)."""
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        if orders:
            return i, orders[0]
    return None, None


def test_enters_long_on_upside_expansion_after_squeeze():
    strat = SqueezeBreakout()
    strat.reset()
    data = _squeeze_then_breakout(direction=1)

    i, order = _run_flat(strat, data)
    assert order is not None, "expected an entry when the bands fired out of the squeeze"
    assert order.action == OrderAction.ENTER_LONG
    assert i >= 60, "must not fire during the compression phase"
    # Risk: engine-level stop attached to the entry, stop_atr_mult * ATR below the close.
    hist = data.iloc[: i + 1]
    expected_atr = atr(hist, strat.atr_period).iloc[-1]
    assert order.stop_price is not None
    assert order.stop_price == pytest.approx(hist["close"].iloc[-1] - 2.0 * expected_atr)
    assert order.stop_price < hist["close"].iloc[-1]


def test_enters_short_on_downside_expansion_after_squeeze():
    strat = SqueezeBreakout()
    strat.reset()
    data = _squeeze_then_breakout(direction=-1)

    i, order = _run_flat(strat, data)
    assert order is not None
    assert order.action == OrderAction.ENTER_SHORT
    hist = data.iloc[: i + 1]
    expected_atr = atr(hist, strat.atr_period).iloc[-1]
    assert order.stop_price == pytest.approx(hist["close"].iloc[-1] + 2.0 * expected_atr)
    assert order.stop_price > hist["close"].iloc[-1]


def test_no_entry_without_qualifying_squeeze_duration():
    # Same expansion, but require an implausibly long squeeze first -- must stay flat.
    strat = SqueezeBreakout(min_squeeze_bars=500)
    strat.reset()
    data = _squeeze_then_breakout(direction=1)
    _, order = _run_flat(strat, data)
    assert order is None


def test_trailing_stop_ratchets_up_and_never_down():
    strat = SqueezeBreakout()
    strat.reset()
    uptrend = [100.0 + i for i in range(40)]
    data = _bars(uptrend)
    pos = PositionState(side="long", entry_price=105.0, stop_price=90.0)

    stops = []
    for i in range(25, len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)
        for o in orders:
            if o.action == OrderAction.UPDATE_STOP:
                assert o.stop_price >= pos.stop_price
                pos.stop_price = o.stop_price
                stops.append(o.stop_price)
    assert len(stops) > 0
    assert stops == sorted(stops)


def test_momentum_flip_exits_long_after_consecutive_flip_bars():
    strat = SqueezeBreakout()
    strat.reset()
    flat = [100.0] * 15
    rise = [100.0 + i for i in range(1, 21)]  # up to 120
    drop = [112.0, 104.0, 96.0, 88.0]  # momentum flips hard negative
    data = _bars(flat + rise + drop)
    pos = PositionState(side="long", entry_price=105.0, stop_price=50.0)

    exit_bar = None
    first_drop = len(flat) + len(rise)
    for i in range(25, len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)
        for o in orders:
            if o.action == OrderAction.UPDATE_STOP:
                pos.stop_price = o.stop_price
            if o.action == OrderAction.EXIT:
                exit_bar = i
                assert o.reason == "momentum_flip"
        if exit_bar is not None:
            break
    assert exit_bar is not None, "expected a momentum-flip exit"
    # Needs exit_mom_flip_bars (2) consecutive against-bars: not before the second drop bar.
    assert exit_bar >= first_drop + 1
