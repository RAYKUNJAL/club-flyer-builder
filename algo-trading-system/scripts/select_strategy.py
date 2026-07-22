"""Select the strategy the paper trader will run -- from the FULL validated trial log,
not just the dashboard's top-8.

Default mode picks the config with the highest out-of-sample Wilson lower bound on win
rate (the law-of-large-numbers 'solid win rate' pick -- currently the RSI-2 family).
The chosen config is re-backtested on full history and written to
data/active_strategy.json with its metrics embedded, so the paper tracker has its
comparison baseline no matter how the config was chosen.

Usage (from repo root):
    python scripts/select_strategy.py                  # best win-rate lower bound (default)
    python scripts/select_strategy.py --best-score     # best in-sample composite score
    python scripts/select_strategy.py --strategy rsi2_pullback --symbol "Nasdaq ETF (QQQ)"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.backtest.engine import BacktestEngine  # noqa: E402
from algotrader.backtest.metrics import compute_metrics  # noqa: E402
from algotrader.backtest.scoring import composite_score, wilson_lower  # noqa: E402
from algotrader.data.loader import load_csv  # noqa: E402
from algotrader.risk.position_sizing import PositionSizer, RiskConfig  # noqa: E402
from algotrader.strategies.registry import build_strategy  # noqa: E402
from algotrader.webapp.volume_profile import SOURCE_FILES  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

LABELS = {
    "orb": "Opening Range Breakout", "fast_trend": "Fast Trend",
    "pulse": "Pulse (All-Session Trend)", "mean_reversion": "Mean Reversion",
    "swing_trend": "Swing Trend", "rsi2_pullback": "RSI-2 Pullback",
    "squeeze_breakout": "Squeeze Breakout", "vwap_reversion": "VWAP Reversion",
}


def pick_trial(trials: list[dict], mode: str = "best-win-rate",
               strategy: str | None = None, symbol: str | None = None,
               timeframe: str | None = None, min_oos_trades: int = 10) -> dict:
    """Pure selection logic. Only OOS-passing trials with a real OOS sample qualify."""
    pool = [t for t in trials if t.get("oos_pass") and t["oos"]["num_trades"] >= min_oos_trades]
    if strategy:
        pool = [t for t in pool if t["strategy"] == strategy]
    if symbol:
        pool = [t for t in pool if t["symbol"] == symbol]
    if timeframe:
        pool = [t for t in pool if t["timeframe"] == timeframe]
    if not pool:
        raise LookupError(
            "no OOS-passing trial matches the filters "
            f"(strategy={strategy}, symbol={symbol}, timeframe={timeframe}, "
            f"min_oos_trades={min_oos_trades})"
        )
    if mode == "best-score":
        return max(pool, key=lambda t: t["is_score"])
    # best-win-rate: highest 95% Wilson lower bound on the OOS win rate
    return max(pool, key=lambda t: wilson_lower(
        round(t["oos"]["win_rate"] * t["oos"]["num_trades"]), t["oos"]["num_trades"]
    ))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--best-score", action="store_true", help="pick by in-sample composite score instead")
    ap.add_argument("--strategy", help="restrict to one strategy family (e.g. rsi2_pullback)")
    ap.add_argument("--symbol", help='restrict to one symbol label (e.g. "S&P 500 ETF (SPY)")')
    ap.add_argument("--timeframe", choices=["1d", "5m"], help="restrict to one timeframe")
    args = ap.parse_args()

    trials = json.loads((DATA_DIR / "scan_trials.json").read_text())
    trial = pick_trial(
        trials, mode="best-score" if args.best_score else "best-win-rate",
        strategy=args.strategy, symbol=args.symbol, timeframe=args.timeframe,
    )

    fname = SOURCE_FILES[(trial["symbol"], trial["timeframe"])]
    data = load_csv(DATA_DIR / fname)
    strat = build_strategy(trial["strategy"], trial["params"])
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.02, point_value=1.0, max_contracts=2000))
    engine = BacktestEngine(
        data, strat, sizer, starting_equity=50_000.0, point_value=1.0,
        commission_per_contract=0.0, slippage_points=trial["slippage"],
    )
    m = compute_metrics(engine.run(), starting_equity=50_000.0)

    oos_w = round(trial["oos"]["win_rate"] * trial["oos"]["num_trades"])
    active = {
        "strategy": trial["strategy"],
        "label": LABELS.get(trial["strategy"], trial["strategy"]),
        "symbol": trial["symbol"],
        "timeframe": trial["timeframe"],
        "params": trial["params"],
        "score": composite_score(m.win_rate, m.profit_factor, m.sharpe, m.max_drawdown_pct),
        "metrics": {
            "num_trades": m.num_trades, "win_rate": m.win_rate, "profit_factor": m.profit_factor,
            "total_pnl": m.total_pnl, "total_return_pct": m.total_return_pct,
            "max_drawdown_pct": m.max_drawdown_pct, "sharpe": m.sharpe,
            "avg_win": m.avg_win, "avg_loss": m.avg_loss,
        },
        "validation": {
            "in_sample": trial["is"], "out_of_sample": trial["oos"], "oos_pass": trial["oos_pass"],
            "oos_win_rate_lower_95": wilson_lower(oos_w, trial["oos"]["num_trades"]),
        },
        "selected_by": "select_strategy.py " + ("--best-score" if args.best_score else "--best-win-rate"),
        "selected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (DATA_DIR / "active_strategy.json").write_text(json.dumps(active, indent=2))

    v = active["validation"]
    print(f"Selected: {active['label']} on {active['symbol']} ({active['timeframe']})")
    print(f"  params: {active['params']}")
    print(f"  full-history: {m.num_trades} trades, {m.win_rate:.1%} win rate, PF {m.profit_factor:.2f}, "
          f"return {m.total_return_pct:.1%}, maxDD {m.max_drawdown_pct:.1%}")
    print(f"  OOS holdout: {trial['oos']['num_trades']} trades, {trial['oos']['win_rate']:.1%} win rate "
          f"(95% lower bound {v['oos_win_rate_lower_95']:.1%}), PF {trial['oos']['profit_factor']:.2f}")
    print(f"\nwrote data/active_strategy.json -- start trading it with: python scripts/run_paper_trading.py")


if __name__ == "__main__":
    main()
