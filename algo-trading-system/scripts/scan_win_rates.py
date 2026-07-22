"""Grid-scan every strategy archetype x parameter variants x real market data -- with
honest validation.

Universe: Alpaca-tradable US equities/ETFs (GLD, SPY, QQQ, TSLA) at zero commission
and penny-scale slippage. (Alpaca does not support futures; the old futures CSVs stay
in data/ for reference but are no longer scanned.)

Anti-overfitting design (the part that keeps this from lying to you):
  * Each dataset is split 70/30 chronologically: configs are ranked ONLY on the
    in-sample (first 70%) composite score; the untouched out-of-sample tail is then
    reported next to it. An edge that exists only in-sample is curve-fit, not real.
  * EVERY attempted configuration is logged to data/scan_trials.json with its IS and
    OOS results -- selection from many trials inflates the winners' stats (probability
    of backtest overfitting; Bailey & Lopez de Prado), so the trial count and the
    losers must stay visible.
  * A minimum trade-count floor keeps 2-trade wonders off the board, and the top-8
    payload marks each config's OOS verdict so the dashboard can show it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from algotrader.backtest.engine import BacktestEngine  # noqa: E402
from algotrader.backtest.metrics import compute_metrics  # noqa: E402
from algotrader.backtest.scoring import composite_score  # noqa: E402
from algotrader.data.loader import load_csv  # noqa: E402
from algotrader.risk.position_sizing import PositionSizer, RiskConfig  # noqa: E402
from algotrader.strategies.fast_trend import FastTrend  # noqa: E402
from algotrader.strategies.mean_reversion import MeanReversion  # noqa: E402
from algotrader.strategies.orb import OpeningRangeBreakout  # noqa: E402
from algotrader.strategies.pulse import Pulse  # noqa: E402
from algotrader.strategies.rsi2_pullback import Rsi2Pullback  # noqa: E402
from algotrader.strategies.squeeze_breakout import SqueezeBreakout  # noqa: E402
from algotrader.strategies.swing_trend import SwingTrend  # noqa: E402
from algotrader.strategies.vwap_reversion import VwapReversion  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MIN_TRADES = 8
IS_FRACTION = 0.70  # chronological in-sample share; the last 30% is the holdout

# Alpaca-tradable universe. point_value = 1.0 (shares), zero commission, penny slippage.
DAILY_SOURCES = [
    ("GLD_daily.csv", "Gold ETF (GLD)"),
    ("SPY_daily.csv", "S&P 500 ETF (SPY)"),
    ("QQQ_daily.csv", "Nasdaq ETF (QQQ)"),
    ("TSLA_daily.csv", "Tesla (TSLA)"),
]
INTRADAY_SOURCES = [
    ("SPY_5min_rth.csv", "S&P 500 ETF (SPY)"),
    ("QQQ_5min_rth.csv", "Nasdaq ETF (QQQ)"),
    ("TSLA_5min_rth.csv", "Tesla (TSLA)"),
]

POINT_VALUE = 1.0
MAX_SHARES = 2000
COMMISSION = 0.0          # Alpaca equities are commission-free
SLIPPAGE_DAILY = 0.02     # $/share -- conservative for liquid ETFs at daily horizon
SLIPPAGE_5M = 0.01

# ATR/std-based strategies are price-scale-free and keep fixed params.
SWING_VARIANTS = [
    {"entry_period": 55, "exit_period": 20, "atr_period": 20, "atr_stop_mult": 3.0},
    {"entry_period": 20, "exit_period": 10, "atr_period": 14, "atr_stop_mult": 2.5},
    {"entry_period": 40, "exit_period": 15, "atr_period": 20, "atr_stop_mult": 3.0},
]
MEANREV_VARIANTS = [
    {"band_period": 20, "band_std": 2.0, "stop_std": 3.0},
    {"band_period": 14, "band_std": 1.5, "stop_std": 2.5},
    {"band_period": 10, "band_std": 2.5, "stop_std": 3.5},
]
RSI2_VARIANTS = [
    {"rsi_period": 2, "oversold": 10.0, "trend_period": 200, "exit_ma_period": 5, "max_hold_bars": 10, "stop_atr_mult": 3.0},
    {"rsi_period": 2, "oversold": 25.0, "trend_period": 100, "exit_ma_period": 5, "max_hold_bars": 8, "stop_atr_mult": 3.0},
    {"rsi_period": 4, "oversold": 20.0, "trend_period": 150, "exit_ma_period": 10, "max_hold_bars": 12, "stop_atr_mult": 2.5},
]
SQUEEZE_VARIANTS = [
    {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.5, "min_squeeze_bars": 5, "stop_atr_mult": 2.0, "trail_atr_mult": 2.5},
    {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_atr_mult": 1.2, "min_squeeze_bars": 3, "stop_atr_mult": 1.5, "trail_atr_mult": 2.0},
    {"bb_period": 14, "bb_std": 1.8, "kc_period": 14, "kc_atr_mult": 1.5, "min_squeeze_bars": 6, "stop_atr_mult": 2.5, "trail_atr_mult": 3.0},
]
PULSE_VARIANTS = [
    {"fast_period": 9, "slow_period": 21, "atr_period": 14, "trail_atr_mult": 2.0, "min_spread_atr_mult": 0.15},
    {"fast_period": 5, "slow_period": 13, "atr_period": 10, "trail_atr_mult": 1.5, "min_spread_atr_mult": 0.1},
    {"fast_period": 12, "slow_period": 26, "atr_period": 14, "trail_atr_mult": 2.5, "min_spread_atr_mult": 0.2},
]
VWAP_VARIANTS = [
    {"entry_dev": 2.0, "stop_dev": 3.5, "dev_period": 30, "warmup_bars": 30, "max_hold_bars": 60},
    {"entry_dev": 2.5, "stop_dev": 4.0, "dev_period": 24, "warmup_bars": 24, "max_hold_bars": 48},
    {"entry_dev": 1.5, "stop_dev": 3.0, "dev_period": 36, "warmup_bars": 36, "max_hold_bars": 36},
]


def fasttrend_variants_for(price: float) -> list[dict]:
    """FastTrend's thresholds are absolute price points; scale them off the instrument's
    price so 'momentum' means comparable %-moves on a $600 SPY and a $60 name."""
    out = []
    for thr_pct, hold in [(0.0015, 30), (0.0025, 45), (0.0035, 20)]:
        thr = round(price * thr_pct, 2)
        out.append({
            "drive_minutes": 5 if hold != 45 else 10,
            "momentum_threshold_points": thr,
            "target_points": round(thr * 1.5, 2),
            "stop_points": round(thr * 0.75, 2),
            "max_hold_minutes": hold,
        })
    return out


def orb_variants_for(price: float) -> list[dict]:
    max_risk = round(price * 0.01, 2)  # cap risk per share at ~1% of price
    return [
        {"range_minutes": 15, "atr_period": 14, "atr_stop_mult": 1.5, "reward_risk": 2.0, "max_risk_points": max_risk},
        {"range_minutes": 30, "atr_period": 14, "atr_stop_mult": 1.5, "reward_risk": 2.0, "max_risk_points": max_risk},
        {"range_minutes": 30, "atr_period": 14, "atr_stop_mult": 1.0, "reward_risk": 1.5, "max_risk_points": round(max_risk * 0.6, 2)},
    ]


def run_one(strategy, data, slippage, equity=50_000.0, risk_pct=0.02):
    sizer = PositionSizer(RiskConfig(
        risk_per_trade_pct=risk_pct, point_value=POINT_VALUE, max_contracts=MAX_SHARES,
    ))
    engine = BacktestEngine(
        data, strategy, sizer, starting_equity=equity, point_value=POINT_VALUE,
        commission_per_contract=COMMISSION, slippage_points=slippage,
    )
    result = engine.run()
    return result, compute_metrics(result, starting_equity=equity)


def metrics_dict(m) -> dict:
    return {
        "num_trades": m.num_trades, "win_rate": m.win_rate, "profit_factor": m.profit_factor,
        "total_pnl": m.total_pnl, "total_return_pct": m.total_return_pct,
        "max_drawdown_pct": m.max_drawdown_pct, "sharpe": m.sharpe,
        "avg_win": m.avg_win, "avg_loss": m.avg_loss,
    }


def score_of(m) -> float:
    return composite_score(m.win_rate, m.profit_factor, m.sharpe, m.max_drawdown_pct)


def main():
    strategy_grid_daily = [
        ("swing_trend", SwingTrend, SWING_VARIANTS),
        ("mean_reversion", MeanReversion, MEANREV_VARIANTS),
        ("rsi2_pullback", Rsi2Pullback, RSI2_VARIANTS),
        ("squeeze_breakout", SqueezeBreakout, SQUEEZE_VARIANTS),
    ]

    trials = []
    for sources, tf, slippage, grid_builder in [
        (DAILY_SOURCES, "1d", SLIPPAGE_DAILY, lambda price: strategy_grid_daily),
        (INTRADAY_SOURCES, "5m", SLIPPAGE_5M, lambda price: [
            ("orb", OpeningRangeBreakout, orb_variants_for(price)),
            ("fast_trend", FastTrend, fasttrend_variants_for(price)),
            ("pulse", Pulse, PULSE_VARIANTS),
            ("vwap_reversion", VwapReversion, VWAP_VARIANTS),
            ("squeeze_breakout", SqueezeBreakout, SQUEEZE_VARIANTS),
        ]),
    ]:
        for fname, label in sources:
            if not (DATA_DIR / fname).exists():
                print(f"skip {label} {tf}: {fname} missing")
                continue
            data = load_csv(DATA_DIR / fname)
            split = int(len(data) * IS_FRACTION)
            is_data, oos_data = data.iloc[:split], data.iloc[split:]
            price = float(data["close"].median())
            for strat_name, cls, variants in grid_builder(price):
                for params in variants:
                    _, m_is = run_one(cls(**params), is_data, slippage)
                    _, m_oos = run_one(cls(**params), oos_data, slippage)
                    trials.append({
                        "strategy": strat_name, "symbol": label, "timeframe": tf,
                        "params": params, "slippage": slippage,
                        "is": metrics_dict(m_is), "oos": metrics_dict(m_oos),
                        "is_score": score_of(m_is),
                        "oos_pass": bool(m_oos.num_trades > 0 and m_oos.profit_factor > 1.0),
                        "_m_is": m_is,
                    })

    # Log EVERY trial -- selection bias is only measurable if the losers stay visible.
    trials_path = DATA_DIR / "scan_trials.json"
    trials_path.write_text(json.dumps(
        [{k: v for k, v in t.items() if not k.startswith("_")} for t in trials], indent=2
    ))

    qualified = [t for t in trials if t["is"]["num_trades"] >= MIN_TRADES]
    qualified.sort(key=lambda t: t["is_score"], reverse=True)

    print(f"{len(trials)} configurations tried ({len(qualified)} with >= {MIN_TRADES} in-sample trades) "
          f"-- all logged to {trials_path.name}")
    print(f"{'strategy':16s} {'symbol':18s} {'tf':4s} {'IS score':>8s} {'IS trades':>9s} {'IS PF':>6s} "
          f"{'OOS trades':>10s} {'OOS PF':>7s} {'OOS?':>5s}")
    for t in qualified[:20]:
        print(f"{t['strategy']:16s} {t['symbol']:18s} {t['timeframe']:4s} {t['is_score']:8.3f} "
              f"{t['is']['num_trades']:9d} {t['is']['profit_factor']:6.2f} "
              f"{t['oos']['num_trades']:10d} {t['oos']['profit_factor']:7.2f} "
              f"{'pass' if t['oos_pass'] else 'FAIL':>5s}")

    # Dashboard payload: top 8 by IN-SAMPLE score, each re-run on the full history for
    # display curves, with the IS/OOS validation verdict attached and visible.
    top = qualified[:8]
    payload = []
    for t in top:
        cls = {"swing_trend": SwingTrend, "mean_reversion": MeanReversion,
               "rsi2_pullback": Rsi2Pullback, "squeeze_breakout": SqueezeBreakout,
               "orb": OpeningRangeBreakout, "fast_trend": FastTrend,
               "pulse": Pulse, "vwap_reversion": VwapReversion}[t["strategy"]]
        fname = next(f for f, lbl in (DAILY_SOURCES + INTRADAY_SOURCES)
                     if lbl == t["symbol"] and ((t["timeframe"] == "1d") == ("daily" in f)))
        data = load_csv(DATA_DIR / fname)
        result, m_full = run_one(cls(**t["params"]), data, t["slippage"])
        payload.append({
            "strategy": t["strategy"], "symbol": t["symbol"], "timeframe": t["timeframe"],
            "params": t["params"],
            "score": t["is_score"],
            "validation": {
                "in_sample": t["is"], "out_of_sample": t["oos"], "oos_pass": t["oos_pass"],
                "note": f"ranked on first {IS_FRACTION:.0%} of history; last {1-IS_FRACTION:.0%} untouched holdout",
                "trials_total": len(trials),
            },
            "metrics": metrics_dict(m_full),
            "equity_curve": [{"t": str(ts), "equity": float(v)} for ts, v in result.equity_curve.items()],
            "trades": [
                {"side": tr.side, "entry_time": str(tr.entry_time), "exit_time": str(tr.exit_time),
                 "entry_price": tr.entry_price, "exit_price": tr.exit_price, "contracts": tr.contracts,
                 "pnl": tr.pnl, "entry_reason": tr.entry_reason, "exit_reason": tr.exit_reason}
                for tr in result.trades
            ],
        })

    out_path = DATA_DIR / "win_rate_scan.json"
    out_path.write_text(json.dumps(payload, indent=2))
    oos_passes = sum(1 for t in top if t["oos_pass"])
    print(f"\nwrote top {len(payload)} configs to {out_path.name} "
          f"({oos_passes}/{len(top)} passed the out-of-sample holdout)")


if __name__ == "__main__":
    main()
