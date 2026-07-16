"""Tradovate REST API client -- the broker the vendor's own site pairs with NinjaTrader for
automated futures execution. Talks to the public Tradovate API (demo environment by default).

Credentials are read from environment variables, never hardcoded:
  TRADOVATE_USERNAME, TRADOVATE_PASSWORD, TRADOVATE_APP_ID, TRADOVATE_APP_VERSION,
  TRADOVATE_CID, TRADOVATE_SECRET, TRADOVATE_ACCOUNT_ID

Safety: `dry_run=True` by default. In dry-run mode, place_market_order/flatten log the intended
order and return a fake id instead of calling the API. You must pass dry_run=False explicitly
(after testing against the demo endpoint) to route real orders.
"""
from __future__ import annotations

import os
import uuid

import requests

from .broker_base import Broker, BrokerPosition

DEMO_BASE_URL = "https://demo.tradovateapi.com/v1"
LIVE_BASE_URL = "https://live.tradovateapi.com/v1"


class TradovateBroker(Broker):
    def __init__(self, demo: bool = True, dry_run: bool = True, account_id: int | None = None):
        self.base_url = DEMO_BASE_URL if demo else LIVE_BASE_URL
        self.dry_run = dry_run
        self.account_id = account_id or int(os.environ.get("TRADOVATE_ACCOUNT_ID", "0") or 0)
        self._access_token: str | None = None
        self.order_log: list[dict] = []

    # -- auth -----------------------------------------------------------------
    def authenticate(self) -> None:
        payload = {
            "name": os.environ["TRADOVATE_USERNAME"],
            "password": os.environ["TRADOVATE_PASSWORD"],
            "appId": os.environ["TRADOVATE_APP_ID"],
            "appVersion": os.environ.get("TRADOVATE_APP_VERSION", "1.0"),
            "cid": os.environ["TRADOVATE_CID"],
            "sec": os.environ["TRADOVATE_SECRET"],
        }
        resp = requests.post(f"{self.base_url}/auth/accesstokenrequest", json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "accessToken" not in data:
            raise RuntimeError(f"tradovate auth failed: {data}")
        self._access_token = data["accessToken"]

    def _headers(self) -> dict:
        if self._access_token is None:
            self.authenticate()
        return {"Authorization": f"Bearer {self._access_token}"}

    # -- account / positions ----------------------------------------------------
    def get_equity(self) -> float:
        resp = requests.get(f"{self.base_url}/cashBalance/getcashbalancesnapshot",
                             params={"accountId": self.account_id}, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        return float(resp.json().get("netLiq", 0.0))

    def get_position(self, symbol: str) -> BrokerPosition:
        resp = requests.get(f"{self.base_url}/position/list", headers=self._headers(), timeout=15)
        resp.raise_for_status()
        for p in resp.json():
            if p.get("accountId") == self.account_id and str(p.get("contractId")) == symbol:
                qty = p.get("netPos", 0)
                if qty == 0:
                    return BrokerPosition(symbol, "flat", 0, 0.0)
                side = "long" if qty > 0 else "short"
                return BrokerPosition(symbol, side, abs(qty), p.get("netPrice", 0.0))
        return BrokerPosition(symbol, "flat", 0, 0.0)

    # -- orders -----------------------------------------------------------------
    def place_market_order(self, symbol: str, side: str, contracts: int) -> str:
        if self.dry_run:
            order_id = f"dryrun-{uuid.uuid4()}"
            self.order_log.append({"id": order_id, "symbol": symbol, "side": side, "contracts": contracts})
            return order_id

        payload = {
            "accountId": self.account_id,
            "action": "Buy" if side == "buy" else "Sell",
            "symbol": symbol,
            "orderQty": contracts,
            "orderType": "Market",
            "isAutomated": True,
        }
        resp = requests.post(f"{self.base_url}/order/placeorder", json=payload, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        order_id = str(data.get("orderId", ""))
        self.order_log.append({"id": order_id, "symbol": symbol, "side": side, "contracts": contracts})
        return order_id

    def flatten(self, symbol: str) -> None:
        pos = self.get_position(symbol)
        if pos.contracts == 0:
            return
        side = "sell" if pos.side == "long" else "buy"
        self.place_market_order(symbol, side, pos.contracts)

    def place_stop_order(self, symbol: str, side: str, contracts: int, stop_price: float) -> str:
        """Rest a protective stop at Tradovate so the position is protected broker-side even
        if this process crashes or loses connectivity."""
        if self.dry_run:
            order_id = f"dryrun-stop-{uuid.uuid4()}"
            self.order_log.append({"id": order_id, "symbol": symbol, "side": side,
                                   "contracts": contracts, "stop_price": stop_price, "type": "stop"})
            return order_id

        payload = {
            "accountId": self.account_id,
            "action": "Buy" if side == "buy" else "Sell",
            "symbol": symbol,
            "orderQty": contracts,
            "orderType": "Stop",
            "stopPrice": stop_price,
            "isAutomated": True,
        }
        resp = requests.post(f"{self.base_url}/order/placeorder", json=payload, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        order_id = str(data.get("orderId", ""))
        self.order_log.append({"id": order_id, "symbol": symbol, "side": side,
                               "contracts": contracts, "stop_price": stop_price, "type": "stop"})
        return order_id

    def cancel_order(self, order_id: str) -> None:
        if self.dry_run or order_id.startswith("dryrun-"):
            self.order_log.append({"id": order_id, "type": "cancel"})
            return
        resp = requests.post(f"{self.base_url}/order/cancelorder", json={"orderId": int(order_id)},
                             headers=self._headers(), timeout=15)
        resp.raise_for_status()
