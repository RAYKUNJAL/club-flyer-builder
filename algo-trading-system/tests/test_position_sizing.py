import math

from algotrader.risk.position_sizing import PositionSizer, RiskConfig


def test_sizes_by_risk_percent_and_stop_distance():
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=20, max_contracts=10))
    # equity=100k, risk 1% = $1000. Stop distance 10 points * $20/pt = $200 risk/contract -> 5 contracts.
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=14990) == 5


def test_caps_at_max_contracts():
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.5, point_value=20, max_contracts=3))
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=14999) == 3


def test_zero_stop_distance_sizes_zero():
    sizer = PositionSizer(RiskConfig(point_value=20))
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=15000) == 0


def test_nan_stop_sizes_zero_instead_of_raising():
    sizer = PositionSizer(RiskConfig(point_value=20))
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=math.nan) == 0
    assert sizer.size(equity=100_000, entry_price=math.nan, stop_price=14990) == 0
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=None) == 0


def test_costs_per_contract_shrink_size_so_stop_out_stays_within_risk():
    sizer = PositionSizer(RiskConfig(risk_per_trade_pct=0.01, point_value=20, max_contracts=10))
    # $1000 risk budget; 10 pts * $20 = $200/contract, plus $50 costs -> $250 -> 4 contracts.
    assert sizer.size(equity=100_000, entry_price=15000, stop_price=14990, costs_per_contract=50.0) == 4


def test_daily_loss_cap():
    sizer = PositionSizer(RiskConfig(daily_loss_cap_pct=0.03))
    assert sizer.daily_loss_limit_hit(equity_at_day_start=100_000, current_equity=96_000) is True
    assert sizer.daily_loss_limit_hit(equity_at_day_start=100_000, current_equity=98_000) is False
