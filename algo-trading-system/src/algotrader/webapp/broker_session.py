"""Process-wide broker connection state for the web app.

A single-user local dev server, so a module-level singleton is enough -- no session
store or auth needed. Holds whichever Broker is currently connected (or none).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..live.broker_base import Broker
from ..live.tradovate_broker import TradovateBroker

logger = logging.getLogger(__name__)


@dataclass
class BrokerSession:
    broker: Optional[Broker] = None
    mode: Optional[str] = None  # "demo" | "live"
    connected: bool = False
    detail: str = "Not connected."


session = BrokerSession()


def connect(mode: str = "demo") -> BrokerSession:
    demo = mode != "live"
    broker = TradovateBroker(demo=demo, dry_run=True)
    try:
        broker.authenticate()
    except KeyError as exc:
        session.connected = False
        session.broker = None
        session.mode = None
        session.detail = (
            f"Missing Tradovate credential env var: {exc}. Set TRADOVATE_USERNAME, "
            "TRADOVATE_PASSWORD, TRADOVATE_APP_ID, TRADOVATE_CID, TRADOVATE_SECRET "
            "(see README: 'Tradovate demo account setup') and try again."
        )
        return session
    except Exception:  # network/auth failure against the real API
        # Log the full error server-side only: raw broker/API response bodies must not be
        # echoed to the (unauthenticated) web client.
        logger.exception("Tradovate authentication failed (mode=%s)", mode)
        session.connected = False
        session.broker = None
        session.mode = None
        session.detail = (
            "Tradovate authentication failed (network or credential error). "
            "Check the server logs for details."
        )
        return session

    session.broker = broker
    session.mode = mode
    session.connected = True
    session.detail = f"Connected to Tradovate ({mode}). Orders are in dry-run mode (no real fills)."
    return session


def disconnect() -> BrokerSession:
    session.broker = None
    session.mode = None
    session.connected = False
    session.detail = "Disconnected."
    return session
