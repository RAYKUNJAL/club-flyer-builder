"""Footprint (order-flow / cluster) chart data built from 1-minute OHLCV bars.

A true footprint chart needs tick-by-tick trades tagged with aggressor side
(bid hit vs offer lifted). That data is licensed for CME futures (Databento,
IQFeed, or Tradovate's market-data feed on a connected account) -- Yahoo bars
don't carry it. This module builds the honest approximation that IS possible
from public 1-minute bars, and labels itself as such:

  * Each display candle (default 15 min) is split into price bins.
  * Each 1-minute bar's volume is classified long/short by the classic TICK
    RULE -- volume on an uptick counts as buying, on a downtick as selling,
    and an unchanged close carries the previous direction. Research on the
    tick rule (Lee & Ready 1991 and successors) puts its per-trade accuracy
    around 75-85%; treat cluster values as estimates, not tape truth.
  * A bar's volume is spread uniformly across the price bins its high-low
    range covers -- we can't know the true intrabar distribution from OHLCV.

The output shape is exactly what a real tick feed would produce ({price bin ->
buy volume, sell volume} per candle), so when Tradovate market data is wired
in, only the builder changes -- the API and chart stay identical.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class FootprintCandle:
    t: str
    open: float
    high: float
    low: float
    close: float
    clusters: list[dict] = field(default_factory=list)  # [{p, buy, sell}] high -> low
    delta: float = 0.0
    total: float = 0.0
    poc: float = 0.0  # price bin with the highest total volume


def _default_price_step(bars: pd.DataFrame, target_bins: int = 10) -> float:
    """Pick a bin size that gives displayable candles: ~target_bins rows for a
    typical candle. Snapped to a 0.25 grid (the ES/NQ/GC tick family)."""
    candle_ranges = bars["high"].rolling(15).max() - bars["low"].rolling(15).min()
    typical = float(candle_ranges.quantile(0.75))
    if not math.isfinite(typical) or typical <= 0:
        return 0.25
    step = max(round(typical / target_bins / 0.25) * 0.25, 0.25)
    return step


def build_footprint(
    bars_1m: pd.DataFrame,
    candle_minutes: int = 15,
    price_step: float | None = None,
    max_candles: int = 26,
) -> dict:
    """Aggregate 1-minute OHLCV bars into footprint candles.

    bars_1m needs columns open/high/low/close/volume and a DatetimeIndex.
    Returns the last `max_candles` candles plus chart-level context.
    """
    bars = bars_1m[bars_1m["volume"] > 0].copy()
    if bars.empty:
        return {"candles": [], "price_step": 0.25, "cum_delta": [],
                "method": _METHOD_NOTE, "candle_minutes": candle_minutes}

    step = price_step if price_step is not None else _default_price_step(bars)

    # Tick rule with carry: uptick -> buy, downtick -> sell, unchanged -> previous.
    closes = bars["close"].to_numpy()
    direction = 1
    directions = []
    prev_close = None
    for c in closes:
        if prev_close is not None:
            if c > prev_close:
                direction = 1
            elif c < prev_close:
                direction = -1
        directions.append(direction)
        prev_close = c
    bars["dir"] = directions

    candles: list[FootprintCandle] = []
    for t0, grp in bars.groupby(bars.index.floor(f"{candle_minutes}min")):
        clusters: dict[float, dict] = {}
        for _, row in grp.iterrows():
            lo_bin = math.floor(row["low"] / step) * step
            hi_bin = math.floor(row["high"] / step) * step
            n_bins = int(round((hi_bin - lo_bin) / step)) + 1
            vol_per_bin = row["volume"] / n_bins
            for k in range(n_bins):
                p = round(lo_bin + k * step, 4)
                cell = clusters.setdefault(p, {"p": p, "buy": 0.0, "sell": 0.0})
                if row["dir"] > 0:
                    cell["buy"] += vol_per_bin
                else:
                    cell["sell"] += vol_per_bin
        ordered = sorted(clusters.values(), key=lambda c: c["p"], reverse=True)
        for c in ordered:
            c["buy"] = round(c["buy"], 1)
            c["sell"] = round(c["sell"], 1)
        total = sum(c["buy"] + c["sell"] for c in ordered)
        delta = sum(c["buy"] - c["sell"] for c in ordered)
        poc = max(ordered, key=lambda c: c["buy"] + c["sell"])["p"] if ordered else 0.0
        candles.append(FootprintCandle(
            t=str(t0),
            open=float(grp["open"].iloc[0]), high=float(grp["high"].max()),
            low=float(grp["low"].min()), close=float(grp["close"].iloc[-1]),
            clusters=ordered, delta=round(delta, 1), total=round(total, 1), poc=poc,
        ))

    candles = candles[-max_candles:]
    cum = 0.0
    cum_delta = []
    for c in candles:
        cum += c.delta
        cum_delta.append(round(cum, 1))
    return {
        "candles": [c.__dict__ for c in candles],
        "price_step": step,
        "cum_delta": cum_delta,
        "candle_minutes": candle_minutes,
        "method": _METHOD_NOTE,
    }


_METHOD_NOTE = (
    "Approximated from real 1-minute OHLCV bars: tick-rule aggressor classification "
    "(~75-85% accurate per research), volume spread uniformly across each bar's range. "
    "True bid/ask footprints require a tick feed (e.g. Tradovate market data once connected)."
)
