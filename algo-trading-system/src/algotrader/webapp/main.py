"""Real backend for the strategy dashboard: serves backtest results over HTTP and
exposes a real (dry-run-by-default) Tradovate connection -- this is the piece a
static, sandboxed page (like a hosted Claude Artifact) cannot do, since that kind
of page is blocked from making outbound network calls entirely. Run this locally
(or on your own server) and it can actually reach Tradovate's API.

Run:
    uvicorn algotrader.webapp.main:app --reload --port 8000
Then open http://localhost:8000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..backtest.scoring import composite_score
from ..live.paper_tracker import PaperTracker
from . import broker_session
from .volume_profile import profile_for_config

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCAN_FILE = DATA_DIR / "win_rate_scan.json"
TOP_TRADERS_FILE = DATA_DIR / "top_traders.json"
ACTIVE_STRATEGY_FILE = DATA_DIR / "active_strategy.json"
PAPER_TRADES_FILE = DATA_DIR / "paper_trades.json"

STRATEGY_LABELS = {
    "orb": "Opening Range Breakout",
    "fast_trend": "Fast Trend",
    "pulse": "Pulse (All-Session Trend)",
    "mean_reversion": "Mean Reversion",
    "swing_trend": "Swing Trend",
    "rsi2_pullback": "RSI-2 Pullback",
    "squeeze_breakout": "Squeeze Breakout",
    "vwap_reversion": "VWAP Reversion",
}

app = FastAPI(title="algotrader dashboard API")


def _load_scan() -> list[dict]:
    if not SCAN_FILE.exists():
        return []
    return json.loads(SCAN_FILE.read_text())


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/strategies")
def list_strategies():
    scan = _load_scan()
    if not scan:
        raise HTTPException(
            404,
            "No backtest results found. Run `python scripts/fetch_yahoo_chart.py ...` then "
            "`python scripts/scan_win_rates.py` from the repo root first.",
        )
    out = []
    for i, d in enumerate(scan):
        m = d["metrics"]
        out.append(
            {
                "id": i,
                "strategy": d["strategy"],
                "label": STRATEGY_LABELS.get(d["strategy"], d["strategy"]),
                "symbol": d["symbol"],
                "timeframe": d["timeframe"],
                "params": d["params"],
                # Older scan files predate the composite score -- compute on the fly.
                "score": d.get(
                    "score",
                    composite_score(m["win_rate"], m["profit_factor"], m["sharpe"], m["max_drawdown_pct"]),
                ),
                "validation": d.get("validation"),
                "metrics": m,
            }
        )
    return out


def _get_strategy_or_404(strategy_id: int) -> dict:
    scan = _load_scan()
    if strategy_id < 0 or strategy_id >= len(scan):
        raise HTTPException(404, f"no strategy with id {strategy_id}")
    return scan[strategy_id]


@app.get("/api/strategies/{strategy_id}/equity_curve")
def equity_curve(strategy_id: int, points: int = 200):
    d = _get_strategy_or_404(strategy_id)
    curve = d["equity_curve"]
    n = len(curve)
    if n <= points:
        return curve
    step = n / points
    sampled = [curve[int(i * step)] for i in range(points)]
    sampled.append(curve[-1])
    return sampled


@app.get("/api/strategies/{strategy_id}/trades")
def trades(strategy_id: int):
    d = _get_strategy_or_404(strategy_id)
    return d["trades"]


@app.get("/api/strategies/{strategy_id}/volume_profile")
def volume_profile(strategy_id: int, bins: int = 36, bars: int = 240):
    """Volume-at-price clusters (footprint approximation) for this config's market data."""
    d = _get_strategy_or_404(strategy_id)
    profile = profile_for_config(DATA_DIR, d["symbol"], d["timeframe"], bins, bars)
    if profile is None:
        raise HTTPException(
            404,
            f"no market data file for {d['symbol']} {d['timeframe']} -- run "
            "scripts/fetch_yahoo_chart.py for that symbol first",
        )
    return profile


@app.get("/api/paper/summary")
def paper_summary():
    """Live paper-trading performance vs the active strategy's backtest, with kill criteria."""
    tracker = PaperTracker(PAPER_TRADES_FILE)
    backtest = None
    if ACTIVE_STRATEGY_FILE.exists():
        active = json.loads(ACTIVE_STRATEGY_FILE.read_text())
        scan = _load_scan()
        sid = active.get("strategy_id")
        if isinstance(sid, int) and 0 <= sid < len(scan):
            backtest = scan[sid]["metrics"]
    return tracker.summary(backtest)


