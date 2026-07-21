import numpy as np
import pandas as pd

from algotrader.webapp.volume_profile import compute_volume_profile


def _bars(rows):
    idx = pd.date_range("2024-01-02 09:30", periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])


def test_up_down_split_and_conservation():
    bars = _bars([
        [100.0, 101.0, 100.0, 101.0, 1000.0],  # up bar
        [101.0, 101.0, 100.0, 100.0, 500.0],   # down bar
    ])
    p = compute_volume_profile(bars, num_bins=4)
    total_up = sum(b["up"] for b in p["bins"])
    total_down = sum(b["down"] for b in p["bins"])
    assert abs(total_up - 1000.0) < 1.0
    assert abs(total_down - 500.0) < 1.0


def test_poc_is_highest_volume_bin():
    # Heavy trading concentrated at ~100, light wings elsewhere.
    rows = [[100.0, 100.5, 99.5, 100.2, 10_000.0] for _ in range(20)]
    rows += [[105.0, 105.5, 104.5, 105.2, 100.0] for _ in range(3)]
    p = compute_volume_profile(_bars(rows), num_bins=12)
    poc = p["bins"][p["poc_index"]]
    assert poc["p0"] <= 100.5 and poc["p1"] >= 99.5


def test_empty_data_returns_empty_profile():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    p = compute_volume_profile(empty)
    assert p["bins"] == [] and p["poc_index"] is None


def test_bar_volume_spread_across_range():
    # One bar spanning the full range should touch every bin it overlaps.
    bars = _bars([[100.0, 104.0, 100.0, 104.0, 400.0]])
    p = compute_volume_profile(bars, num_bins=4)
    touched = [b for b in p["bins"] if b["up"] > 0]
    assert len(touched) == 4
    assert all(abs(b["up"] - 100.0) < 1.0 for b in touched)
