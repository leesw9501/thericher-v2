# Runbook

## Modes

The engine supports three modes:

- `off`: collect data and run research only. No order placement.
- `paper`: KIS paper trading allowed within risk limits.
- `live`: live trading allowed only after explicit promotion and capital caps.

Default mode is `off`.

## Long Task Workflow

Start each long Codex task with:

```powershell
.\scripts\start_next_codex_task.ps1
```

Then read the required handoff and architecture files printed by the script.
Before changing architecture, promotion rules, or agent governance, ask Claude
CLI for a short drift-check and judge it against `HANDOFF.md`,
`ARCHITECTURE.md`, and `DECISIONS.md`.

Check `agents/README.md` for the current lane stateboards. Use the relevant
agent file for active queues, held resources, running jobs, and handoff notes.

Before ending a long task:

- run the relevant verification commands,
- commit and push completed work when changes are ready,
- refresh `NEXT_CODEX_GOAL.md` with the next single objective,
- keep the next goal tied to one engine loop.

When GPU research is active, keep bounded training and validation jobs running
on the single GPU by default. Other lanes may proceed while those jobs run, as
long as they do not touch the same ownership boundary or enable broker/live
behavior prematurely.

Bounded GPU research jobs run through Docker `research` and write artifacts to
the external model artifact mount:

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-training-smoke --kind candidate_training --candidate-artifact /app/model_artifacts/experiments/short-momentum-cpu-queue-walk-forward-gpu-candidate-smoke.json --max-bars 120 --max-epochs 8 --max-steps 256
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-evaluation-smoke --kind candidate_evaluation --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-training-smoke/metrics.json --max-bars 120
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-replay-smoke --kind candidate_replay --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-training-smoke/metrics.json --evaluation-artifact /app/model_artifacts/candidate-evaluation/bounded-candidate-evaluation-smoke/metrics.json --yahoo-snapshot /app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz --symbol CVS --max-bars 180 --buy-threshold 0.47 --sell-threshold 0.45
```

```powershell
uv run --extra dev thericher-v2-research-job --job-id bounded-candidate-replay-comparison-smoke --kind candidate_replay_comparison --candidate-replay-artifact D:\thericher-v2\model-artifacts\candidate-replay\bounded-candidate-replay-smoke\metrics.json --training-metrics-artifact D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-training-smoke\metrics.json --yahoo-snapshot D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0-8d-probe\ohlcv_1m.csv.gz --symbol CVS --max-bars 180 --buy-threshold 0.47 --sell-threshold 0.45
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-threshold-sweep-smoke --kind candidate_threshold_sweep --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-training-smoke/metrics.json --evaluation-artifact /app/model_artifacts/candidate-evaluation/bounded-candidate-evaluation-smoke/metrics.json --comparison-artifact /app/model_artifacts/candidate-replay-comparison/bounded-candidate-replay-comparison-smoke/metrics.json --yahoo-snapshot /app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz --symbol CVS --max-bars 180 --threshold-pair 0.47:0.455 --threshold-pair 0.50:0.455 --threshold-pair 0.52:0.455 --threshold-pair 0.55:0.455 --threshold-pair 0.60:0.455
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-threshold-robustness-smoke --kind candidate_threshold_robustness --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-training-smoke/metrics.json --evaluation-artifact /app/model_artifacts/candidate-evaluation/bounded-candidate-evaluation-smoke/metrics.json --max-bars 180 --threshold-pair 0.47:0.455 --threshold-pair 0.50:0.455 --threshold-pair 0.52:0.455 --threshold-pair 0.55:0.455 --threshold-pair 0.60:0.455 --robustness-slice cvs=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:CVS --robustness-slice fcx=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:FCX --robustness-slice ko=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:KO
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-multislice-training-smoke --kind candidate_training --candidate-artifact /app/model_artifacts/experiments/short-momentum-cpu-queue-walk-forward-gpu-candidate-smoke.json --max-bars 180 --max-epochs 8 --max-steps 256 --data-slice cvs=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:CVS --data-slice fcx=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:FCX --data-slice ko=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:KO
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-multislice-evaluation-smoke --kind candidate_evaluation --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-multislice-training-smoke/metrics.json --max-bars 180
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-multislice-calibration-smoke --kind candidate_threshold_calibration --training-metrics-artifact /app/model_artifacts/candidate-training/bounded-candidate-multislice-training-smoke/metrics.json --evaluation-artifact /app/model_artifacts/candidate-evaluation/bounded-candidate-multislice-evaluation-smoke/metrics.json --max-bars 180 --robustness-slice cvs=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:CVS --robustness-slice fcx=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:FCX --robustness-slice ko=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-07-09-shadow-t0-8d-probe/ohlcv_1m.csv.gz:KO
```

```powershell
docker compose --profile research run --rm --no-deps research thericher-v2-research-job --job-id bounded-candidate-calibration-holdout-smoke --kind candidate_threshold_holdout --calibration-artifact /app/model_artifacts/candidate-threshold-calibration/bounded-candidate-multislice-calibration-smoke/metrics.json --max-bars 180 --robustness-slice cvs_holdout=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:CVS --robustness-slice fcx_holdout=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:FCX --robustness-slice ko_holdout=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:KO
```

## Market Data Acquisition

Use `D:\market_data` as the default external market data root. Do not download
or copy acquired market data into the Git workspace.

Agents may acquire additional data only when it is available without
credentials, payment, login, private APIs, or unclear licensing. Stop acquisition
for a source when those limits are hit, when two automated attempts fail, or
when more data no longer improves the active engine loop.

If operator help is needed, record exact symbols, markets, date ranges, formats,
and blocker reasons in `agents/data.md` under `Operator Help Needed`. The daily
report surfaces that section.

## Emergency Stop

There are two independent emergency actions.

### Stop New Orders

Effect:

- prevents new orders,
- persists across engine restart,
- does not automatically cancel existing open orders.

Resume requires explicit local confirmation.

### Cancel Open Orders

Effect:

- asks the broker adapter to cancel currently open orders,
- logs every cancel request and result,
- does not resume new order placement.

This action is separate from stop-new-orders so the operator can choose whether
to freeze only new activity or also clear open orders.

## Live Promotion Draft Criteria

These are initial planning criteria and must be encoded in versioned config
before live mode exists.

- at least 20 paper trading days,
- at least 300 to 500 paper trades,
- positive expectancy after fees and slippage,
- positive expectancy under 2x cost stress,
- maximum drawdown within 6 to 8 percent,
- zero daily loss-limit violations,
- no dependence on one or two symbols for most profit,
- walk-forward and out-of-sample consistency,
- operator review approval before each capital ramp.

Daily return above 1 percent after costs is treated as a strong result but not a
promotion rule by itself. It can also signal overfitting or lucky regime
exposure.

## Daily Review

At 08:00 KST, the daily report should summarize:

- what changed,
- current mode,
- engine heartbeat,
- paper/live status,
- open risk events,
- model performance,
- trading metrics,
- market data root and operator data requests,
- blockers,
- next goal script.

One concise report bundle per day is preferred.

## Dashboard Minimum

The dashboard shows:

- mode,
- heartbeat,
- KIS connectivity,
- cash and equity by currency,
- holdings,
- open orders,
- recent fills and rejects,
- model signals,
- ensemble action,
- confidence,
- expected edge,
- risk score,
- stop-new-orders state,
- cancel-open-orders action status.

The dashboard must not show secrets, raw KIS payloads, or unrestricted order
controls.