@app.get("/api/paper/trades")
def paper_trades():
    tracker = PaperTracker(PAPER_TRADES_FILE)
    return tracker.trades


FOOTPRINT_SOURCES = {
    # Alpaca-tradable universe first; legacy futures kept for reference
    "SPY": ("SPY_1min.csv", "S&P 500 ETF (SPY)"),
    "QQQ": ("QQQ_1min.csv", "Nasdaq ETF (QQQ)"),
    "TSLA": ("TSLA_1min.csv", "Tesla (TSLA)"),
    "ES": ("ES_1min.csv", "S&P 500 (ES)"),
}


@app.get("/api/footprint/{symbol}")
def footprint(symbol: str, candle_minutes: int = 15, max_candles: int = 26, price_step: float | None = None):
    """Order-flow footprint clusters, approximated from real 1-minute bars."""
    src = FOOTPRINT_SOURCES.get(symbol.upper())
    if src is None:
        raise HTTPException(404, f"no footprint source for '{symbol}' -- one of {sorted(FOOTPRINT_SOURCES)}")
    fname, label = src
    csv_path = DATA_DIR / fname
    if not csv_path.exists():
        raise HTTPException(
            404,
            f"{fname} not found. Fetch it first: python scripts/fetch_yahoo_chart.py "
            f"'{symbol}=F' --range 5d --interval 1m --out data/{fname}",
        )
    import pandas as pd

    from ..analytics.footprint import build_footprint

    bars = pd.read_csv(csv_path, parse_dates=["timestamp"], index_col="timestamp")
    out = build_footprint(bars, candle_minutes=candle_minutes, max_candles=max_candles, price_step=price_step)
    out["symbol"] = label
    return out


@app.get("/api/top_traders")
def top_traders():
    """Leaderboard of famous fund managers' latest disclosed portfolios (SEC 13F)."""
    if not TOP_TRADERS_FILE.exists():
        raise HTTPException(
            404,
            "No 13F snapshot found. Run `python scripts/fetch_top_traders.py` from the "
            "repo root to pull the latest filings from SEC EDGAR (free, no API key).",
        )
    return json.loads(TOP_TRADERS_FILE.read_text())


class SelectRequest(BaseModel):
    strategy_id: int


@app.post("/api/live/select")
def live_select(req: SelectRequest):
    """'Copy' a leaderboard strategy: mark it as the active config for the live runner.

    This only selects -- it never starts trading by itself. The live runner (and its
    dry-run/demo defaults) still has to be started explicitly on the server.
    """
    from datetime import datetime, timezone

    d = _get_strategy_or_404(req.strategy_id)
    m = d["metrics"]
    active = {
        "strategy_id": req.strategy_id,
        "strategy": d["strategy"],
        "label": STRATEGY_LABELS.get(d["strategy"], d["strategy"]),
        "symbol": d["symbol"],
        "timeframe": d["timeframe"],
        "params": d["params"],
        "score": d.get(
            "score",
            composite_score(m["win_rate"], m["profit_factor"], m["sharpe"], m["max_drawdown_pct"]),
        ),
        "selected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    ACTIVE_STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_STRATEGY_FILE.write_text(json.dumps(active, indent=2))
    return {"active": active}


@app.get("/api/live/active")
def live_active():
    if not ACTIVE_STRATEGY_FILE.exists():
        return {"active": None}
    return {"active": json.loads(ACTIVE_STRATEGY_FILE.read_text())}


@app.post("/api/live/deselect")
def live_deselect():
    if ACTIVE_STRATEGY_FILE.exists():
        ACTIVE_STRATEGY_FILE.unlink()
    return {"active": None}


class ConnectRequest(BaseModel):
    mode: Literal["paper", "live"] = "paper"


@app.get("/api/broker/status")
def broker_status():
    s = broker_session.session
    return {"connected": s.connected, "mode": s.mode, "detail": s.detail}


@app.post("/api/broker/connect")
def broker_connect(req: ConnectRequest):
    s = broker_session.connect(req.mode)
    return {"connected": s.connected, "mode": s.mode, "detail": s.detail}


@app.post("/api/broker/disconnect")
def broker_disconnect():
    s = broker_session.disconnect()
    return {"connected": s.connected, "mode": s.mode, "detail": s.detail}


@app.get("/api/broker/account")
def broker_account():
    s = broker_session.session
    if not s.connected or s.broker is None:
        raise HTTPException(409, "not connected -- call POST /api/broker/connect first")
    try:
        equity = s.broker.get_equity()
    except Exception as exc:
        raise HTTPException(502, f"broker call failed: {exc}") from None
    return {"equity": equity, "mode": s.mode}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
