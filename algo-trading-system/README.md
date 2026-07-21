# algotrader

A standalone, broker-agnostic backtester and live-execution engine for rule-based futures/trend
trading systems, in Python. Eight strategy archetypes are implemented, each covering one of the
canonical system types vendors like NinjaTrader-based "automated futures trading" products
(trend following, breakout, reversal/mean-reversion, fast-trend momentum) advertise:

| Config key | File | Archetype | Behavior |
|---|---|---|---|
| `orb_nq` | `strategies/orb.py` | Opening range breakout | Builds an N-minute opening range, trades the breakout, ATR stop, fixed R:R target |
| `fast_trend_nq` | `strategies/fast_trend.py` | Opening momentum | One trade at the open if the opening drive clears a point threshold; fixed target, tight time-boxed exit |
| `pulse_nq` | `strategies/pulse.py` | All-session trend | EMA-crossover trend filter held with an ATR trailing stop; re-enters on fresh crossovers all session |
| `mean_reversion_nq` | `strategies/mean_reversion.py` | Mean reversion | Bollinger Band fade, exits at the mean or a wider stop |
| `swing_trend_multi_asset` | `strategies/swing_trend.py` | Long-term trend | Donchian-channel breakout on daily bars, ATR trailing stop, multi-day/week holds, any trending asset |
| — | `strategies/rsi2_pullback.py` | Trend-filtered pullback | Connors RSI(2): buys deep short-term oversold dips above the 200-day SMA on daily bars, exits on the snapback to a short MA or a time stop |
| — | `strategies/squeeze_breakout.py` | Volatility compression | Bollinger-inside-Keltner "squeeze": waits out the compression, enters on the expansion in the direction of momentum, ATR trailing stop; daily or intraday |
| — | `strategies/vwap_reversion.py` | Intraday VWAP fade | Fades stretches beyond N stretch-sigmas from the session-anchored VWAP back to VWAP; time stop and mandatory end-of-day flat |

## Important: this does not reproduce anyone's proprietary system

These implement the *well-documented technical-analysis patterns* that "automated futures
trading system" vendors publicly describe (opening range breakout, EMA/ADX trend following,
Donchian trend-following, Bollinger mean reversion). The actual tuned parameters behind any
specific commercial product are not public — they live behind a paid Discord/course. Treat the
default parameters here as a reasonable starting point to backtest and tune against your own
data, not as a cloned black box.

**No strategy here is guaranteed to be profitable.** Futures trading involves substantial risk
of loss. Backtest results (especially on the free daily bars yfinance provides) do not account
for realistic slippage, fill quality, or regime change, and past performance never guarantees
future results. Only trade capital you can afford to lose, and paper-trade any of this
extensively before risking real money.

## Install

```bash
cd algo-trading-system
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Backtest

```bash
# Intraday archetypes need intraday bars -- yfinance only keeps ~60 days of 1m/5m history.
python -m algotrader.cli backtest --name orb_nq --symbol NQ=F --interval 5m --period 60d --point-value 2 --show-trades

# Daily swing/trend-following can run on years of history and across any trending asset.
python -m algotrader.cli backtest --name swing_trend_multi_asset --symbol GC=F --interval 1d --period 10y --point-value 10
python -m algotrader.cli backtest --name swing_trend_multi_asset --symbol TSLA --interval 1d --period 5y --point-value 1

# Bring your own real futures minute/tick data (e.g. exported from NinjaTrader) instead of yfinance:
python -m algotrader.cli backtest --name pulse_nq --csv data/NQ_5min.csv --point-value 2
```

If yfinance fails with a connection reset (some proxies/networks block its browser-TLS-impersonation
library even though plain HTTPS works fine), use the bundled fallback fetcher instead:

```bash
python scripts/fetch_yahoo_chart.py NQ=F --range 60d --interval 5m --rth-only --out data/NQ_5min.csv
python scripts/fetch_yahoo_chart.py GC=F --range 10y --interval 1d --out data/GC_daily.csv
python -m algotrader.cli backtest --name orb_nq --csv data/NQ_5min.csv --point-value 2 --show-trades
```

`--point-value` is the dollar value of one point per contract: NQ e-mini = 20, **MNQ micro = 2**,
ES e-mini = 50, **MES micro = 5**, GC full = 100, **MGC micro = 10**, single stocks = 1 (per share).

**Sizing gotcha to know before you conclude "no trades fired":** the risk sizer (`risk_per_trade_pct`
of equity / stop-distance-in-points) will legitimately return 0 contracts — and silently skip every
signal — if a full-size contract's point value makes one stop-out cost more than your risk budget
(e.g. 1% of $50k = $500 risk, but a 50-point NQ stop at $20/pt = $1,000 risk -- too big for 1 full
contract). If a backtest shows zero trades, check this before assuming the strategy logic is broken:
either use the micro contract's point value, raise `--risk-pct`, or raise `--equity`.

## Strategy config (the "no-code" layer)

Edit `config/strategies.yaml` to change parameters or add new named variants of any archetype
— no Python required, same idea as the vendor's "no-code rule builder" pitch:

```yaml
my_tighter_orb:
  type: orb
  params:
    range_minutes: 15
    atr_stop_mult: 1.0
    reward_risk: 3.0
