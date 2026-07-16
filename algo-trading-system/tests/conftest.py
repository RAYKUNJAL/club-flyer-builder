import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def daily_trending_bars():
    """Synthetic daily OHLCV with a clean sustained uptrend -- enough bars for a 55-day Donchian entry."""
    n = 300
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    rng = np.random.default_rng(42)
    drift = np.linspace(0, 150, n)
    noise = rng.normal(0, 1.5, n).cumsum() * 0.2
    close = 100 + drift + noise
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1000, 5000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)


@pytest.fixture
def intraday_session_bars():
    """One trading day of 1-minute bars, 9:30-16:00, with a clear morning breakout."""
    session = pd.date_range("2024-03-01 09:30", "2024-03-01 16:00", freq="1min")
    n = len(session)
    rng = np.random.default_rng(7)
    base = np.concatenate(
        [
            100 + rng.normal(0, 0.05, 45).cumsum(),  # first 45 min: opening range, tight chop
            np.linspace(100, 130, n - 45) + rng.normal(0, 0.1, n - 45).cumsum(),  # then a strong breakout trend
        ]
    )
    high = base + rng.uniform(0.05, 0.3, n)
    low = base - rng.uniform(0.05, 0.3, n)
    open_ = base + rng.normal(0, 0.05, n)
    volume = rng.integers(50, 500, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": base, "volume": volume}, index=session)
