"""OHLCV data loading: yfinance for quick backtests, CSV for real futures tick/minute data."""
from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"data missing required columns: {missing}")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df[REQUIRED_COLUMNS]


def load_yfinance(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Pull OHLCV bars via yfinance. interval='1m' is capped at ~8 days by Yahoo; use '1h'/'1d' for longer history."""
    import yfinance as yf

    raw = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
    if raw.empty:
        raise ValueError(f"no data returned for {symbol} ({period}, {interval})")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0] for c in raw.columns]
    return _normalize(raw)


def load_csv(path: str, tz: str | None = None) -> pd.DataFrame:
    """Load bar data exported from NinjaTrader / a data vendor. Expects a timestamp column plus OHLCV."""
    raw = pd.read_csv(path)
    ts_col = next((c for c in raw.columns if c.lower() in ("timestamp", "date", "datetime", "time")), raw.columns[0])
    raw = raw.set_index(ts_col)
    df = _normalize(raw)
    if tz:
        df.index = df.index.tz_localize(tz) if df.index.tz is None else df.index.tz_convert(tz)
    return df