```

## Live trading

`src/algotrader/live/` provides:
- `broker_base.py` — the `Broker` interface (`get_equity`, `get_position`, `place_market_order`, `flatten`)
- `paper_broker.py` — in-memory paper broker, no real orders, for dry-running the loop
- `tradovate_broker.py` — real Tradovate REST API client (the broker vendors like this one pair
  with NinjaTrader). **Defaults to the demo environment and `dry_run=True`** — it will not place
  a real order until you explicitly pass `dry_run=False` after testing against demo. Credentials
  are read from environment variables (`TRADOVATE_USERNAME`, `TRADOVATE_PASSWORD`,
  `TRADOVATE_APP_ID`, `TRADOVATE_APP_VERSION`, `TRADOVATE_CID`, `TRADOVATE_SECRET`,
  `TRADOVATE_ACCOUNT_ID`), never hardcoded.
- `runner.py` — `LiveRunner` drives a `Strategy` against a live bar feed exactly like the
  backtest engine does (same stop/target enforcement), routing orders to whichever `Broker` you
  give it. You supply a `fetch_latest_bar()` callable — this repo intentionally doesn't hardcode
  one data feed, since that depends on what market data access you actually have.

```python
from algotrader.strategies.registry import build_strategy
from algotrader.risk.position_sizing import PositionSizer, RiskConfig
from algotrader.live.paper_broker import PaperBroker
from algotrader.live.runner import LiveRunner

strategy = build_strategy("orb", {"range_minutes": 30})
broker = PaperBroker(starting_equity=50_000, point_value=20)
sizer = PositionSizer(RiskConfig(point_value=20))
runner = LiveRunner(strategy, broker, sizer, symbol="NQ")

# runner.run_forever(fetch_latest_bar=your_data_feed_fn, poll_interval_seconds=60)
```

## Dashboard (real web app, not a static mockup)

`src/algotrader/webapp/` is a real FastAPI backend + frontend, meant to run locally (or on your
own server) since it makes real outbound network calls (to Tradovate) that a sandboxed static
page (e.g. a hosted Claude Artifact) is not allowed to make.

```bash
# 1. Generate backtest data if you haven't already:
python scripts/fetch_yahoo_chart.py GC=F --range 10y --interval 1d --out data/GC_daily.csv
python scripts/scan_win_rates.py   # writes data/win_rate_scan.json

