"""Volume-at-price clusters ("footprint chart" approximation) from OHLCV bars.

A true footprint / order-flow / cluster chart shows bid-vs-ask traded volume at
every price level inside each bar, which requires tick-level data with trade
direction. Free OHLCV feeds (Yahoo) don't carry that, so this module computes
the standard approximation used when only bars are available:

  * each bar's volume is spread uniformly across the price bins its low-high
    range overlaps (a bar that traded 100k contracts across 4 price levels
    contributes 25k to each);
  * a bar's volume counts as UP volume when close >= open, DOWN otherwise --
    the bar-level proxy for aggressive buying vs selling;
  * the bin with the highest total volume is the POC (point of control).

This is honest scaffolding: once a real tick feed exists (e.g. Tradovate market
data after credentials are set), replace the per-bar uniform spread with true
per-price bid/ask splits and the chart upgrades in place -- the output schema
already matches what a real footprint needs.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

#: (symbol label, timeframe) -> CSV file, matching scripts/scan_win_rates.py sources.
SOURCE_FILES: dict[tuple[str, str], str] = {
    ("Gold (GC)", "1d"): "GC_daily.csv",
    ("Gold (GC)", "5m"): "GC_5min_rth.csv",
    ("S&P 500 (ES)", "1d"): "ES_daily.csv",
    ("S&P 500 (ES)", "5m"): "ES_5min_rth.csv",
    ("Crude Oil (CL)", "1d"): "CL_daily.csv",
    ("Tesla (TSLA)", "1d"): "TSLA_daily.csv",
    ("Nasdaq (NQ)", "5m"): "NQ_5min_rth.csv",
}

APPROXIMATION_NOTE = (
    "Approximated from OHLCV bars (volume spread across each bar's range; up/down split "
    "by close vs open). A true bid×ask footprint requires tick data -- available from "
    "Tradovate market data once connected."
)


def compute_volume_profile(
    bars: pd.DataFrame, num_bins: int = 36, last_n_bars: int = 240
) -> dict:
    """Bin the last N bars' volume by price. Returns bins low->high plus POC index."""
    df = bars.tail(last_n_bars)
    if df.empty:
        return {"bins": [], "poc_index": None, "bars_used": 0, "note": APPROXIMATION_NOTE}

    p_min = float(df["low"].min())
    p_max = float(df["high"].max())
    if p_max <= p_min:
        p_max = p_min + 1.0
    bin_size = (p_max - p_min) / num_bins

    up = [0.0] * num_bins
    down = [0.0] * num_bins
    for _, bar in df.iterrows():
        lo, hi, vol = float(bar["low"]), float(bar["high"]), float(bar["volume"])
        if vol <= 0:
            continue
        first = max(0, min(num_bins - 1, int((lo - p_min) / bin_size)))
        last = max(0, min(num_bins - 1, int((hi - p_min) / bin_size - 1e-9)))
        share = vol / (last - first + 1)
        bucket = up if bar["close"] >= bar["open"] else down
        for b in range(first, last + 1):
            bucket[b] += share

    totals = [u + d for u, d in zip(up, down)]
    poc = max(range(num_bins), key=lambda i: totals[i]) if any(totals) else None
    return {
        "price_min": p_min,
        "price_max": p_max,
        "bin_size": bin_size,
        "bars_used": len(df),
        "from": str(df.index[0]),
        "to": str(df.index[-1]),
        "poc_index": poc,
        "bins": [
            {"p0": p_min + i * bin_size, "p1": p_min + (i + 1) * bin_size,
             "up": round(up[i], 1), "down": round(down[i], 1)}
            for i in range(num_bins)
        ],
        "note": APPROXIMATION_NOTE,
    }


def profile_for_config(
    data_dir: Path, symbol: str, timeframe: str, num_bins: int = 36, last_n_bars: int = 240
) -> dict | None:
    """Load the matching CSV for a scanned config and compute its profile.
    Returns None when no data file maps to this symbol/timeframe."""
    fname = SOURCE_FILES.get((symbol, timeframe))
    if fname is None or not (data_dir / fname).exists():
        return None
    from ..data.loader import load_csv

    return compute_volume_profile(load_csv(data_dir / fname), num_bins, last_n_bars)
