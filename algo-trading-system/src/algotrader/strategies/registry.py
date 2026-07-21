"""No-code strategy builder: instantiate any archetype from a name + a dict of params.

Mirrors the vendor's "Alpha Engine" pitch (set your rules, no code) -- here that's a YAML file
read by config.py and turned into a live Strategy object via build_strategy().
"""
from __future__ import annotations

from datetime import time

from .base import Strategy
from .fast_trend import FastTrend
from .mean_reversion import MeanReversion
from .orb import OpeningRangeBreakout
from .pulse import Pulse
from .rsi2_pullback import Rsi2Pullback
from .squeeze_breakout import SqueezeBreakout
from .swing_trend import SwingTrend
from .vwap_reversion import VwapReversion

STRATEGY_TYPES: dict[str, type[Strategy]] = {
    "orb": OpeningRangeBreakout,
    "fast_trend": FastTrend,
    "pulse": Pulse,
    "mean_reversion": MeanReversion,
    "swing_trend": SwingTrend,
    "rsi2_pullback": Rsi2Pullback,
    "squeeze_breakout": SqueezeBreakout,
    "vwap_reversion": VwapReversion,
}

_TIME_PARAMS = {"session_open", "session_close"}


def _coerce_params(raw_params: dict) -> dict:
    params = dict(raw_params)
    for key in _TIME_PARAMS & params.keys():
        value = params[key]
        if isinstance(value, str):
            hour, minute = value.split(":")
            params[key] = time(int(hour), int(minute))
    return params


def build_strategy(strategy_type: str, params: dict | None = None) -> Strategy:
    if strategy_type not in STRATEGY_TYPES:
        raise ValueError(f"unknown strategy type '{strategy_type}', choose from {list(STRATEGY_TYPES)}")
    cls = STRATEGY_TYPES[strategy_type]
    return cls(**_coerce_params(params or {}))


def build_from_config(config: dict) -> Strategy:
    """config looks like {'type': 'orb', 'params': {...}}."""
    return build_strategy(config["type"], config.get("params", {}))
