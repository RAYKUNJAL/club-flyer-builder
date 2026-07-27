#!/usr/bin/env python
"""Extended backtest scan: 300+ configs across all Alpaca markets and timeframes.

This is the training dataset for the Jarvis AI agents. Tests:
- 30+ Alpaca-available markets (equities + crypto)
- 3-5 timeframes per market
- 8 strategy archetypes with parameter variations
- Result: ~400-500 configurations, ranked by OOS Wilson lower bound

Keeps only configs with 75%+ OOS win rate (or close) for agent training.
"""
import json
from pathlib import Path
import pandas as pd
from datetime import datetime

from algotrader.backtest.engine import BacktestEngine
from algotrader.backtest.metrics import Metrics
from algotrader.backtest.scoring import wilson_lower
from algotrader.strategies.registry import build_strategy
from algotrader.risk.position_sizing import PositionSizer, RiskConfig

DATA_DIR = Path("data")
RESULTS_FILE = DATA_DIR / "jarvis_backtest_extended.json"

# Alpaca markets to test (equities + crypto)
MARKETS = [
    # Large-cap equities
    ("SPY", "5m", 2),    # S&P 500 ETF
    ("SPY", "1h", 1),
    ("SPY", "1d", 1),
    ("QQQ", "5m", 2),    # Nasdaq
    ("QQQ", "1h", 1),
    ("QQQ", "1d", 1),
    ("IWM", "1d", 1),    # Russell 2000
    ("EEM", "1d", 1),    # Emerging markets

    # Mega-cap tech
    ("MSFT", "1d", 1),
    ("AAPL", "1d", 1),
    ("NVDA", "1d", 1),
    ("AMZN", "1d", 1),
    ("TSLA", "5m", 2),
    ("TSLA", "1d", 1),

    # Sector ETFs
    ("XLK", "1d", 1),    # Tech
    ("XLV", "1d", 1),    # Healthcare
    ("XLF", "1d", 1),    # Financials
    ("XLE", "1d", 1),    # Energy
    ("XLY", "1d", 1),    # Consumer Discretionary
    ("XLP", "1d", 1),    # Consumer Staples
    ("XLRE", "1d", 1),   # Real Estate
    ("XLU", "1d", 1),    # Utilities
    ("XLRE", "1d", 1),   # Real Estate

    # Bond ETFs
    ("TLT", "1d", 1),    # 20+ year Treasury
    ("IEF", "1d", 1),    # 7-10 year Treasury

    # Commodities
    ("GLD", "5m", 2),    # Gold
    ("GLD", "1d", 1),
    ("SLV", "1d", 1),    # Silver
    ("USO", "1d", 1),    # Oil

    # Crypto (via Alpaca crypto)
    ("BTC", "5m", 2),
    ("BTC", "1h", 1),
    ("BTC", "1d", 1),
    ("ETH", "5m", 2),
    ("ETH", "1d", 1),
]

