# Go-live gates

No real-money deployment until EVERY gate below passes. These are pre-committed so
they can't be argued with after a good week. Loosening a gate requires editing this
file in a commit of its own, with the reason in the commit message.

## Gate 1 — Statistical evidence (backtest layer)
- [ ] Every attempted configuration logged (`data/scan_trials.json`) — the trial count
      is part of the evidence; selection from N trials inflates the winner's stats.
- [ ] Candidate passes the untouched out-of-sample holdout (last 30%): OOS profit
      factor > 1.0 with trades present. (Scanner enforces + dashboard shows this.)
- [ ] Performance survives pessimistic costs: doubled slippage assumptions still
      leave expectancy positive.
- [ ] ≥ 300 sufficiently independent out-of-sample/forward trades accumulated across
      regimes before any capital decision. Two weeks of paper validates plumbing, not skill.

## Gate 2 — Paper validation (live layer)
- [ ] ≥ 60 trading days on the paper account (Alpaca paper preferred over in-memory).
- [ ] Kill criteria never triggered (`paper_tracker.py`): live drawdown within backtest
      max; live expectancy ≥ half of backtest after 30 trades.
- [ ] Live vs backtest slippage gap measured and folded back into the backtest costs.

## Gate 3 — Operational hardness
- [ ] 30 consecutive days without: crashes, duplicate orders, stale-feed incidents
      unhandled, or reconciliation mismatches.
- [ ] Restart drill passes: kill the runner mid-position; on restart it reconciles
      with the broker (adopts or flattens) with no orphaned position or stop.
- [ ] Stale-data drill passes: cut the data feed; runner flattens and halts.
- [ ] Broker-side protective stop verified resting on Alpaca's book for every entry.

## Gate 4 — Capital rules (when 1–3 pass)
- [ ] First live allocation is the smallest practical size (single-digit shares),
      regardless of paper results.
- [ ] Hard daily / weekly / account loss limits configured and tested.
- [ ] The live endpoint two-step (live=True + ALPACA_ALLOW_LIVE=1) stays out of all
      committed code; enabling it is a manual, deliberate act.

## Standing realism note
$50K → $1M requires ~82%/yr for 5 years or ~35%/yr for 10 — far beyond anything the
current evidence supports. The goal of these gates is not to promise those returns;
it is to make sure whatever edge exists is real, measured, and survives costs before
any money is exposed to it.
