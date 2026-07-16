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

from . import broker_session

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCAN_FILE = DATA_DIR / "win_rate_scan.json"

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
        out.append(
            {
                "id": i,
                "strategy": d["strategy"],
                "label": STRATEGY_LABELS.get(d["strategy"], d["strategy"]),
                "symbol": d["symbol"],
                "timeframe": d["timeframe"],
                "params": d["params"],
                "metrics": d["metrics"],
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


class ConnectRequest(BaseModel):
    mode: Literal["demo", "live"] = "demo"


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
