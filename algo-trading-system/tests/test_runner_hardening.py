"""Execution-hardening behaviors: invalid bars are skipped, startup reconciliation
flattens unmanaged positions, and the session gate blocks off-hours entries."""
from datetime import time as dtime

import pandas as pd

from algotrader.live.paper_broker import PaperBroker
from algotrader.live.runner import LiveRunner
from algotrader.risk.position_sizing import PositionSizer, RiskConfig
from algotrader.strategies.base import Order, OrderAction, Strategy


class AlwaysEnter(Strategy):
    name = "always_enter"

    def reset(self):
        pass

    def on_bar(self, ctx):
        if ctx.position.side is None:
            return [Order(action=OrderAction.ENTER_LONG, stop_price=ctx.history["close"].iloc[-1] - 5.0,
                          reason="test")]
        return []


def _runner(**kwargs):
    broker = PaperBroker(starting_equity=50_000.0, point_value=1.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=1.0, max_contracts=2000))
    return LiveRunner(strategy=AlwaysEnter(), broker=broker, risk_sizer=sizer, symbol="SPY", **kwargs), broker


def _bar(o, h, l, c):
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": 100})


def test_invalid_bars_are_skipped():
    runner, broker = _runner()
    ts = pd.Timestamp("2024-01-02 10:00")
    runner.on_new_bar(ts, pd.Series({"open": 100.0, "close": 101.0, "volume": 100}))          # missing high/low
    runner.on_new_bar(ts, _bar(100.0, float("nan"), 99.0, 100.5))                              # NaN
    runner.on_new_bar(ts, _bar(100.0, 99.0, 101.0, 100.0))                                     # inverted high/low
    assert len(runner._history) == 0
    assert broker.order_log == []


def test_startup_reconciliation_flattens_unmanaged_position():
    runner, broker = _runner()
    broker.update_quote("SPY", 500.0)
    broker.place_market_order("SPY", "buy", 25)  # position from a previous crashed process
    assert broker.get_position("SPY").contracts == 25
    runner.reconcile_with_broker()
    assert broker.get_position("SPY").side == "flat"


def test_session_gate_blocks_offhours_entries():
    runner, broker = _runner(session=(dtime(9, 30), dtime(16, 0)))
    runner.on_new_bar(pd.Timestamp("2024-01-02 08:00"), _bar(100, 101, 99, 100))   # pre-market
    assert runner._pos.side is None
    runner.on_new_bar(pd.Timestamp("2024-01-02 10:00"), _bar(100, 101, 99, 100))   # RTH
    assert runner._pos.side == "long"
