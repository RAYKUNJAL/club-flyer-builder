"""Automated paper trading on Alpaca-tradable equities: trade the strategy you tapped
"Copy" on, hands-free.

Reads data/active_strategy.json (written by the dashboard's Copy button), builds that
exact strategy from the registry, and runs the hardened live loop against real polled
market bars. Broker selection:

  * If APCA_API_KEY_ID / APCA_API_SECRET_KEY are set -> Alpaca PAPER account (real
    paper orders on Alpaca's book, with broker-side protective stops).
  * Otherwise -> in-memory PaperBroker (no credentials needed, still real market data).

Neither path can touch real money: the Alpaca live endpoint requires a deliberate
two-step (live=True AND ALPACA_ALLOW_LIVE=1) that nothing here performs.

Every closed trade feeds the PaperTracker; the dashboard's validation card compares
live results to the backtest under the pre-committed kill criteria.

Run from the repo root (keep it running; Ctrl-C to stop):
    python scripts/run_paper_trading.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import time as dtime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.live.alpaca_broker import AlpacaBroker, missing_credentials  # noqa: E402
from algotrader.live.paper_broker import PaperBroker  # noqa: E402
from algotrader.live.paper_tracker import PaperTracker  # noqa: E402
from algotrader.live.runner import LiveRunner  # noqa: E402
from algotrader.risk.position_sizing import PositionSizer, RiskConfig  # noqa: E402
from algotrader.strategies.registry import build_strategy  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

#: dashboard symbol label -> tradable ticker (all Alpaca-supported; point value 1.0/share)
SYMBOLS = {
    "Gold ETF (GLD)": "GLD",
    "S&P 500 ETF (SPY)": "SPY",
    "Nasdaq ETF (QQQ)": "QQQ",
    "Tesla (TSLA)": "TSLA",
}

STARTING_EQUITY = 50_000.0  # matches the backtests, so results are directly comparable
RTH = (dtime(9, 30), dtime(16, 0))  # US equities regular session (exchange time)

REQUIRED_COLS = ("open", "high", "low", "close", "volume")


def make_bar_fetcher(ticker: str, interval: str):
    """Poll Yahoo's chart API (plain requests -- survives TLS-inspecting proxies that
    break yfinance) for the most recent COMPLETED bar; validate defensively and dedupe
    by timestamp. Malformed responses (missing columns/timestamps -- observed in the
    wild) return None instead of crashing the loop."""
    from fetch_yahoo_chart import fetch_chart  # sibling script, shared client

    last_seen = {"ts": None}
    log = logging.getLogger(__name__)

    def fetch():
        period = "5d" if interval != "1d" else "1mo"
        try:
            df = fetch_chart(ticker, period, interval)
        except Exception:
            log.exception("bar fetch failed for %s", ticker)
            return None
        if df is None or len(df) < 2:
            return None
        df = df.rename(columns=str.lower)
        if "timestamp" in df.columns:  # fetch_chart returns timestamp as a column
            df = df.set_index(pd.DatetimeIndex(pd.to_datetime(df["timestamp"])))
        if not isinstance(df.index, pd.DatetimeIndex):
            log.warning("bar fetch for %s returned no usable timestamps -- skipping", ticker)
            return None
        if any(c not in df.columns for c in REQUIRED_COLS):
            log.warning("bar fetch for %s missing columns (got %s) -- skipping", ticker, list(df.columns))
            return None
        # The final row is the still-forming bar; the one before it is complete.
        ts = df.index[-2]
        if last_seen["ts"] is not None and ts <= last_seen["ts"]:
            return None
        last_seen["ts"] = ts
        return pd.Timestamp(ts), df.iloc[-2][list(REQUIRED_COLS)]

    return fetch


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the full pipeline (selection, strategy build, broker, one real bar) and exit")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    active_file = DATA / "active_strategy.json"
    if not active_file.exists():
        raise SystemExit(
            "No active strategy selected. Open the dashboard, pick a strategy on the "
            "leaderboard, and tap 'Copy strategy' first (writes data/active_strategy.json)."
        )
    active = json.loads(active_file.read_text())
    if active["symbol"] not in SYMBOLS:
        raise SystemExit(
            f"no live mapping for symbol {active['symbol']!r} -- the tradable universe is "
            f"{sorted(SYMBOLS)} (Alpaca supports equities/ETFs, not futures)"
        )

    ticker = SYMBOLS[active["symbol"]]
    intraday = active["timeframe"] == "5m"
    interval = "5m" if intraday else "1d"
    poll_seconds = 60.0 if intraday else 900.0

    if missing_credentials():
        broker = PaperBroker(starting_equity=STARTING_EQUITY, point_value=1.0)
        broker_desc = "in-memory paper broker (set APCA_API_KEY_ID/APCA_API_SECRET_KEY for Alpaca paper)"
    else:
        broker = AlpacaBroker(live=False)
        broker_desc = "Alpaca PAPER account"

    strategy = build_strategy(active["strategy"], active["params"])
    strategy.reset()
    tracker = PaperTracker(DATA / "paper_trades.json", starting_equity=STARTING_EQUITY)
    sizer = PositionSizer(RiskConfig(
        risk_per_trade_pct=0.02, point_value=1.0, max_contracts=2000, daily_loss_cap_pct=0.03,
    ))
    runner = LiveRunner(
        strategy=strategy, broker=broker, risk_sizer=sizer, symbol=ticker,
        on_trade_closed=tracker.record,
        session=RTH if intraday else None,
        max_stale_polls=60 if intraday else None,  # ~1h of dead 5m feed -> flatten + halt
    )

    print(f"Paper trading {active['label']} on {ticker} ({interval} bars) via {broker_desc}. "
          f"{len(tracker.trades)} trades logged so far.")

    if args.check:
        fetch = make_bar_fetcher(ticker, interval)
        result = fetch()
        if result is None:
            raise SystemExit("CHECK FAILED: could not fetch a completed bar from the data feed")
        ts, bar = result
        runner.reconcile_with_broker()
        runner.on_new_bar(ts, bar)
        print(f"CHECK OK: fetched real {interval} bar {ts} (close {bar['close']:.2f}), "
              f"fed it through the hardened runner, broker equity ${broker.get_equity():,.2f}. "
              "Pipeline is live-ready.")
        return

    runner.run_forever(make_bar_fetcher(ticker, interval), poll_interval_seconds=poll_seconds)


if __name__ == "__main__":
    main()
