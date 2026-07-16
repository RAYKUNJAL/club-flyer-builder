import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.rsi2_pullback import Rsi2Pullback


def _bars(closes, spread=1.0, start="2022-01-03"):
    idx = pd.date_range(start, periods=len(closes), freq="B")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + spread,
            "low": closes - spread,
            "close": closes,
            "volume": 1000,
        },
        index=idx,
    )


def _uptrend_with_pullback(trend_len=220, pullback_len=3):
    """Long steady uptrend, then a sharp multi-day pullback that stays above SMA(200)."""
    trend = [100.0 + 0.5 * i for i in range(trend_len)]
    pullback = [trend[-1] - 3.0 * (i + 1) for i in range(pullback_len)]
    return trend + pullback


def _run_flat(strat, data):
    """Feed bars one at a time while flat; return (bar_index, orders) of first emitted order."""
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        if orders:
            return i, orders
    return None, []


def test_enters_long_on_pullback_within_uptrend_with_atr_stop():
    strat = Rsi2Pullback()
    strat.reset()
    closes = _uptrend_with_pullback()
    data = _bars(closes)

    i, orders = _run_flat(strat, data)
    assert i is not None, "expected an entry during the pullback"
    assert i >= 220, "must not enter before the pullback starts"
    order = orders[0]
    assert order.action == OrderAction.ENTER_LONG
    # Risk logic: engine-level stop must be attached, below entry, and wide (3x ATR).
    entry_price = data["close"].iloc[i]
    assert order.stop_price is not None
    assert order.stop_price < entry_price
    assert entry_price - order.stop_price >= 2.0  # 3 * ATR(14) with true range >= ~2


def test_no_entry_during_smooth_uptrend_without_pullback():
    strat = Rsi2Pullback()
    strat.reset()
    data = _bars([100.0 + 0.5 * i for i in range(240)])  # never a down close
    i, orders = _run_flat(strat, data)
    assert orders == []


def test_no_entry_when_pullback_is_below_trend_filter():
    """RSI(2) is pinned low in a persistent downtrend, but close < SMA(200) blocks longs."""
    strat = Rsi2Pullback()
    strat.reset()
    data = _bars([300.0 - 0.5 * i for i in range(240)])
    i, orders = _run_flat(strat, data)
    assert orders == []


def test_exit_fires_when_close_snaps_back_above_exit_ma():
    strat = Rsi2Pullback()
    strat.reset()
    # Down for a while, then one big up bar that closes above the 5-bar SMA.
    closes = [110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 112.0]
    data = _bars(closes)
    pos = PositionState(
        side="long",
        entry_price=100.0,
        stop_price=90.0,
        entry_time=data.index[-2],  # entered on the prior bar
    )
    ctx = StrategyContext(history=data, position=pos)
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "snapback_above_exit_ma"

    # Sanity: with the last bar still below the exit MA, no exit is emitted.
    strat.reset()
    ctx_hold = StrategyContext(history=data.iloc[:-1], position=pos)
    assert strat.on_bar(ctx_hold) == []


def test_time_stop_exits_after_max_hold_bars():
    strat = Rsi2Pullback(max_hold_bars=10)
    strat.reset()
    # Persistent grind lower: close never crosses above the 5-bar SMA, so only the
    # time stop can get us out.
    closes = [200.0 - 2.0 * i for i in range(30)]
    data = _bars(closes)
    entry_i = 15
    pos = PositionState(side="long", entry_price=closes[entry_i], stop_price=100.0, entry_time=data.index[entry_i])

    exited_at = None
    for i in range(entry_i + 1, len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)
        if orders:
            assert orders[0].action == OrderAction.EXIT
            assert orders[0].reason == "time_stop"
            exited_at = i
            break
    assert exited_at == entry_i + 10  # exactly max_hold_bars after entry


def test_short_side_gated_by_enable_shorts():
    # Long downtrend, then a sharp 3-day rally: RSI(2) pins high while close
    # stays below SMA(200).
    trend = [400.0 - 0.5 * i for i in range(220)]
    rally = [trend[-1] + 3.0 * (i + 1) for i in range(3)]
    data = _bars(trend + rally)

    strat_off = Rsi2Pullback(enable_shorts=False)
    strat_off.reset()
    _, orders_off = _run_flat(strat_off, data)
    assert orders_off == []

    strat_on = Rsi2Pullback(enable_shorts=True)
    strat_on.reset()
    i, orders_on = _run_flat(strat_on, data)
    assert i is not None and i >= 220
    order = orders_on[0]
    assert order.action == OrderAction.ENTER_SHORT
    assert order.stop_price is not None
    assert order.stop_price > data["close"].iloc[i]
