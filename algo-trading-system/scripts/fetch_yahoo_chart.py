"""Fetch OHLCV bars straight from Yahoo's chart API with plain `requests` and write a CSV
`algotrader.data.loader.load_csv` can read.

Exists as a fallback to yfinance: yfinance's curl_cffi-based browser TLS impersonation gets
blocked by some corporate TLS-inspecting proxies (connection resets) even though a plain
`requests` call with a normal browser User-Agent header goes through fine.

Usage:
    python scripts/fetch_yahoo_chart.py NQ=F --range 60d --interval 5m --out data/NQ_5min.csv
    python scripts/fetch_yahoo_chart.py GC=F --range 10y --interval 1d --out data/GC_daily.csv
"""
from __future__ import annotations

import argparse

import pandas as pd
import requests

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_chart(symbol: str, range_: str, interval: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = requests.get(url, params={"range": range_, "interval": interval}, headers=BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload["chart"].get("error"):
        raise RuntimeError(f"Yahoo chart API error: {payload['chart']['error']}")
    result = payload["chart"]["result"]
    if not result:
        raise ValueError(f"no data returned for {symbol} ({range_}, {interval})")

    res = result[0]
    quote = res["indicators"]["quote"][0]
    tz = res.get("meta", {}).get("exchangeTimezoneName", "America/New_York")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None)
    df = pd.DataFrame(
        {
            "timestamp": idx,
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "volume": quote["volume"],
        }
    ).dropna()
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Yahoo ticker, e.g. NQ=F, ES=F, GC=F, TSLA")
    parser.add_argument("--range", dest="range_", default="1y")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--rth-only",
        action="store_true",
        help="filter to 09:30-16:00 (regular trading hours) -- required for the session-aware "
        "intraday strategies (orb, fast_trend, pulse), which assume RTH-only bars",
    )
    args = parser.parse_args()

    df = fetch_chart(args.symbol, args.range_, args.interval)
    if args.rth_only:
        df = df.set_index("timestamp").between_time("09:30", "16:00").reset_index()
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} bars ({df['timestamp'].min()} -> {df['timestamp'].max()}) to {args.out}")


if __name__ == "__main__":
    main()
