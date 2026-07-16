"""Fetch the latest 13F holdings for the famous-manager list from SEC EDGAR and
write data/top_traders.json for the dashboard's Top Traders leaderboard.

Run from the repo root:
    python scripts/fetch_top_traders.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.public_data.edgar13f import write_snapshot_file  # noqa: E402


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "data" / "top_traders.json"
    data = write_snapshot_file(out)
    print(f"{'fund':28s} {'manager':26s} {'filed':>10s} {'positions':>9s} {'value':>16s}")
    for f in data["funds"]:
        print(
            f"{f['fund'][:28]:28s} {f['manager'][:26]:26s} {f['filing_date']:>10s} "
            f"{f['num_positions']:9d} ${f['total_value']:>14,.0f}"
        )
    for e in data["errors"]:
        print(f"FAILED: {e['fund']} (CIK {e['cik']}): {e['error']}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
