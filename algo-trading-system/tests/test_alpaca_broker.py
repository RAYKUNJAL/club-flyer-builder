import pytest

from algotrader.live.alpaca_broker import PAPER_URL, AlpacaBroker, missing_credentials


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "test-key")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "test-secret")
    monkeypatch.delenv("ALPACA_ALLOW_LIVE", raising=False)


def test_missing_credentials_reported_by_name(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    assert missing_credentials() == ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]
    with pytest.raises(RuntimeError, match="APCA_API_KEY_ID"):
        AlpacaBroker()


def test_live_refused_without_second_deliberate_step(creds):
    with pytest.raises(RuntimeError, match="ALPACA_ALLOW_LIVE"):
        AlpacaBroker(live=True)


def test_defaults_to_paper_endpoint(creds):
    assert AlpacaBroker().base_url == PAPER_URL


def test_position_404_means_flat(creds, monkeypatch):
    broker = AlpacaBroker()
    monkeypatch.setattr(broker, "_request", lambda *a, **k: None)
    pos = broker.get_position("SPY")
    assert pos.side == "flat" and pos.contracts == 0


def test_market_orders_carry_unique_client_ids(creds, monkeypatch):
    broker = AlpacaBroker()
    sent = []

    def fake_request(method, path, json_body=None):
        sent.append(json_body)
        return {"id": f"order-{len(sent)}"}

    monkeypatch.setattr(broker, "_request", fake_request)
    broker.place_market_order("SPY", "buy", 10)
    broker.place_market_order("SPY", "buy", 10)
    ids = [b["client_order_id"] for b in sent]
    assert len(set(ids)) == 2  # unique per order -- broker-side duplicate protection
    assert all(i.startswith("algotrader-") for i in ids)
    assert sent[0]["type"] == "market" and sent[0]["qty"] == "10"


def test_stop_order_is_gtc_stop_type(creds, monkeypatch):
    broker = AlpacaBroker()
    sent = []
    monkeypatch.setattr(broker, "_request",
                        lambda m, p, json_body=None: (sent.append(json_body), {"id": "s1"})[1])
    broker.place_stop_order("SPY", "sell", 10, 512.34)
    assert sent[0]["type"] == "stop"
    assert sent[0]["stop_price"] == "512.34"
    assert sent[0]["time_in_force"] == "gtc"
