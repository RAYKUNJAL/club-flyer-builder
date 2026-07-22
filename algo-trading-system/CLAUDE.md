# algotrader — project guide

Event-driven algorithmic trading system: 8 strategy archetypes, a bar-by-bar backtest
engine, a FastAPI dashboard, automated paper trading with validation, and a
(dry-run-by-default) Tradovate broker integration.

## Commands

```bash
pip install -e . && pip install pytest fastapi uvicorn httpx pandas numpy yfinance

python -m pytest tests/ -q                 # full test suite — keep it green
python scripts/fetch_yahoo_chart.py "GC=F" --range 10y --interval 1d --out data/GC_daily.csv
python scripts/scan_win_rates.py           # grid scan -> data/win_rate_scan.json
python scripts/fetch_top_traders.py        # SEC 13F snapshot -> data/top_traders.json
uvicorn algotrader.webapp.main:app --port 8000   # dashboard at http://localhost:8000
python scripts/run_paper_trading.py        # auto-trades the dashboard-copied strategy (paper)
```

## Architecture

- `src/algotrader/strategies/` — Strategy subclasses; `on_bar(ctx)` returns Orders.
  `registry.py` maps name -> class (used by config and the paper-trading runner).
- `src/algotrader/backtest/engine.py` — bar-by-bar engine. Stops/targets enforced at the
  ENGINE level against each bar's high/low (gap-aware: fills at the worse of open vs stop).
  `metrics.py` computes stats; `scoring.py` is the composite leaderboard score
  (35% PF / 25% win rate / 20% Sharpe / 20% drawdown).
- `src/algotrader/risk/position_sizing.py` — %-equity risk sizing by stop distance,
  daily loss cap.
- `src/algotrader/live/` — `runner.py` (hardened live loop: broker-side protective stops,
  ratchet-only stop updates, bar validation, startup reconciliation, stale-feed halt,
  session gate, reports closed trades via `on_trade_closed`), `alpaca_broker.py` (paper
  by default, unique client order ids), `paper_broker.py`, `paper_tracker.py` (validation
  + kill criteria), `tradovate_broker.py` (legacy futures reference, unused).
- `src/algotrader/webapp/` — FastAPI backend + static frontend. Reads
  `data/win_rate_scan.json`, `data/top_traders.json`, `data/active_strategy.json`,
  `data/paper_trades.json`. `volume_profile.py` = footprint-chart approximation from OHLCV.
- `scripts/` — data fetchers, the scanner, the paper-trading loop.
- `data/` — real Yahoo OHLCV CSVs + generated JSON results (committed);
  `active_strategy.json`/`paper_trades.json` are runtime state (gitignored).

## Invariants — do not break these

1. **No lookahead bias.** Strategies may only read `ctx.history` up to the current bar.
   The engine and tests enforce this; any new strategy needs a test proving its entries.
2. **Safety defaults are load-bearing.** The broker is Alpaca PAPER; the live endpoint
   requires the deliberate two-step (AlpacaBroker(live=True) + ALPACA_ALLOW_LIVE=1) that
   no committed code performs. Never change these defaults, never log or echo credentials,
   never commit real credential values, and see GATES.md before touching anything live.
3. **Stops are engine/runner-level, not strategy trust.** Entries carry `stop_price`;
   stop updates may only tighten risk (the runner rejects widening). Keep it that way.
4. **Honest reporting.** Backtest results are labeled as backtests; approximations (e.g.
   the volume-profile chart) say so in the UI; broker failures surface the real cause.
   Paper-validation kill criteria live in `paper_tracker.py` and are pre-committed —
   don't loosen them to make results look better.
5. **$50,000 starting equity everywhere** (backtests, paper trading) so results stay
   directly comparable.

## Testing conventions

Tests use synthetic bar fixtures (see `tests/conftest.py`) that construct the market
condition a strategy should react to. Every strategy has at least: an entry test in its
intended condition and a risk-logic test (stop present / exits fire). Webapp tests use
FastAPI's TestClient with tmp_path-monkeypatched data files — never the repo's real data.
