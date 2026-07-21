"""Automated paper trading: trade the strategy you tapped "Copy" on, hands-free.

Reads data/active_strategy.json (written by the dashboard's Copy button), builds
that exact strategy from the registry, and runs the live loop against real
polled market bars -- on a PAPER broker. No real orders, no credentials needed.
Every closed trade is recorded by the PaperTracker, and the dashboard's
"Paper trading validation" card compares live results against the backtest and
enforces the pre-committed kill criteria.

Run from the repo root (keep it running; Ctrl-C to stop):
    python scripts/run_paper_trading.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.live.paper_broker import PaperBroker  # noqa: E402
from algotrader.live.paper_tracker import PaperTracker  # noqa: E402
from algotrader.live.runner import LiveRunner  # noqa: E402
from algotrader.risk.position_sizing import PositionSizer, RiskConfig  # noqa: E402
from algotrader.strategies.registry import build_strategy  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

#: dashboard symbol label -> (yfinance ticker, futures point value)
SYMBOLS = {
    "Gold (GC)": ("GC=F", 10.0),
    "S&P 500 (ES)": ("ES=F", 5.0),
    "Crude Oil (CL)": ("CL=F", 10.0),
    "Nasdaq (NQ)": ("NQ=F", 2.0),
    "Tesla (TSLA)": ("TSLA", 1.0),
}

STARTING_EQUITY = 50_000.0  # matches the backtests, so results are directly comparable


def make_bar_fetcher(ticker: str, interval: str):
    """Poll Yahoo for the most recent COMPLETED bar; dedupe by timestamp."""
    import yfinance as yf

    last_seen = {"ts": None}

    def fetch():
        period = "2d" if interval != "1d" else "10d"
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or len(df) < 2:
            return None
        df = df.rename(columns=str.lower)
        # The final row is the still-forming bar; the one before it is complete.
        ts = df.index[-2]
        if last_seen["ts"] is not None and ts <= last_seen["ts"]:
            return None
        last_seen["ts"] = ts
        bar = df.iloc[-2][["open", "high", "low", "close", "volume"]]
        return pd.Timestamp(ts), bar

    return fetch


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    active_file = DATA / "active_strategy.json"
    if not active_file.exists():
        raise SystemExit(
            "No active strategy selected. Open the dashboard, pick a strategy on the "
            "leaderboard, and tap 'Copy strategy' first (writes data/active_strategy.json)."
        )
    active = json.loads(active_file.read_text())
    if active["symbol"] not in SYMBOLS:
        raise SystemExit(f"no live data mapping for symbol {active['symbol']!r}")

    ticker, point_value = SYMBOLS[active["symbol"]]
    interval = "5m" if active["timeframe"] == "5m" else "1d"
    poll_seconds = 60.0 if interval == "5m" else 900.0

    strategy = build_strategy(active["strategy"], active["params"])
    strategy.reset()
    tracker = PaperTracker(DATA / "paper_trades.json", starting_equity=STARTING_EQUITY)
    broker = PaperBroker(starting_equity=STARTING_EQUITY, point_value=point_value)
    sizer = PositionSizer(RiskConfig(
        risk_per_trade_pct=0.02, point_value=point_value, max_contracts=50, daily_loss_cap_pct=0.03,
    ))
    runner = LiveRunner(
        strategy=strategy, broker=broker, risk_sizer=sizer,
        symbol=active["symbol"], on_trade_closed=tracker.record,
    )

    print(f"Paper trading {active['label']} on {active['symbol']} ({interval} bars, "
          f"${STARTING_EQUITY:,.0f} paper account). {len(tracker.trades)} trades logged so far.")
    runner.run_forever(make_bar_fetcher(ticker, interval), poll_interval_seconds=poll_seconds)


if __name__ == "__main__":
    main()
