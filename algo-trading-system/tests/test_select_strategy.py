import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from select_strategy import pick_trial  # noqa: E402


def _trial(strategy, symbol, oos_n, oos_wr, oos_pf, is_score, oos_pass=True, tf="1d"):
    return {
        "strategy": strategy, "symbol": symbol, "timeframe": tf,
        "params": {}, "slippage": 0.02, "is_score": is_score, "oos_pass": oos_pass,
        "is": {"num_trades": 100, "win_rate": 0.5, "profit_factor": 1.5},
        "oos": {"num_trades": oos_n, "win_rate": oos_wr, "profit_factor": oos_pf},
    }


TRIALS = [
    _trial("rsi2_pullback", "S&P 500 ETF (SPY)", 200, 0.75, 2.48, 0.57),
    _trial("rsi2_pullback", "Nasdaq ETF (QQQ)", 10, 0.90, 5.0, 0.55),   # higher rate, tiny sample
    _trial("swing_trend", "Tesla (TSLA)", 23, 0.43, 1.80, 0.66),
    _trial("vwap_reversion", "S&P 500 ETF (SPY)", 20, 0.60, 0.75, 0.65, oos_pass=False),
]


def test_best_win_rate_uses_lower_bound_not_raw_rate():
    # 90% on 10 trades (lower bound ~60%) loses to 75% on 200 trades (lower bound
    # ~68%) -- the law-of-large-numbers pick must be the big-sample config.
    t = pick_trial(TRIALS, mode="best-win-rate")
    assert t["symbol"] == "S&P 500 ETF (SPY)" and t["strategy"] == "rsi2_pullback"


def test_oos_failures_are_never_selectable():
    t = pick_trial(TRIALS, mode="best-win-rate", symbol="S&P 500 ETF (SPY)")
    assert t["strategy"] != "vwap_reversion"


def test_best_score_mode_picks_highest_is_score():
    assert pick_trial(TRIALS, mode="best-score")["strategy"] == "swing_trend"


def test_min_oos_trades_floor():
    with pytest.raises(LookupError):
        pick_trial(TRIALS, strategy="rsi2_pullback", symbol="Nasdaq ETF (QQQ)", min_oos_trades=20)


def test_no_match_raises_with_filters_in_message():
    with pytest.raises(LookupError, match="nonexistent"):
        pick_trial(TRIALS, strategy="nonexistent")
