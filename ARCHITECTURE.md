# Architecture

## Core Pipeline

```text
market data -> features -> models -> ensemble -> sizing -> risk -> broker -> state
                                                        -> dashboard
                                                        -> daily review
```

## Modules

```text
data/        intraday bars, calendars, data quality, cache
features/    indicators, chart patterns, volume, volatility, regime inputs
models/      rule, statistical, ML, and DL model implementations
ensemble/    signal combination, confidence, expected edge, disagreement
backtest/    event simulation, walk-forward, costs, slippage, attribution
execution/   KIS paper/live adapters, order lifecycle, risk limits
state/       SQLite plus append-only JSONL event log
dashboard/   read-focused monitor plus emergency controls
ops/         daily reports, next-goal scripts, scheduled maintenance
```

## Timeframe Policy

Default production policy is hierarchical, not free-form weighted blending.

- 1h and 3h: regime and direction filter.
- 10m: confirmation and trend stability.
- 1m and 5m: entry and exit timing.

Research may test alternative ensemble methods, but production promotion must
show why the combination is stable, interpretable, and robust out of sample.

## Model Policy

The research lane may explore many model families:

- technical rule models,
- random parameter sweeps,
- CNN/LSTM/Transformer-style models,
- modern time-series models,
- meta-labeling and probability calibration,
- regime classifiers,
- exit and stop models,
- risk and trade quality classifiers.

The real-time trading loop must remain deterministic at the execution boundary.
Deep-learning models may contribute signals only after they are versioned,
reproducible, and logged with their feature window, model artifact id, and
confidence output.

## Model Artifact Storage

GPU research can create large model artifacts. Keep them outside the Git
workspace by default.

Default host path:

```text
D:\thericher-v2\model-artifacts
```

Docker research path:

```text
/app/model_artifacts
```

Use `THERICHER_HOST_MODEL_ARTIFACT_ROOT` for the host mount and
`THERICHER_MODEL_ARTIFACT_ROOT` for the in-container path. The base engine image
must not require these heavy artifacts for tests or startup.

## State Policy

Use one SQLite database plus append-only JSONL logs.

SQLite stores current and queryable state:

- bars,
- features,
- model predictions,
- ensemble decisions,
- orders,
- fills,
- positions,
- portfolio snapshots,
- risk events,
- emergency stop state.

JSONL stores immutable events for replay and daily review.

## Safety Minimum

Paper trading should be easy to repeat. Live trading should be hard to enable.

Hard stops:

- live mode not explicitly enabled,
- emergency stop active,
- duplicate client order id,
- open order conflict,
- position or daily loss limit exceeded,
- missing broker account mode,
- secret exposure detected,
- stale broker state before submit.

Warnings only:

- weak strategy quality,
- incomplete research lineage,
- insufficient experiment notes,
- non-critical dashboard mismatch.

## Dashboard Boundary

The dashboard is authenticated and mostly read-only.

Read:

- mode: off, paper, live,
- engine heartbeat,
- KIS connectivity,
- cash and equity by currency,
- holdings,
- open orders,
- recent fills and rejects,
- model signals and confidence,
- ensemble action and expected edge,
- daily PnL and loss-limit usage.

Write:

- stop new orders,
- cancel open orders,
- resume only after explicit local confirmation.

The dashboard must never expose KIS secrets or raw broker payloads.
