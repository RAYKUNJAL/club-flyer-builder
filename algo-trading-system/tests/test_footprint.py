import numpy as np
import pandas as pd

from algotrader.analytics.footprint import build_footprint


def _bars(closes, volumes=None, spread=0.0):
    idx = pd.date_range("2026-07-15 09:30", periods=len(closes), freq="1min")
    closes = np.asarray(closes, dtype=float)
    vols = np.asarray(volumes if volumes is not None else [100.0] * len(closes))
    return pd.DataFrame(
        {"open": closes, "high": closes + spread, "low": closes - spread,
         "close": closes, "volume": vols},
        index=idx,
    )


def test_uptick_volume_counts_as_buying_downtick_as_selling():
    # 5 rising closes then 5 falling: buys should dominate the first candle's top,
    # sells the move down. Use zero spread so each bar maps to exactly one bin.
    data = _bars([100, 101, 102, 103, 104, 103, 102, 101, 100, 99], spread=0.0)
    fp = build_footprint(data, candle_minutes=5, price_step=1.0)
    assert len(fp["candles"]) == 2
    up, down = fp["candles"]
    assert up["delta"] > 0, "rising candle must show positive delta under the tick rule"
    assert down["delta"] < 0, "falling candle must show negative delta"


def test_unchanged_close_carries_previous_direction():
    data = _bars([100, 101, 101, 101], spread=0.0)
    fp = build_footprint(data, candle_minutes=5, price_step=1.0)
    c = fp["candles"][0]
    # bars 2-4 all land in the 101 bin; direction stays 'buy' from the 100->101 uptick
    cell_101 = next(cl for cl in c["clusters"] if cl["p"] == 101.0)
    assert cell_101["buy"] == 300.0 and cell_101["sell"] == 0.0


def test_volume_conserved_across_clusters():
    data = _bars([100, 102, 101, 103, 102], volumes=[50, 150, 200, 100, 75], spread=1.0)
    fp = build_footprint(data, candle_minutes=5, price_step=0.5)
    c = fp["candles"][0]
    assert abs(c["total"] - 575.0) < 1.0  # rounding to 0.1 per cell


def test_poc_is_highest_volume_bin():
    # Heavy volume at 101, light elsewhere.
    data = _bars([100, 101, 101, 102], volumes=[10, 500, 500, 10], spread=0.0)
    fp = build_footprint(data, candle_minutes=5, price_step=1.0)
    assert fp["candles"][0]["poc"] == 101.0


def test_cum_delta_accumulates_across_candles():
    data = _bars(list(range(100, 110)), spread=0.0)  # 10 rising bars = all buying
    fp = build_footprint(data, candle_minutes=5, price_step=1.0)
    assert fp["cum_delta"][-1] > fp["cum_delta"][0] > 0
    assert fp["cum_delta"] == sorted(fp["cum_delta"])


def test_empty_or_zero_volume_input():
    data = _bars([100, 101], volumes=[0, 0])
    fp = build_footprint(data)
    assert fp["candles"] == [] and fp["cum_delta"] == []


def test_method_note_discloses_approximation():
    data = _bars([100, 101])
    fp = build_footprint(data)
    assert "tick-rule" in fp["method"].lower() or "tick rule" in fp["method"].lower()
