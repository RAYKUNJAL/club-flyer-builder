"""Paper-trading validation tracker: log every live/paper trade and continuously
compare live performance against the strategy's backtest, with pre-committed
kill criteria.

The point of the paper-trading phase is to answer one question honestly: does
the strategy behave live the way the backtest said it would? This module makes
that comparison automatic and puts the decision rules in code *before* any
results exist, so they can't be rationalized away later:

Kill criteria (evaluated by `summary()`):
  1. Drawdown breach -- live max drawdown (in dollars, vs starting equity)
     exceeds the backtest's max drawdown. The backtest already saw the worst
     of a decade; going deeper live means the live edge is not the tested one.
  2. Expectancy collapse -- after MIN_TRADES_TO_JUDGE trades, live expectancy
     ($/trade) is below half the backtest's. Half, not equal, because live
     friction is expected; below half means the edge isn't surviving contact.

Below MIN_TRADES_TO_JUDGE trades the status is "insufficient_data" -- judging a
strategy on a handful of trades is coin-flip reading, in either direction.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MIN_TRADES_TO_JUDGE = 30


class PaperTracker:
    def __init__(self, path: Path, starting_equity: float = 50_000.0):
        self.path = Path(path)
        self.starting_equity = starting_equity
        self.trades: list[dict] = []
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            self.trades = saved.get("trades", [])
            self.starting_equity = saved.get("starting_equity", starting_equity)

    def record(self, trade: dict) -> None:
        """Append one closed trade: side, entry_time, exit_time, entry_price,
        exit_price, contracts, pnl, entry_reason, exit_reason."""
        trade = dict(trade)
        trade.setdefault("recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.trades.append(trade)
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"starting_equity": self.starting_equity, "trades": self.trades}, indent=2
        ))

    def live_metrics(self) -> dict:
        n = len(self.trades)
        if n == 0:
            return {"num_trades": 0, "win_rate": None, "profit_factor": None,
                    "expectancy": None, "total_pnl": 0.0, "max_drawdown_pct": 0.0}
        pnls = [t["pnl"] for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        equity = self.starting_equity
        peak = equity
        max_dd = 0.0
        for p in pnls:
            equity += p
            peak = max(peak, equity)
            max_dd = min(max_dd, (equity - peak) / peak)
        return {
            "num_trades": n,
            "win_rate": len(wins) / n,
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            "expectancy": sum(pnls) / n,
            "total_pnl": sum(pnls),
            "max_drawdown_pct": max_dd,
        }

    def summary(self, backtest_metrics: dict | None = None) -> dict:
        """Live metrics plus, when backtest metrics are supplied, the side-by-side
        comparison and kill-criteria verdict."""
        live = self.live_metrics()
        out: dict = {"live": live, "min_trades_to_judge": MIN_TRADES_TO_JUDGE}
        if not backtest_metrics:
            out["status"] = "no_backtest_baseline"
            return out

        bt_expectancy = (
            backtest_metrics["total_pnl"] / backtest_metrics["num_trades"]
            if backtest_metrics.get("num_trades") else None
        )
        out["backtest"] = {
            "num_trades": backtest_metrics.get("num_trades"),
            "win_rate": backtest_metrics.get("win_rate"),
            "profit_factor": backtest_metrics.get("profit_factor"),
            "expectancy": bt_expectancy,
            "max_drawdown_pct": backtest_metrics.get("max_drawdown_pct"),
        }

        violations = []
        bt_dd = backtest_metrics.get("max_drawdown_pct")
        if bt_dd is not None and live["max_drawdown_pct"] < bt_dd:
            violations.append(
                f"drawdown breach: live {live['max_drawdown_pct']:.1%} exceeds backtest {bt_dd:.1%}"
            )
        judged = live["num_trades"] >= MIN_TRADES_TO_JUDGE
        if judged and bt_expectancy and bt_expectancy > 0 and live["expectancy"] is not None:
            if live["expectancy"] < 0.5 * bt_expectancy:
                violations.append(
                    f"expectancy collapse: live ${live['expectancy']:.0f}/trade is below half "
                    f"the backtest's ${bt_expectancy:.0f}/trade after {live['num_trades']} trades"
                )

        if violations:
            out["status"] = "kill"
        elif not judged:
            out["status"] = "insufficient_data"
        else:
            out["status"] = "healthy"
        out["violations"] = violations
        return out
