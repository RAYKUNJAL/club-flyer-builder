import numpy as np
import pandas as pd

from algotrader.strategies.base import OrderAction, PositionState, StrategyContext
from algotrader.strategies.vwap_reversion import VwapReversion


def _session_bars(closes, start="2024-03-01 09:30", volume=100):
    """1-minute session bars where high/low hug the close so VWAP ~ mean of closes."""
    idx = pd.date_range(start, periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.02,
            "low": closes - 0.02,
            "close": closes,
            "volume": volume,
        },
        index=idx,
    )


def _calm(n, level=100.0, amplitude=0.1, period=15):
    """Deterministic gentle sinusoid: nonzero stretch-std, but max |dev|/std = sqrt(2) < entry_dev,
    so a calm regime can never trigger an entry by construction (unlike iid noise, which
    produces 2-sigma deviation events by definition)."""
    return level + amplitude * np.sin(2 * np.pi * np.arange(n) / period)


def _run_until_entry(strat, data, pos=None):
    pos = pos or PositionState()
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=pos)
        orders = strat.on_bar(ctx)
        if orders and orders[0].action in (OrderAction.ENTER_LONG, OrderAction.ENTER_SHORT):
            return i, orders[0]
    return None, None


def test_enters_long_on_downside_stretch_below_vwap():
    """A sharp drop far below the session VWAP triggers a long fade with target at VWAP."""
    strat = VwapReversion()
    strat.reset()
    calm = list(_calm(45))
    plunge = [97.0, 96.8, 96.9]  # ~3 points below a ~100 VWAP, >> 2 stretch-stds
    data = _session_bars(calm + plunge)

    i, order = _run_until_entry(strat, data)
    assert order is not None, "expected a long entry on the downside stretch"
    assert order.action == OrderAction.ENTER_LONG
    assert i >= 45  # only after the plunge, never during the calm regime
    entry_close = data["close"].iloc[i]
    # Target is the VWAP itself: above the stretched entry price, near the session mean.
    assert order.target_price > entry_close
    assert abs(order.target_price - 100.0) < 1.0


def test_enters_short_on_upside_stretch_above_vwap():
    strat = VwapReversion()
    strat.reset()
    calm = list(_calm(45))
    spike = [103.0, 103.2]
    data = _session_bars(calm + spike)

    i, order = _run_until_entry(strat, data)
    assert order is not None
    assert order.action == OrderAction.ENTER_SHORT
    assert order.target_price < data["close"].iloc[i]


def test_no_entry_during_warmup_even_if_stretched():
    """Before warmup_bars session bars, the strategy must stay flat regardless of stretch."""
    strat = VwapReversion(warmup_bars=30)
    strat.reset()
    data = _session_bars(list(_calm(20)) + [95.0])  # huge stretch at bar 21

    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        assert strat.on_bar(ctx) == []


def test_entry_orders_carry_protective_stop_on_correct_side():
    strat = VwapReversion()
    strat.reset()
    calm = list(_calm(45))
    data = _session_bars(calm + [97.0])

    i, order = _run_until_entry(strat, data)
    assert order is not None and order.action == OrderAction.ENTER_LONG
    entry_close = data["close"].iloc[i]
    assert order.stop_price is not None
    assert order.stop_price < entry_close  # long stop sits below the entry
    # stop_dev (3.5) is wider than entry_dev (2.0): stop is further from VWAP than entry.
    assert order.stop_price < order.target_price


def test_exits_on_stop_when_stretch_extends():
    """Holding a long, a close at/below the recorded stop_price fires an EXIT."""
    strat = VwapReversion()
    strat.reset()
    calm = list(_calm(45))
    data = _session_bars(calm + [97.0, 96.0])  # keeps falling after entry

    pos = PositionState(side="long", entry_price=97.0, stop_price=96.5, bars_held=1)
    ctx = StrategyContext(history=data, position=pos)
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "stop_hit"


def test_exits_on_target_when_close_reverts_to_vwap():
    strat = VwapReversion()
    strat.reset()
    calm = list(_calm(45))
    data = _session_bars(calm + [97.0, 100.5])  # snaps back above the ~100 VWAP

    pos = PositionState(side="long", entry_price=97.0, stop_price=94.0, bars_held=1)
    ctx = StrategyContext(history=data, position=pos)
    orders = strat.on_bar(ctx)
    assert len(orders) == 1
    assert orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "vwap_target_touch"


def test_max_hold_time_stop():
    strat = VwapReversion(max_hold_bars=60)
    strat.reset()
    calm = list(_calm(45))
    data = _session_bars(calm + [97.0] * 10)  # stuck below VWAP, no stop, no target

    pos = PositionState(side="long", entry_price=97.0, stop_price=90.0, bars_held=60)
    ctx = StrategyContext(history=data, position=pos)
    orders = strat.on_bar(ctx)
    assert orders and orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "max_hold_time_stop"


def test_mandatory_flat_at_session_eod():
    """At/after session_eod_flat the strategy force-exits any open position."""
    strat = VwapReversion()
    strat.reset()
    # Session running 09:30 -> past 15:55; price pinned below VWAP so no other exit fires.
    n_to_eod = int((pd.Timestamp("2024-03-01 15:55") - pd.Timestamp("2024-03-01 09:30")).total_seconds() // 60) + 1
    closes = list(_calm(45)) + [97.0] * (n_to_eod - 45)
    data = _session_bars(closes)
    assert data.index[-1].time() >= pd.Timestamp("2024-03-01 15:55").time()

    pos = PositionState(side="long", entry_price=97.0, stop_price=90.0, bars_held=5)
    ctx = StrategyContext(history=data, position=pos)
    orders = strat.on_bar(ctx)
    assert orders and orders[0].action == OrderAction.EXIT
    assert orders[0].reason == "session_eod_flat"


def test_no_new_entries_after_cutoff_time():
    """A qualifying stretch after no_new_entries_after (14:30) is ignored."""
    strat = VwapReversion()
    strat.reset()
    # Start the session late in the day so bar 46 lands after 14:30 exchange time.
    calm = list(_calm(45))
    data = _session_bars(calm + [97.0, 96.9], start="2024-03-01 13:50")
    # Bars land inside the same day but after the cutoff by the time the stretch appears.
    assert data.index[45].time() > pd.Timestamp("2024-03-01 14:30").time()

    # VWAP anchor uses session_open=09:30; every bar here is >= 09:30 so all count.
    for i in range(len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        orders = strat.on_bar(ctx)
        assert not any(
            o.action in (OrderAction.ENTER_LONG, OrderAction.ENTER_SHORT) for o in orders
        )


def test_vwap_anchor_resets_on_new_day():
    """Day 2's VWAP ignores day 1: a price level far from day 1's mean but at day 2's mean is not a stretch."""
    strat = VwapReversion()
    strat.reset()
    day1 = _session_bars(list(_calm(60, level=100.0)), start="2024-03-01 09:30")
    # Day 2 trades calmly around 120 -- 20 points from day 1's VWAP but AT day 2's VWAP.
    day2 = _session_bars(list(_calm(60, level=120.0)), start="2024-03-04 09:30")
    data = pd.concat([day1, day2])

    for i in range(len(day1), len(data)):
        ctx = StrategyContext(history=data.iloc[: i + 1], position=PositionState())
        assert strat.on_bar(ctx) == [], "no entry expected: day 2 price sits on day 2's own VWAP"
