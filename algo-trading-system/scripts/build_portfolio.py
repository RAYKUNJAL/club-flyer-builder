"""Combine the out-of-sample-validated strategies into one portfolio view, with
law-of-large-numbers-honest win-rate statistics.

Why: no single config here trades often enough for its win rate to be a "solid"
number -- a 60% win rate on 30 trades has a 95% lower bound near 42%. Pooling the
trades of every config that PASSED the out-of-sample holdout multiplies the sample
size, which is the only legitimate way to a statistically supported win rate
(the law of large numbers tightens the estimate as N grows; it never raises the
true rate). Output: data/portfolio.json for the dashboard's portfolio card.

Run from the repo root, after scan_win_rates.py:
    python scripts/build_portfolio.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.backtest.scoring import wilson_lower  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def summarize(trades: list[dict]) -> dict:
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    gross_win = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))
    return {
        "num_trades": n,
        "wins": wins,
        "win_rate": wins / n if n else None,
        "win_rate_lower_95": wilson_lower(wins, n),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "total_pnl": sum(t["pnl"] for t in trades),
        "expectancy": (sum(t["pnl"] for t in trades) / n) if n else None,
    }


def family_stats(trials: list[dict]) -> list[dict]:
    """Pool win rates by strategy family across ALL trials (winners and losers alike --
    no selection conditioning), separately for the in-sample and out-of-sample segments.
    This is the cleanest law-of-large-numbers view: the OOS pool was never selected on,
    so its win rate is an honest estimate, and pooling every variant/symbol gives the
    sample size a single config can never have."""
    fams: dict[str, dict] = {}
    for t in trials:
        f = fams.setdefault(t["strategy"], {"is_n": 0, "is_w": 0, "oos_n": 0, "oos_w": 0, "variants": 0})
        f["variants"] += 1
        for seg in ("is", "oos"):
            m = t[seg]
            f[seg + "_n"] += m["num_trades"]
            f[seg + "_w"] += round(m["win_rate"] * m["num_trades"])
    out = []
    for name, f in fams.items():
        out.append({
            "family": name,
            "variants": f["variants"],
            "is_trades": f["is_n"],
            "is_win_rate": f["is_w"] / f["is_n"] if f["is_n"] else None,
            "oos_trades": f["oos_n"],
            "oos_win_rate": f["oos_w"] / f["oos_n"] if f["oos_n"] else None,
            "oos_win_rate_lower_95": wilson_lower(f["oos_w"], f["oos_n"]),
        })
    out.sort(key=lambda r: r["oos_win_rate_lower_95"], reverse=True)
    return out


def main() -> None:
    scan = json.loads((DATA_DIR / "win_rate_scan.json").read_text())
    passing = [e for e in scan if (e.get("validation") or {}).get("oos_pass")]
    if not passing:
        raise SystemExit("no OOS-passing configs in win_rate_scan.json -- run scan_win_rates.py first")

    configs = []
    pooled: list[dict] = []
    for e in passing:
        s = summarize(e["trades"])
        s.update({"strategy": e["strategy"], "symbol": e["symbol"], "timeframe": e["timeframe"],
                  "score": e.get("score")})
        configs.append(s)
        pooled.extend(e["trades"])

    pooled.sort(key=lambda t: t["exit_time"])
    combined = summarize(pooled)

    out = {
        "note": (
            "Pooled trades from every config that passed the untouched out-of-sample holdout. "
            "Win-rate lower bounds are 95% Wilson intervals: the honest, law-of-large-numbers "
            "reading of a win rate. Pooling grows the sample and tightens the bound -- it never "
            "inflates the underlying rate. Trades overlap in time across configs; this is a "
            "statistical pool, not a simulated margin-accurate multi-strategy account."
        ),
        "combined": combined,
        "configs": sorted(configs, key=lambda c: c["win_rate_lower_95"], reverse=True),
        "families": family_stats(json.loads((DATA_DIR / "scan_trials.json").read_text())),
    }
    (DATA_DIR / "portfolio.json").write_text(json.dumps(out, indent=2))

    print(f"{'config':44s} {'trades':>6s} {'win%':>6s} {'95% lower':>9s} {'PF':>6s}")
    for c in out["configs"]:
        label = f"{c['strategy']} {c['symbol']} {c['timeframe']}"
        pf = f"{c['profit_factor']:.2f}" if c["profit_factor"] else "inf"
        print(f"{label:44s} {c['num_trades']:6d} {c['win_rate']*100:5.1f}% {c['win_rate_lower_95']*100:8.1f}% {pf:>6s}")
    print("-" * 76)
    pf = f"{combined['profit_factor']:.2f}" if combined["profit_factor"] else "inf"
    print(f"{'COMBINED (pooled)':44s} {combined['num_trades']:6d} {combined['win_rate']*100:5.1f}% "
          f"{combined['win_rate_lower_95']*100:8.1f}% {pf:>6s}")
    print(f"\nwrote {DATA_DIR / 'portfolio.json'}")


if __name__ == "__main__":
    main()
