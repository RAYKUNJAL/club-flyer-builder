"""In-memory paper broker -- fills market orders at the last quoted price, no real orders sent.
Use this to dry-run the live runner loop end to end before ever touching a real account.

Assumes the flat -> position -> flat lifecycle the runner drives (enter once from flat, exit
back to flat) -- no partial adds or direct long/short reversal in a single order.
"""
from __future__ import annotations

import uuid

from .broker_base import Broker, BrokerPosition


class PaperBroker(Broker):
    def __init__(self, starting_equity: float = 100_000.0, point_value: float = 20.0):
        self.equity = starting_equity
        self.point_value = point_value
        self._positions: dict[str, BrokerPosition] = {}
        self._last_price: dict[str, float] = {}
        self.order_log: list[dict] = []
        self.resting_orders: dict[str, dict] = {}

    def update_quote(self, symbol: str, price: float) -> None:
        self._last_price[symbol] = price

    def get_equity(self) -> float:
        return self.equity

    def get_position(self, symbol: str) -> BrokerPosition:
        return self._positions.get(symbol, BrokerPosition(symbol=symbol, side="flat", contracts=0, avg_price=0.0))

    def place_market_order(self, symbol: str, side: str, contracts: int) -> str:
        price = self._last_price.get(symbol)
        if price is None:
            raise RuntimeError(f"no quote for {symbol}; call update_quote() first")

        order_id = str(uuid.uuid4())
        pos = self.get_position(symbol)

        if pos.side == "flat":
            new_side = "long" if side == "buy" else "short"
            self._positions[symbol] = BrokerPosition(symbol, new_side, contracts, price)
        else:
            # Closing (fully or partially) an existing position.
            closing_side = "sell" if pos.side == "long" else "buy"
            if side != closing_side:
                raise NotImplementedError("paper broker only supports flat->position->flat, not adds/reversals")
            direction = 1 if pos.side == "long" else -1
            close_qty = min(contracts, pos.contracts)
            self.equity += (price - pos.avg_price) * direction * self.point_value * close_qty
            remaining = pos.contracts - close_qty
            self._positions[symbol] = (
                BrokerPosition(symbol, "flat", 0, 0.0)
                if remaining == 0
                else BrokerPosition(symbol, pos.side, remaining, pos.avg_price)
            )

        self.order_log.append({"id": order_id, "symbol": symbol, "side": side, "contracts": contracts, "price": price})
        return order_id

    def flatten(self, symbol: str) -> None:
        pos = self.get_position(symbol)
        if pos.contracts == 0:
            return
        side = "sell" if pos.side == "long" else "buy"
        self.place_market_order(symbol, side, pos.contracts)

    # -- resting stop orders (recorded, not simulated tick-by-tick) ---------------
    def place_stop_order(self, symbol: str, side: str, contracts: int, stop_price: float) -> str:
        order_id = str(uuid.uuid4())
        self.resting_orders[order_id] = {
            "symbol": symbol, "side": side, "contracts": contracts,
            "stop_price": stop_price, "type": "stop",
        }
        self.order_log.append({"id": order_id, "symbol": symbol, "side": side,
                               "contracts": contracts, "stop_price": stop_price, "type": "stop"})
        return order_id

    def cancel_order(self, order_id: str) -> None:
        self.resting_orders.pop(order_id, None)
