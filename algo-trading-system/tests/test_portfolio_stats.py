import sys
from pathlib import Path

from algotrader.backtest.scoring import wilson_lower

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_portfolio import family_stats, summarize  # noqa: E402


def test_wilson_lower_shrinks_with_small_samples():
    # Same 60% win rate: 10 trades is weak evidence, 200 is solid.
    small = wilson_lower(6, 10)
    large = wilson_lower(120, 200)
    assert small < 0.35
    assert large > 0.52
    assert large > small


def test_wilson_lower_edge_cases():
    assert wilson_lower(0, 0) == 0.0
    assert wilson_lower(0, 50) == 0.0
    assert 0.9 < wilson_lower(100, 100) < 1.0  # perfect record still has uncertainty


def test_summarize_pools_trades():
    trades = [{"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 80.0}, {"pnl": -30.0}]
    s = summarize(trades)
    assert s["num_trades"] == 4 and s["wins"] == 2
    assert s["win_rate"] == 0.5
    assert s["profit_factor"] == 180.0 / 80.0
    assert 0 < s["win_rate_lower_95"] < 0.5


def test_family_stats_pools_all_variants_unconditionally():
    trials = [
        {"strategy": "a", "is": {"num_trades": 100, "win_rate": 0.7}, "oos": {"num_trades": 50, "win_rate": 0.6}},
        {"strategy": "a", "is": {"num_trades": 100, "win_rate": 0.5}, "oos": {"num_trades": 50, "win_rate": 0.4}},
        {"strategy": "b", "is": {"num_trades": 10, "win_rate": 0.9}, "oos": {"num_trades": 5, "win_rate": 0.2}},
    ]
    fams = {f["family"]: f for f in family_stats(trials)}
    a = fams["a"]
    assert a["variants"] == 2
    assert a["is_trades"] == 200 and a["is_win_rate"] == 0.6   # (70+50)/200
    assert a["oos_trades"] == 100 and a["oos_win_rate"] == 0.5  # (30+20)/100
    # ranking is by OOS lower bound: family a (100 OOS trades) must outrank tiny-sample b
    ranked = family_stats(trials)
    assert ranked[0]["family"] == "a"
