import numpy as np
import pandas as pd

from algotrader.backtest.engine import BacktestEngine
from algotrader.risk.position_sizing import PositionSizer, RiskConfig
from algotrader.strategies.base import Order, OrderAction, Strategy, StrategyContext


class _EntersOnceThenHolds(Strategy):
    """Minimal fake strategy: enters long on the first bar, sets a stop and target, then holds."""

    name = "fake"

    def __init__(self, stop_price, target_price):
        super().__init__()
        self.stop_price = stop_price
        self.target_price = target_price
        self._entered = False

    def reset(self):
        self._entered = False

    def on_bar(self, ctx: StrategyContext):
        if not self._entered and ctx.position.side is None:
            self._entered = True
            return [Order(OrderAction.ENTER_LONG, stop_price=self.stop_price, target_price=self.target_price)]
        return []


def _bars(highs, lows, closes, opens=None):
    idx = pd.date_range("2024-01-02", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "open": opens if opens is not None else closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": 100,
        },
        index=idx,
    )


def test_engine_fills_target_and_books_profit():
    strat = _EntersOnceThenHolds(stop_price=90.0, target_price=110.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=10, max_contracts=100))
    closes = [100.0, 101.0, 105.0, 111.0]  # bar 4's high should clear the 110 target
    highs = [c + 0.5 for c in closes[:-1]] + [112.0]
    lows = [c - 0.5 for c in closes]
    data = _bars(highs, lows, closes)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "target_hit"
    assert trade.exit_price == 110.0
    assert trade.pnl > 0


def test_engine_fills_stop_and_books_loss():
    strat = _EntersOnceThenHolds(stop_price=95.0, target_price=130.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=10, max_contracts=100))
    closes = [100.0, 98.0, 94.0, 92.0]
    opens = [100.0, 99.0, 97.0, 93.0]  # bar 3 opens above the stop, then trades through it
    highs = [max(o, c) + 0.5 for o, c in zip(opens, closes)]
    lows = [93.5, 97.5, 93.5, 91.5]  # bar 3's low clears the 95 stop
    data = _bars(highs, lows, closes, opens)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_hit"
    assert trade.exit_price == 95.0
    assert trade.pnl < 0


def test_engine_gap_through_stop_fills_at_open():
    """A bar that OPENS below a long stop must fill at the open, not the (unreachable) stop."""
    strat = _EntersOnceThenHolds(stop_price=95.0, target_price=130.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=10, max_contracts=100))
    closes = [100.0, 98.0, 90.0, 89.0]
    opens = [100.0, 99.0, 91.0, 90.0]  # bar 3 gaps open at 91, well below the 95 stop
    highs = [max(o, c) + 0.5 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.5 for o, c in zip(opens, closes)]
    data = _bars(highs, lows, closes, opens)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_hit"
    assert trade.exit_price == 91.0  # worse of open vs stop


def test_engine_stop_fill_gets_adverse_slippage():
    strat = _EntersOnceThenHolds(stop_price=95.0, target_price=130.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=10, max_contracts=100))
    closes = [100.0, 98.0, 94.0, 92.0]
    opens = [100.0, 99.0, 97.0, 93.0]
    highs = [max(o, c) + 0.5 for o, c in zip(opens, closes)]
    lows = [93.5, 97.5, 93.5, 91.5]
    data = _bars(highs, lows, closes, opens)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0.5)
    result = engine.run()

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_hit"
    assert trade.exit_price == 94.5  # triggered stop is a market order: 95 - 0.5 slippage


def test_engine_equity_curve_is_marked_to_market():
    """Open-position drawdown must show up in the equity curve, not only at trade close."""
    strat = _EntersOnceThenHolds(stop_price=80.0, target_price=200.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.10, point_value=10, max_contracts=100))
    closes = [100.0, 90.0, 100.0, 100.0]  # dips mid-hold, recovers by the end
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    data = _bars(highs, lows, closes)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    curve = result.equity_curve
    assert curve.min() < 100_000  # the 100 -> 90 excursion is visible intratrade


def test_engine_bars_held_is_incremented():
    seen = []

    class _RecordsBarsHeld(_EntersOnceThenHolds):
        def on_bar(self, ctx):
            if ctx.position.side is not None:
                seen.append(ctx.position.bars_held)
            return super().on_bar(ctx)

    strat = _RecordsBarsHeld(stop_price=80.0, target_price=200.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.10, point_value=10, max_contracts=100))
    closes = [100.0, 100.0, 100.0, 100.0]
    data = _bars([c + 0.5 for c in closes], [c - 0.5 for c in closes], closes)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    engine.run()

    assert seen == [1, 2, 3]  # entry bar is 0; each subsequent bar increments


def test_engine_rejects_stop_widening():
    class _WidensStop(_EntersOnceThenHolds):
        def on_bar(self, ctx):
            if ctx.position.side is not None:
                return [Order(OrderAction.UPDATE_STOP, stop_price=ctx.position.stop_price - 50.0)]
            return super().on_bar(ctx)

    strat = _WidensStop(stop_price=95.0, target_price=200.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=10, max_contracts=100))
    closes = [100.0, 98.0, 94.0, 92.0]
    opens = [100.0, 99.0, 97.0, 93.0]
    highs = [max(o, c) + 0.5 for o, c in zip(opens, closes)]
    lows = [93.5, 97.5, 93.5, 91.5]
    data = _bars(highs, lows, closes, opens)

    engine = BacktestEngine(data, strat, sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    # The widened stop was rejected, so the original 95 stop still fires.
    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "stop_hit"
    assert result.trades[0].exit_price == 95.0


def test_engine_halts_new_entries_after_daily_loss_cap():
    class _ReentersAllDay(Strategy):
        name = "reenters"

        def on_bar(self, ctx):
            if ctx.position.side is None:
                price = ctx.bar["close"]
                return [Order(OrderAction.ENTER_LONG, stop_price=price - 1.0)]
            return []

    # Every bar drifts down 1 point, so each trade stops out for its full 2% risk.
    n = 30
    closes = [100.0 - i for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="5min")  # all one trading day
    data = pd.DataFrame({"open": closes, "high": highs, "low": lows, "close": closes, "volume": 100}, index=idx)

    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=10,
                                     daily_loss_cap_pct=0.03, max_contracts=1000))
    engine = BacktestEngine(data, _ReentersAllDay(), sizer, starting_equity=100_000, point_value=10,
                             commission_per_contract=0, slippage_points=0)
    result = engine.run()

    # Each stop-out loses ~2% of equity; after the cap (3%) trips, no new entries fire,
    # so losses stop near the cap instead of compounding all day.
    assert 0 < len(result.trades) <= 3
    final_equity = result.equity_curve.iloc[-1]
    assert final_equity >= 100_000 * (1 - 0.05)  # cap (3%) + at most one more trade (2%)