# 2. Run the app:
uvicorn algotrader.webapp.main:app --reload --port 8000
# open http://localhost:8000
```

It serves:
- `GET /api/strategies`, `/api/strategies/{id}/equity_curve`, `/api/strategies/{id}/trades` — real
  backtest results, read from `data/win_rate_scan.json`. Each strategy carries a composite
  risk-adjusted `score` (35% profit factor, 25% win rate, 20% Sharpe, 20% drawdown — see
  `src/algotrader/backtest/scoring.py`); the scanner and the dashboard leaderboard both rank by it.
- `GET /api/broker/status`, `POST /api/broker/connect`, `POST /api/broker/disconnect`,
  `GET /api/broker/account` — a genuine (dry-run-by-default) `TradovateBroker` connection. Without
  credentials set, "Connect account" honestly reports it can't authenticate and tells you which
  environment variable is missing — see below to get real ones.
- `POST /api/live/select`, `GET /api/live/active`, `POST /api/live/deselect` — dub-style
  "copy this strategy": one tap marks a leaderboard config as the active one for the live runner
  (written to `data/active_strategy.json`). Selecting never starts trading by itself — the runner
  is started separately and defaults to dry-run/demo.

### Order-flow footprint chart

`GET /api/footprint/{ES|NQ|GC}` serves footprint (cluster) candles for the dashboard's order-flow
panel: per-price-level buy/sell volume clusters, per-candle delta, cumulative delta, and point of
control, built by `src/algotrader/analytics/footprint.py` from real 1-minute bars:

```bash
python scripts/fetch_yahoo_chart.py "ES=F" --range 5d --interval 1m --out data/ES_1min.csv
```

Honesty note: a *true* footprint chart needs tick data with bid/ask aggressor tags, which is
licensed for CME futures (Databento, IQFeed, or Tradovate's market-data feed on a connected
account). This panel is the best public-data approximation — tick-rule classification
(~75–85% accurate per Lee & Ready-line research) with volume spread uniformly across each
1-minute bar's range — and says so in the UI. The JSON shape matches what a real tick feed
would produce, so wiring Tradovate market data in later only swaps the builder.

### Automated paper trading (the AI trades the copied strategy)

The full hands-free loop: tap **Copy strategy** on the dashboard, then run

```bash
python scripts/run_paper_trading.py
```

It builds that exact strategy from the registry, polls real market bars, and trades a
$50,000 **paper** account (same size as the backtests, so results compare directly). No
credentials needed and no real orders — ever — from this script. Every closed trade is
logged to `data/paper_trades.json`, and the dashboard's **Paper trading validation** card
compares live results against the backtest with kill criteria committed in code
(`src/algotrader/live/paper_tracker.py`): stop if live drawdown exceeds the backtest's max,
or if expectancy falls below half the backtest's after 30 trades. Below 30 trades the
verdict is "insufficient data" on purpose — small samples read like coin flips.

### Order-flow / footprint chart (honest approximation)

`GET /api/strategies/{id}/volume_profile` powers the dashboard's volume-cluster chart:
volume traded at each price level over the recent window, split into buy pressure
(close ≥ open) and sell pressure, with the point of control highlighted. This is the
standard OHLCV approximation — a true bid×ask footprint requires tick data, which plugs
into `src/algotrader/webapp/volume_profile.py` once Tradovate market data is connected
(the output schema is already shaped for it).

### Top Traders leaderboard (real SEC 13F data)

The dashboard also shows the latest disclosed portfolios of well-known fund managers (Buffett,
Burry, Ackman, Druckenmiller, Dalio, Tepper, Klarman, Loeb, Einhorn, plus Renaissance), pulled
straight from **SEC EDGAR Form 13F filings** — official, free, public data, no API key:

```bash
python scripts/fetch_top_traders.py   # writes data/top_traders.json
```

Know the limits before reading it as a signal: 13Fs cover long US equity positions only (no
shorts, futures, cash, or international), and are filed up to 45 days after quarter end — always
stale. Some filers still report values in thousands despite the 2023 dollars rule; the fetcher
detects and corrects that (a 13F totaling under the $100M filing threshold is a units error).
Copy-trading apps like dub have no public API, which is why this uses the SEC source directly.

### Tradovate demo account setup

To wire this to a real (simulated) account:

1. Create a Tradovate account at [tradovate.com](https://www.tradovate.com) — sign-up includes a
   free demo/simulation account by default, no funding required to practice.
2. Tradovate's REST/WebSocket API requires a registered API app (an app ID + CID/secret pair) —
   apply for API access from your Tradovate account dashboard or contact their support for
   current API-access requirements; policies around which account tiers get API access do change,
   so confirm directly with Tradovate rather than assuming.
3. Once you have credentials, set them as environment variables (never commit them to git):
   ```bash
   export TRADOVATE_USERNAME=you@example.com
   export TRADOVATE_PASSWORD=...
   export TRADOVATE_APP_ID=...
   export TRADOVATE_APP_VERSION=1.0
   export TRADOVATE_CID=...
   export TRADOVATE_SECRET=...
   export TRADOVATE_ACCOUNT_ID=...
   ```
4. Restart the app and click **Connect account** — it authenticates against Tradovate's `demo`
   endpoint. Orders stay in `dry_run=True` (logged, never sent) until you deliberately change that
   in `TradovateBroker`, and only after you've verified behavior against the demo environment.

## Architecture

```
src/algotrader/
  data/loader.py          # yfinance + CSV OHLCV loading
  strategies/              # the 8 archetypes + base.py contract + registry.py (YAML -> Strategy)
  backtest/engine.py        # event-driven bar-by-bar backtester, engine-level stop/target fills
  backtest/metrics.py       # win rate, profit factor, drawdown, Sharpe
  risk/position_sizing.py   # % equity risk sizing + daily loss cap, mirrors the "$1,000/50pt" convention
  live/                     # Broker interface, PaperBroker, TradovateBroker, LiveRunner
  webapp/                   # FastAPI backend + frontend -- the real, locally-run live dashboard
  cli.py                    # `python -m algotrader.cli backtest ...`
```

## Tests

```bash
pip install -e .
pytest
```
