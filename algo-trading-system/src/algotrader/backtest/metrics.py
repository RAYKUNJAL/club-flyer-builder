"""Performance metrics computed from a BacktestResult."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import BacktestResult


@dataclass
class Metrics:
    num_trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    avg_win: float
    avg_loss: float

    def __str__(self) -> str:
        return (
            f"trades={self.num_trades} win_rate={self.win_rate:.1%} "
            f"profit_factor={self.profit_factor:.2f} total_pnl=${self.total_pnl:,.2f} "
            f"total_return={self.total_return_pct:.1%} max_drawdown={self.max_drawdown_pct:.1%} "
            f"sharpe={self.sharpe:.2f} avg_win=${self.avg_win:,.2f} avg_loss=${self.avg_loss:,.2f}"
        )


def compute_metrics(result: BacktestResult, starting_equity: float) -> Metrics:
    trades = result.trades
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    num_trades = len(trades)
    win_rate = len(wins) / num_trades if num_trades else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    total_pnl = sum(pnls)
    total_return_pct = total_pnl / starting_equity if starting_equity else 0.0

    equity = result.equity_curve
    if len(equity) > 1:
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown_pct = float(drawdown.min())
        daily = equity.resample("1D").last().dropna()
        returns = daily.pct_change().dropna()
        sharpe = float(returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
    else:
        max_drawdown_pct = 0.0
        sharpe = 0.0

    avg_win = (gross_win / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0

    return Metrics(
        num_trades=num_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        total_pnl=total_pnl,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe=sharpe,
        avg_win=avg_win,
        avg_loss=avg_loss,
    )
