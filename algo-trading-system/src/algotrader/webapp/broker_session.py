"""Process-wide broker connection state for the web app.

A single-user local dev server, so a module-level singleton is enough -- no session
store or auth needed. Holds whichever Broker is currently connected (or none).

Primary broker is Alpaca (paper endpoint): the tradable universe is US equities/
ETFs (GLD, SPY, QQQ, TSLA), which Alpaca supports commission-free. The web app
only ever connects to the PAPER endpoint -- going live requires deliberately
constructing AlpacaBroker(live=True) plus ALPACA_ALLOW_LIVE=1, and no code path
here does that.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..live.alpaca_broker import AlpacaBroker, missing_credentials
from ..live.broker_base import Broker

logger = logging.getLogger(__name__)


@dataclass
class BrokerSession:
    broker: Optional[Broker] = None
    mode: Optional[str] = None  # "paper" (live is never offered here)
    connected: bool = False
    detail: str = "Not connected."


session = BrokerSession()


def connect(mode: str = "paper") -> BrokerSession:
    if mode == "live":
        session.connected = False
        session.broker = None
        session.mode = None
        session.detail = (
            "Live trading is not available from the dashboard. The web app only connects "
            "to Alpaca's paper endpoint; see README for the deliberate two-step required "
            "for anything else."
        )
        return session

    missing = missing_credentials()
    if missing:
        session.connected = False
        session.broker = None
        session.mode = None
        session.detail = (
            "Missing Alpaca credential env var(s): " + ", ".join(missing) + ". "
            "Create a free paper account at alpaca.markets, generate API keys, set "
            "APCA_API_KEY_ID and APCA_API_SECRET_KEY, then try again."
        )
        return session

    broker = AlpacaBroker(live=False)
    try:
        equity = broker.get_equity()
    except Exception:  # network/auth failure against the real API
        # Log the full error server-side only: raw broker/API response bodies must not be
        # echoed to the (unauthenticated) web client.
        logger.exception("Alpaca paper authentication failed")
        session.connected = False
        session.broker = None
        session.mode = None
        session.detail = (
            "Alpaca authentication failed (network or credential error). "
            "Check the server logs for details."
        )
        return session

    session.broker = broker
    session.mode = "paper"
    session.connected = True
    session.detail = f"Connected to Alpaca paper trading (account equity ${equity:,.2f})."
    return session


def disconnect() -> BrokerSession:
    session.broker = None
    session.mode = None
    session.connected = False
    session.detail = "Disconnected."
    return session
