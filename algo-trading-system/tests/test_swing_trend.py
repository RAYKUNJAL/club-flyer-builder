from algotrader.backtest.engine import BacktestEngine
from algotrader.backtest.metrics import compute_metrics
from algotrader.risk.position_sizing import PositionSizer, RiskConfig
from algotrader.strategies.swing_trend import SwingTrend


def test_sustained_trend_produces_a_winning_long_trade(daily_trending_bars):
    strat = SwingTrend(entry_period=20, exit_period=10, atr_period=14, atr_stop_mult=3.0)
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=20, max_contracts=50))
    engine = BacktestEngine(daily_trending_bars, strat, sizer, starting_equity=100_000, point_value=20)
    result = engine.run()

    assert len(result.trades) >= 1
    longs = [t for t in result.trades if t.side == "long"]
    assert longs, "a clean sustained uptrend should trigger at least one long breakout trade"
    metrics = compute_metrics(result, starting_equity=100_000)
    assert metrics.total_pnl > 0, "should be net profitable riding a clean multi-month uptrend"
