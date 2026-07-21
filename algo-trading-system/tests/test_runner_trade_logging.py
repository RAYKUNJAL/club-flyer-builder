"""The live runner must report every closed trade to its callback with correct P&L --
this is what feeds the paper-trading validation tracker."""
import pandas as pd

from algotrader.live.paper_broker import PaperBroker
from algotrader.live.runner import LiveRunner
from algotrader.risk.position_sizing import PositionSizer, RiskConfig
from algotrader.strategies.base import Order, OrderAction, Strategy


class EnterThenExit(Strategy):
    """Enters long on the first bar, exits on the third."""
    name = "enter_then_exit"

    def __init__(self):
        self.bars_seen = 0

    def reset(self):
        self.bars_seen = 0

    def on_bar(self, ctx):
        self.bars_seen += 1
        if self.bars_seen == 1:
            return [Order(action=OrderAction.ENTER_LONG, stop_price=95.0, reason="test_entry")]
        if self.bars_seen == 3 and ctx.position.side is not None:
            return [Order(action=OrderAction.EXIT, reason="test_exit")]
        return []


def _bar(o, h, l, c):
    return pd.Series({"open": o, "high": h, "low": l, "close": c, "volume": 100})


def test_closed_trade_reported_with_correct_pnl():
    closed = []
    broker = PaperBroker(starting_equity=50_000.0, point_value=10.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=10.0, max_contracts=50))
    runner = LiveRunner(
        strategy=EnterThenExit(), broker=broker, risk_sizer=sizer,
        symbol="TEST", on_trade_closed=closed.append,
    )

    ts = pd.Timestamp("2024-01-02 09:30")
    runner.on_new_bar(ts, _bar(100, 101, 99, 100))                      # enter long @100
    runner.on_new_bar(ts + pd.Timedelta(minutes=5), _bar(101, 103, 100, 102))
    runner.on_new_bar(ts + pd.Timedelta(minutes=10), _bar(102, 105, 101, 104))  # exit @104

    assert len(closed) == 1
    t = closed[0]
    assert t["side"] == "long"
    assert t["exit_reason"] == "test_exit"
    assert t["entry_price"] == 100.0
    assert t["exit_price"] == 104.0
    # pnl = (104-100) * contracts * $10/pt; sizing: 2% of 50k = $1000 risk, stop 5pts*$10=$50/contract -> 20 contracts
    assert t["contracts"] == 20
    assert t["pnl"] == (104.0 - 100.0) * 20 * 10.0


def test_stop_hit_reports_trade_with_stop_price():
    closed = []
    broker = PaperBroker(starting_equity=50_000.0, point_value=10.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=10.0, max_contracts=50))
    runner = LiveRunner(
        strategy=EnterThenExit(), broker=broker, risk_sizer=sizer,
        symbol="TEST", on_trade_closed=closed.append,
    )
    ts = pd.Timestamp("2024-01-02 09:30")
    runner.on_new_bar(ts, _bar(100, 101, 99, 100))                      # enter long @100, stop 95
    runner.on_new_bar(ts + pd.Timedelta(minutes=5), _bar(99, 99.5, 94, 94.5))  # low breaches stop

    assert len(closed) == 1
    t = closed[0]
    assert t["exit_reason"] == "stop_hit"
    assert t["exit_price"] == 95.0  # no gap: open (99) above stop, fills at stop price
    assert t["pnl"] == (95.0 - 100.0) * 20 * 10.0
