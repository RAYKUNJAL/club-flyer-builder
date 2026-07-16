import json

import pytest
from fastapi.testclient import TestClient

from algotrader.webapp import broker_session
from algotrader.webapp.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    scan = [
        {
            "strategy": "orb",
            "symbol": "Test (X)",
            "timeframe": "5m",
            "params": {"range_minutes": 30},
            "metrics": {
                "num_trades": 10, "win_rate": 0.6, "profit_factor": 1.5, "total_pnl": 1000.0,
                "total_return_pct": 0.02, "max_drawdown_pct": -0.05, "sharpe": 1.1,
                "avg_win": 200.0, "avg_loss": -100.0,
            },
            "equity_curve": [{"t": f"2024-01-{i:02d} 09:30:00", "equity": 50000.0 + i * 10} for i in range(1, 20)],
            "trades": [
                {"side": "long", "entry_time": "2024-01-02 09:30:00", "exit_time": "2024-01-02 10:00:00",
                 "entry_price": 100.0, "exit_price": 101.0, "contracts": 2, "pnl": 40.0,
                 "entry_reason": "orb_breakout_long", "exit_reason": "target_hit"}
            ],
        }
    ]
    (tmp_path / "win_rate_scan.json").write_text(json.dumps(scan))
    monkeypatch.setattr("algotrader.webapp.main.SCAN_FILE", tmp_path / "win_rate_scan.json")
    monkeypatch.setattr("algotrader.webapp.main.TOP_TRADERS_FILE", tmp_path / "top_traders.json")
    monkeypatch.setattr("algotrader.webapp.main.ACTIVE_STRATEGY_FILE", tmp_path / "active_strategy.json")
    broker_session.disconnect()
    return TestClient(app)


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_strategies(client):
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["label"] == "Opening Range Breakout"
    assert data[0]["metrics"]["win_rate"] == 0.6


def test_strategies_404_when_no_scan_file(tmp_path, monkeypatch):
    monkeypatch.setattr("algotrader.webapp.main.SCAN_FILE", tmp_path / "missing.json")
    resp = TestClient(app).get("/api/strategies")
    assert resp.status_code == 404


def test_equity_curve_downsamples(client):
    resp = client.get("/api/strategies/0/equity_curve?points=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 6  # sampled points + guaranteed last point


def test_equity_curve_404_for_bad_id(client):
    assert client.get("/api/strategies/99/equity_curve").status_code == 404


def test_trades_endpoint(client):
    resp = client.get("/api/strategies/0/trades")
    assert resp.status_code == 200
    assert resp.json()[0]["exit_reason"] == "target_hit"


def test_broker_status_defaults_disconnected(client):
    resp = client.get("/api/broker/status")
    assert resp.json() == {"connected": False, "mode": None, "detail": "Disconnected."}


def test_broker_connect_without_credentials_fails_honestly(client, monkeypatch):
    for var in ["TRADOVATE_USERNAME", "TRADOVATE_PASSWORD", "TRADOVATE_APP_ID", "TRADOVATE_CID", "TRADOVATE_SECRET"]:
        monkeypatch.delenv(var, raising=False)
    resp = client.post("/api/broker/connect", json={"mode": "demo"})
    body = resp.json()
    assert body["connected"] is False
    assert "TRADOVATE_USERNAME" in body["detail"]


def test_broker_account_requires_connection(client):
    resp = client.get("/api/broker/account")
    assert resp.status_code == 409


def test_strategies_include_composite_score(client):
    data = client.get("/api/strategies").json()
    assert 0.0 <= data[0]["score"] <= 1.0


def test_top_traders_404_when_no_snapshot(client):
    resp = client.get("/api/top_traders")
    assert resp.status_code == 404
    assert "fetch_top_traders" in resp.json()["detail"]


def test_top_traders_served_from_snapshot(client, tmp_path, monkeypatch):
    snapshot = {
        "source": "SEC EDGAR Form 13F-HR",
        "fetched_at": "2026-07-16T00:00:00+00:00",
        "funds": [{"cik": 1, "fund": "F", "manager": "M", "filing_date": "2026-05-15",
                   "total_value": 1e9, "num_positions": 3,
                   "top_holdings": [{"issuer": "APPLE INC", "value": 5e8, "weight": 0.5}],
                   "reported_in_thousands": False}],
        "errors": [],
    }
    monkeypatch.setattr("algotrader.webapp.main.TOP_TRADERS_FILE", tmp_path / "tt.json")
    (tmp_path / "tt.json").write_text(json.dumps(snapshot))
    data = client.get("/api/top_traders").json()
    assert data["funds"][0]["manager"] == "M"


def test_copy_strategy_select_active_deselect_cycle(client):
    assert client.get("/api/live/active").json() == {"active": None}

    resp = client.post("/api/live/select", json={"strategy_id": 0})
    assert resp.status_code == 200
    active = resp.json()["active"]
    assert active["strategy"] == "orb"
    assert active["strategy_id"] == 0
    assert 0.0 <= active["score"] <= 1.0

    assert client.get("/api/live/active").json()["active"]["strategy_id"] == 0

    client.post("/api/live/deselect")
    assert client.get("/api/live/active").json() == {"active": None}


def test_copy_strategy_404_for_bad_id(client):
    assert client.post("/api/live/select", json={"strategy_id": 42}).status_code == 404
