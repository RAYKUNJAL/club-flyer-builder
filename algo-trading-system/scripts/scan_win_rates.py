"""Grid-scan every strategy archetype x several parameter variants x real market data,
to find which configs post the highest backtested win rate (with a minimum trade-count
floor so a 2-trade 100% win rate doesn't top the list). Writes results as JSON for the
dashboard mockup to consume, and prints a ranked table.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.backtest.engine import BacktestEngine  # noqa: E402
from algotrader.backtest.metrics import compute_metrics  # noqa: E402
from algotrader.backtest.scoring import composite_score  # noqa: E402
from algotrader.data.loader import load_csv  # noqa: E402
from algotrader.risk.position_sizing import PositionSizer, RiskConfig  # noqa: E402
from algotrader.strategies.fast_trend import FastTrend  # noqa: E402
from algotrader.strategies.mean_reversion import MeanReversion  # noqa: E402
from algotrader.strategies.orb import OpeningRangeBreakout  # noqa: E402
from algotrader.strategies.pulse import Pulse  # noqa: E402
from algotrader.strategies.rsi2_pullback import Rsi2Pullback  # noqa: E402
from algotrader.strategies.squeeze_breakout import SqueezeBreakout  # noqa: E402
from algotrader.strategies.swing_trend import SwingTrend  # noqa: E402
from algotrader.strategies.vwap_reversion import VwapReversion  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MIN_TRADES = 8

DAILY_SOURCES = [
    ("GC_daily.csv", "Gold (GC)", 10.0),
    ("ES_daily.csv", "S&P 500 (ES)", 5.0),
    ("CL_daily.csv", "Crude Oil (CL)", 10.0),
    ("TSLA_daily.csv", "Tesla (TSLA)", 1.0),
]
INTRADAY_SOURCES = [
    ("NQ_5min_rth.csv", "Nasdaq (NQ)", 2.0),
    ("ES_5min_rth.csv", "S&P 500 (ES)", 5.0),
    ("GC_5min_rth.csv", "Gold (GC)", 10.0),
]

SWING_VARIANTS = [
    {"entry_period": 55, "exit_period": 20, "atr_period": 20, "atr_stop_mult": 3.0},
    {"entry_period": 20, "exit_period": 10, "atr_period": 14, "atr_stop_mult": 2.5},
    {"entry_period": 40, "exit_period": 15, "atr_period": 20, "atr_stop_mult": 3.0},
]
MEANREV_VARIANTS = [
    {"band_period": 20, "band_std": 2.0, "stop_std": 3.0},
    {"band_period": 14, "band_std": 1.5, "stop_std": 2.5},
    {"band_period": 10, "band_std": 2.5, "stop_std": 3.5},
]
ORB_VARIANTS = [
    {"range_minutes": 15, "atr_period": 14, "atr_stop_mult": 1.5, "reward_risk": 2.0, "max_risk_points": 40},
    {"range_minutes": 30, "atr_period": 14, "atr_stop_mult": 1.5, "reward_risk": 2.0, "max_risk_points": 50},
    {"range_minutes": 30, "atr_period": 14, "atr_stop_mult": 1.0, "reward_risk": 1.5, "max_risk_points": 30},
]
FASTTREND_VARIANTS = [
    {"drive_minutes": 5, "momentum_threshold_points": 10, "target_points": 15, "stop_points": 8, "max_hold_minutes": 30},
    {"drive_minutes": 10, "momentum_threshold_points": 15, "target_points": 20, "stop_points": 10, "max_hold_minutes": 45},
    {"drive_minutes": 5, "momentum_threshold_points": 20, "target_points": 25, "stop_points": 12, "max_hold_minutes": 20},
]
PULSE_VARIANTS = [
    {"fast_period": 9, "slow_period": 21, "atr_period": 14, "trail_atr_mult": 2.0, "min_spread_atr_mult": 0.15},
    {"fast_period": 5, "slow_period": 13, "atr_period": 10, "trail_atr_mult": 1.5, "min_spread_atr_mult": 0.1},
    {"fast_period": 12, "slow_period": 26, "atr_period": 14, "trail_atr_mult": 2.5, "min_spread_atr_mult": 0.2},
]
RSI2_VARIANTS = [
    # Classic Connors baseline: deep oversold within the 200-day trend, quick snapback exit.
    {"rsi_period": 2, "oversold": 10.0, "trend_period": 200, "exit_ma_period": 5, "max_hold_bars": 10, "stop_atr_mult": 3.0},
    # Looser entry / shorter trend filter -> more signals on shorter daily histories.
    {"rsi_period": 2, "oversold": 25.0, "trend_period": 100, "exit_ma_period": 5, "max_hold_bars": 8, "stop_atr_mult": 3.0},
    # Smoother RSI(4) variant with a slower exit MA and slightly tighter disaster stop.
    {"rsi_period": 4, "oversold": 20.0, "trend_period": 150, "exit_ma_period": 10, "max_hold_bars": 12, "stop_atr_mult": 2.5},
]
SQUEEZE_VARIANTS = [
    # TTM-style defaults: 20/2.0 Bollinger inside 20/1.5 Keltner, 5-bar squeeze floor.
    {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.5, "min_squeeze_bars": 5, "stop_atr_mult": 2.0, "trail_atr_mult": 2.5},
    # Tighter Keltner + shorter squeeze floor -> earlier, more frequent fires.
    {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.2, "min_squeeze_bars": 3, "stop_atr_mult": 1.5, "trail_atr_mult": 2.0},
    # Faster lookbacks with a longer squeeze requirement and wider trail.
    {"bb_period": 14, "bb_std": 1.8, "kc_period": 14, "kc_atr_mult": 1.5, "min_squeeze_bars": 6, "stop_atr_mult": 2.5, "trail_atr_mult": 3.0},
]
VWAP_VARIANTS = [
    # Baseline 2-sigma stretch fade back to session VWAP.
    {"entry_dev": 2.0, "stop_dev": 3.5, "dev_period": 30, "warmup_bars": 30, "max_hold_bars": 60},
    # Deeper stretch required, shorter estimation window, quicker time stop.
    {"entry_dev": 2.5, "stop_dev": 4.0, "dev_period": 24, "warmup_bars": 24, "max_hold_bars": 48},
    # Shallower stretch, longer warmup for a more stable band, tighter hold.
    {"entry_dev": 1.5, "stop_dev": 3.0, "dev_period": 36, "warmup_bars": 36, "max_hold_bars": 36},
]


def run_one(strategy, data, point_value, equity=50_000.0, risk_pct=0.02, max_contracts=50):
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=risk_pct, point_value=point_value, max_contracts=max_contracts))
    engine = BacktestEngine(data, strategy, sizer, starting_equity=equity, point_value=point_value)
    result = engine.run()
    metrics = compute_metrics(result, starting_equity=equity)
    return result, metrics


def main():
    rows = []

    for fname, label, pv in DAILY_SOURCES:
        data = load_csv(DATA_DIR / fname)
        for params in SWING_VARIANTS:
            strat = SwingTrend(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("swing_trend", label, "1d", params, result, m))
        for params in MEANREV_VARIANTS:
            strat = MeanReversion(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("mean_reversion", label, "1d", params, result, m))
        for params in RSI2_VARIANTS:
            strat = Rsi2Pullback(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("rsi2_pullback", label, "1d", params, result, m))
        for params in SQUEEZE_VARIANTS:
            strat = SqueezeBreakout(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("squeeze_breakout", label, "1d", params, result, m))

    for fname, label, pv in INTRADAY_SOURCES:
        data = load_csv(DATA_DIR / fname)
        for params in ORB_VARIANTS:
            strat = OpeningRangeBreakout(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("orb", label, "5m", params, result, m))
        for params in FASTTREND_VARIANTS:
            strat = FastTrend(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("fast_trend", label, "5m", params, result, m))
        for params in PULSE_VARIANTS:
            strat = Pulse(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("pulse", label, "5m", params, result, m))
        for params in VWAP_VARIANTS:
            strat = VwapReversion(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("vwap_reversion", label, "5m", params, result, m))
        for params in SQUEEZE_VARIANTS:
            strat = SqueezeBreakout(**params)
            result, m = run_one(strat, data, pv)
            rows.append(("squeeze_breakout", label, "5m", params, result, m))

    qualified = [r for r in rows if r[5].num_trades >= MIN_TRADES]
    # Rank by risk-adjusted composite score (see algotrader.backtest.scoring), not raw
    # win rate -- a high win rate with a poor profit factor or deep drawdown should not
    # top the leaderboard.
    def score_of(r):
        m = r[5]
        return composite_score(m.win_rate, m.profit_factor, m.sharpe, m.max_drawdown_pct)

    qualified.sort(key=score_of, reverse=True)

    print(f"{'strategy':14s} {'symbol':16s} {'tf':4s} {'score':>6s} {'trades':>7s} {'win%':>7s} {'PF':>6s} {'return%':>8s} {'maxDD%':>7s}")
    for r in qualified[:20]:
        strat_name, label, tf, params, result, m = r
        print(
            f"{strat_name:14s} {label:16s} {tf:4s} {score_of(r):6.3f} {m.num_trades:7d} {m.win_rate*100:6.1f}% "
            f"{m.profit_factor:6.2f} {m.total_return_pct*100:7.1f}% {m.max_drawdown_pct*100:6.1f}%"
        )

    top = qualified[:8]
    payload = []
    for strat_name, label, tf, params, result, m in top:
        payload.append(
            {
                "strategy": strat_name,
                "symbol": label,
                "timeframe": tf,
                "params": params,
                "score": composite_score(m.win_rate, m.profit_factor, m.sharpe, m.max_drawdown_pct),
                "metrics": {
                    "num_trades": m.num_trades,
                    "win_rate": m.win_rate,
                    "profit_factor": m.profit_factor,
                    "total_pnl": m.total_pnl,
                    "total_return_pct": m.total_return_pct,
                    "max_drawdown_pct": m.max_drawdown_pct,
                    "sharpe": m.sharpe,
                    "avg_win": m.avg_win,
                    "avg_loss": m.avg_loss,
                },
                "equity_curve": [
                    {"t": str(t), "equity": float(v)} for t, v in result.equity_curve.items()
                ],
                "trades": [
                    {
                        "side": t.side,
                        "entry_time": str(t.entry_time),
                        "exit_time": str(t.exit_time),
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "contracts": t.contracts,
                        "pnl": t.pnl,
                        "entry_reason": t.entry_reason,
                        "exit_reason": t.exit_reason,
                    }
                    for t in result.trades
                ],
            }
        )

    out_path = Path(__file__).resolve().parents[1] / "data" / "win_rate_scan.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote top {len(payload)} configs to {out_path}")


if __name__ == "__main__":
    main()
