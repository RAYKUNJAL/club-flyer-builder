from algotrader.live.paper_tracker import MIN_TRADES_TO_JUDGE, PaperTracker


def _trade(pnl):
    return {"side": "long", "entry_time": "t0", "exit_time": "t1", "entry_price": 100.0,
            "exit_price": 101.0, "contracts": 1, "pnl": pnl,
            "entry_reason": "test", "exit_reason": "target_hit"}


BACKTEST = {"num_trades": 50, "win_rate": 0.6, "profit_factor": 2.0,
            "total_pnl": 10_000.0, "max_drawdown_pct": -0.10}


def test_persists_and_reloads_trades(tmp_path):
    path = tmp_path / "paper.json"
    t1 = PaperTracker(path)
    t1.record(_trade(100.0))
    t2 = PaperTracker(path)
    assert len(t2.trades) == 1
    assert t2.trades[0]["pnl"] == 100.0


def test_insufficient_data_before_min_trades(tmp_path):
    t = PaperTracker(tmp_path / "p.json")
    for _ in range(5):
        t.record(_trade(50.0))
    s = t.summary(BACKTEST)
    assert s["status"] == "insufficient_data"
    assert s["violations"] == []


def test_healthy_when_live_matches_backtest(tmp_path):
    t = PaperTracker(tmp_path / "p.json")
    # backtest expectancy is $200/trade; live at $180 is fine
    for _ in range(MIN_TRADES_TO_JUDGE):
        t.record(_trade(180.0))
    s = t.summary(BACKTEST)
    assert s["status"] == "healthy"


def test_kill_on_expectancy_collapse(tmp_path):
    t = PaperTracker(tmp_path / "p.json")
    # live expectancy ~$50/trade vs backtest $200 -> below half -> kill
    for _ in range(MIN_TRADES_TO_JUDGE):
        t.record(_trade(50.0))
    s = t.summary(BACKTEST)
    assert s["status"] == "kill"
    assert any("expectancy" in v for v in s["violations"])


def test_kill_on_drawdown_breach_even_with_few_trades(tmp_path):
    t = PaperTracker(tmp_path / "p.json", starting_equity=50_000.0)
    # -12% drawdown from the start vs backtest max of -10% -> kill immediately
    for _ in range(3):
        t.record(_trade(-2_000.0))
    s = t.summary(BACKTEST)
    assert s["status"] == "kill"
    assert any("drawdown" in v for v in s["violations"])


def test_live_metrics_math(tmp_path):
    t = PaperTracker(tmp_path / "p.json")
    for pnl in [100.0, -50.0, 200.0, -50.0]:
        t.record(_trade(pnl))
    m = t.live_metrics()
    assert m["num_trades"] == 4
    assert m["win_rate"] == 0.5
    assert m["profit_factor"] == 3.0  # 300 gross win / 100 gross loss
    assert m["total_pnl"] == 200.0
