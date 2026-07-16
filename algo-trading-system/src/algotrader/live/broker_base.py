"""Broker interface every execution backend (paper or Tradovate) implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BrokerPosition:
    symbol: str
    side: str  # "long" | "short" | "flat"
    contracts: int
    avg_price: float


class Broker(ABC):
    @abstractmethod
    def get_equity(self) -> float:
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> BrokerPosition:
        ...

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, contracts: int) -> str:
        """side is 'buy' or 'sell'. Returns a broker order id."""

    @abstractmethod
    def flatten(self, symbol: str) -> None:
        ...

    def place_stop_order(self, symbol: str, side: str, contracts: int, stop_price: float) -> str:
        """Rest a protective stop order at the broker so the position stays protected even if
        this process dies or loses connectivity. side is 'buy' or 'sell'. Returns an order id.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support resting stop orders")

    def cancel_order(self, order_id: str) -> None:
        """Cancel a resting (e.g. stop) order previously placed at the broker."""
        raise NotImplementedError(f"{type(self).__name__} does not support order cancellation")
