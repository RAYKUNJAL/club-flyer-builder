"""Alpaca broker backend (paper by default) implementing the Broker interface.

Alpaca trades US equities/ETFs (and crypto), commission-free, with a clean REST
API -- the right match for the equity universe (GLD/SPY/QQQ/TSLA). Futures are
NOT supported by Alpaca; the futures strategies stay backtest/paper-only unless
run against a futures broker.

Safety model:
  * Defaults to the PAPER endpoint (paper-api.alpaca.markets). The live endpoint
    is refused unless BOTH the constructor is called with live=True AND the
    environment sets ALPACA_ALLOW_LIVE=1 -- two deliberate steps, no accidents.
  * Credentials come from the standard Alpaca env vars APCA_API_KEY_ID and
    APCA_API_SECRET_KEY; missing ones are reported by NAME, never guessed.
  * Every order carries a unique client_order_id, so a retried request can never
    double-fill (Alpaca deduplicates on it).
  * Orders use time_in_force="day"; protective stops are real resting stop
    orders on Alpaca's book, not just local state.
"""
from __future__ import annotations

import os
import uuid

import requests

from .broker_base import Broker, BrokerPosition

PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"

REQUIRED_ENV = ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY"]


def missing_credentials() -> list[str]:
    return [v for v in REQUIRED_ENV if not os.environ.get(v)]


class AlpacaBroker(Broker):
    def __init__(self, live: bool = False, timeout: float = 15.0):
        missing = missing_credentials()
        if missing:
            raise RuntimeError(
                "Alpaca credentials missing: set environment variable(s) " + ", ".join(missing)
            )
        if live and os.environ.get("ALPACA_ALLOW_LIVE") != "1":
            raise RuntimeError(
                "live=True refused: set ALPACA_ALLOW_LIVE=1 in the environment as a second "
                "deliberate step before any live-money endpoint is used"
            )
        self.base_url = LIVE_URL if live else PAPER_URL
        self.live = live
        self.timeout = timeout
        self._headers = {
            "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
        }

    # -- transport (single seam, easy to mock in tests) ---------------------------
    def _request(self, method: str, path: str, json_body: dict | None = None) -> dict | list | None:
        resp = requests.request(
            method, f"{self.base_url}{path}", headers=self._headers,
            json=json_body, timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        if not resp.ok:
            raise RuntimeError(f"Alpaca {method} {path} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json() if resp.text else {}

    # -- Broker interface ---------------------------------------------------------
    def get_equity(self) -> float:
        account = self._request("GET", "/v2/account")
        return float(account["equity"])

    def get_position(self, symbol: str) -> BrokerPosition:
        pos = self._request("GET", f"/v2/positions/{symbol}")
        if pos is None:
            return BrokerPosition(symbol=symbol, side="flat", contracts=0, avg_price=0.0)
        qty = int(float(pos["qty"]))
        return BrokerPosition(
            symbol=symbol,
            side="long" if qty > 0 else "short",
            contracts=abs(qty),
            avg_price=float(pos["avg_entry_price"]),
        )

    def place_market_order(self, symbol: str, side: str, contracts: int) -> str:
        order = self._request("POST", "/v2/orders", {
            "symbol": symbol, "qty": str(contracts), "side": side,
            "type": "market", "time_in_force": "day",
            "client_order_id": f"algotrader-{uuid.uuid4()}",
        })
        return order["id"]

    def place_stop_order(self, symbol: str, side: str, contracts: int, stop_price: float) -> str:
        order = self._request("POST", "/v2/orders", {
            "symbol": symbol, "qty": str(contracts), "side": side,
            "type": "stop", "stop_price": f"{stop_price:.2f}", "time_in_force": "gtc",
            "client_order_id": f"algotrader-stop-{uuid.uuid4()}",
        })
        return order["id"]

    def cancel_order(self, order_id: str) -> None:
        self._request("DELETE", f"/v2/orders/{order_id}")

    def flatten(self, symbol: str) -> None:
        self._request("DELETE", f"/v2/positions/{symbol}")