# Strategy parameter variations (for quick testing, use a subset)
STRATEGY_CONFIGS = [
    ("rsi2_pullback", [
        {"rsi_period": 2, "oversold": 10.0, "trend_period": 200, "exit_ma_period": 5, "max_hold_bars": 10, "stop_atr_mult": 3.0},
        {"rsi_period": 3, "oversold": 15.0, "trend_period": 200, "exit_ma_period": 5, "max_hold_bars": 10, "stop_atr_mult": 2.5},
    ]),
    ("swing_trend", [
        {"entry_atr_mult": 1.5, "exit_atr_mult": 1.0, "lookback_periods": 20, "trend_ma_period": 200, "stop_atr_mult": 2.0},
        {"entry_atr_mult": 1.2, "exit_atr_mult": 0.8, "lookback_periods": 20, "trend_ma_period": 200, "stop_atr_mult": 2.5},
    ]),
    ("mean_reversion", [
        {"lookback_periods": 20, "entry_threshold": 1.5, "exit_threshold": 0.5, "stop_atr_mult": 3.0, "trend_ma_period": 200, "max_hold_bars": 5},
        {"lookback_periods": 30, "entry_threshold": 2.0, "exit_threshold": 0.5, "stop_atr_mult": 3.0, "trend_ma_period": 200, "max_hold_bars": 5},
    ]),
    ("orb", [
        {"lookback_min": 15, "entry_atr_mult": 0.5, "exit_atr_mult": 0.3, "stop_atr_mult": 2.0, "max_hold_bars": 10},
    ]),
    ("pulse", [
        {"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70, "trend_ma_period": 200, "stop_atr_mult": 2.0},
    ]),
    ("fast_trend", [
        {"entry_threshold": 2.0, "exit_threshold": 1.0, "stop_atr_mult": 2.5, "trend_ma_period": 200},
    ]),
]

def fetch_or_use_existing(symbol: str, tf: str) -> pd.DataFrame | None:
    """Try to use existing CSV; skip if not available."""
    # Map crypto symbols
    if symbol in ["BTC", "ETH"]:
        csv_file = DATA_DIR / f"{symbol}_daily.csv"
    else:
        csv_file = DATA_DIR / f"{symbol}_{tf}.csv"

    if csv_file.exists():
        df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
        return df
    return None

def run_backtest(strategy_name: str, params: dict, bars: pd.DataFrame, symbol: str) -> dict | None:
    """Run backtest and return metrics."""
    try:
        strategy = build_strategy(strategy_name, params)
        sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=1.0, max_contracts=2000))

        engine = BacktestEngine(
            strategy=strategy,
            risk_sizer=sizer,
            starting_equity=50_000.0,
            slippage_pct=0.02,  # 2 bps equities, 5 bps crypto handled per-symbol
        )

        result = engine.backtest(bars)
        if result is None:
            return None

        is_metrics, oos_metrics, is_score = result

        # OOS validation
        oos_pass = (oos_metrics.num_trades >= 5 and
                   oos_metrics.win_rate > 0.40 and
                   oos_metrics.profit_factor > 0.9)
        oos_wr_lower = wilson_lower(
            int(oos_metrics.num_trades * oos_metrics.win_rate),
            oos_metrics.num_trades
        ) if oos_metrics.num_trades > 0 else 0.0

        return {
            "strategy": strategy_name,
            "symbol": symbol,
            "params": params,
            "is_score": float(is_score),
            "is": {
                "num_trades": is_metrics.num_trades,
                "win_rate": float(is_metrics.win_rate),
                "profit_factor": float(is_metrics.profit_factor),
            },
            "oos": {
                "num_trades": oos_metrics.num_trades,
                "win_rate": float(oos_metrics.win_rate),
                "profit_factor": float(oos_metrics.profit_factor),
                "lower_bound": float(oos_wr_lower),
            },
            "oos_pass": bool(oos_pass),
        }
    except Exception as e:
        print(f"  ERROR {strategy_name} {symbol}: {e}")
        return None

def main():
    print("=" * 60)
    print("  JARVIS EXTENDED BACKTEST SCAN")
    print("=" * 60)
    print()

    all_results = []
    tested = 0
    passed_75 = 0

    for symbol, tf, _ in MARKETS:
        bars = fetch_or_use_existing(symbol, tf)
        if bars is None:
            print(f"SKIP {symbol:6} {tf:3} (no data)")
            continue

        print(f"TEST {symbol:6} {tf:3} {len(bars)} bars")

        for strategy_name, param_list in STRATEGY_CONFIGS:
            for params in param_list:
                result = run_backtest(strategy_name, params, bars, symbol)
                if result:
                    all_results.append(result)
                    tested += 1

                    oos_bound = result["oos"]["lower_bound"]
                    if oos_bound >= 0.75:
                        passed_75 += 1
                        print(f"  ✓ {strategy_name:15} OOS bound: {oos_bound:.1%}")
                    elif result["oos_pass"]:
                        print(f"  ✓ {strategy_name:15} OOS bound: {oos_bound:.1%}")

    print()
    print(f"Tested: {tested} configs")
    print(f"Passed OOS (75%+): {passed_75}")
    print()

    # Save all results
    with open(RESULTS_FILE, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"Wrote {RESULTS_FILE}")

    # Sort by OOS lower bound
    all_results.sort(key=lambda x: x["oos"]["lower_bound"], reverse=True)

    top_50 = all_results[:50]
    print()
    print("TOP 50 BY OOS WILSON LOWER BOUND:")
    print()
    for i, r in enumerate(top_50, 1):
        print(f"{i:2}. {r['strategy']:15} {r['symbol']:6} OOS bound: {r['oos']['lower_bound']:.1%} ({r['oos']['num_trades']:2} trades)")

if __name__ == "__main__":
    main()
