"""CLI: run a backtest for any strategy defined in config/strategies.yaml.

Example:
    python -m algotrader.cli backtest --config config/strategies.yaml --name swing_trend_multi_asset \\
        --symbol GC=F --period 5y --interval 1d --point-value 100
"""
from __future__ import annotations

import argparse

import yaml

from .backtest.engine import BacktestEngine
from .backtest.metrics import compute_metrics
from .data.loader import load_csv, load_yfinance
from .risk.position_sizing import PositionSizer, RiskConfig
from .strategies.registry import build_from_config


def _load_config(path: str, name: str) -> dict:
    with open(path) as f:
        all_configs = yaml.safe_load(f)
    if name not in all_configs:
        raise SystemExit(f"'{name}' not found in {path}; available: {list(all_configs)}")
    return all_configs[name]


def cmd_backtest(args: argparse.Namespace) -> None:
    config = _load_config(args.config, args.name)
    strategy = build_from_config(config)

    if args.csv:
        data = load_csv(args.csv)
    else:
        data = load_yfinance(args.symbol, period=args.period, interval=args.interval)

    risk_config = RiskConfig(
        risk_per_trade_pct=args.risk_pct,
        point_value=args.point_value,
        max_contracts=args.max_contracts,
    )
    sizer = PositionSizer(risk_config)
    engine = BacktestEngine(
        data=data,
        strategy=strategy,
        risk_sizer=sizer,
        starting_equity=args.equity,
        point_value=args.point_value,
    )
    result = engine.run()
    metrics = compute_metrics(result, starting_equity=args.equity)

    print(f"strategy: {args.name} ({config['type']})")
    print(f"symbol:   {args.symbol or args.csv}  bars: {len(data)}  range: {data.index[0]} -> {data.index[-1]}")
    print(metrics)
    if args.show_trades:
        for t in result.trades:
            print(
                f"  {t.entry_time} {t.side:5s} {t.contracts}x @ {t.entry_price:.2f} -> "
                f"{t.exit_time} @ {t.exit_price:.2f}  pnl=${t.pnl:,.2f}  ({t.entry_reason} / {t.exit_reason})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="algotrader: backtest/run trading strategies")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="run a backtest for a configured strategy")
    bt.add_argument("--config", default="config/strategies.yaml")
    bt.add_argument("--name", required=True, help="strategy key from the config file")
    bt.add_argument("--symbol", default=None, help="yfinance ticker, e.g. NQ=F, ES=F, GC=F, TSLA")
    bt.add_argument("--csv", default=None, help="path to a CSV of OHLCV bars instead of yfinance")
    bt.add_argument("--period", default="2y", help="yfinance period, e.g. 1y, 5y, max")
    bt.add_argument("--interval", default="1d", help="yfinance interval, e.g. 1d, 1h, 5m")
    bt.add_argument("--equity", type=float, default=100_000.0)
    bt.add_argument("--point-value", type=float, default=20.0, help="$ per point per contract (NQ=20, MNQ=2, ES=50)")
    bt.add_argument("--risk-pct", type=float, default=0.01, help="fraction of equity risked per trade")
    bt.add_argument("--max-contracts", type=int, default=10)
    bt.add_argument("--show-trades", action="store_true")
    bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
