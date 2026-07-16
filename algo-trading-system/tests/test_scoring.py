from algotrader.backtest.scoring import composite_score


def test_score_in_unit_range():
    assert 0.0 <= composite_score(0.5, 1.5, 1.0, -0.1) <= 1.0
    assert composite_score(0.0, 0.0, -5.0, -0.9) == 0.0
    assert composite_score(1.0, 10.0, 10.0, 0.0) == 1.0


def test_high_win_rate_with_bad_pf_loses_to_balanced_config():
    # 70% win rate but PF below 1 (net loser) must rank below a 52% win rate with PF 3.
    lucky_coin = composite_score(0.70, 0.9, 0.1, -0.20)
    solid = composite_score(0.52, 3.0, 1.2, -0.10)
    assert solid > lucky_coin


def test_deep_drawdown_is_penalized():
    shallow = composite_score(0.55, 1.8, 1.0, -0.05)
    deep = composite_score(0.55, 1.8, 1.0, -0.40)
    assert shallow > deep


def test_profit_factor_clamped_against_overfit_outliers():
    # PF 3 and PF 30 score identically -- a 30x PF on few trades is noise, not skill.
    assert composite_score(0.5, 3.0, 1.0, -0.1) == composite_score(0.5, 30.0, 1.0, -0.1)
