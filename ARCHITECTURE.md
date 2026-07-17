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
research/    bounded validation targets, offline experiment harnesses
state/       SQLite plus append-only JSONL event log
dashboard/   read-focused monitor plus emergency controls
ops/         daily reports, next-goal scripts, scheduled maintenance
```

Durable work is owned by Data, Engine Research, and Execution lanes. Codex may
run their disjoint work packages in parallel. Validation is independent and
temporary; Infra and Review are invoked capabilities.

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

Research uses campaign-level contracts rather than adding a job family for
every question. A campaign freezes its dataset IDs, target timing, chronological
splits, costs, baselines, metrics, compute budget, and stop rules. Breadth work
screens diverse hypotheses; depth work trains only selected candidates;
ensemble work uses independently generated predictions; replication checks
reproducibility and simple falsification controls.

Existing short 1m snapshots are development evidence until a Data-owned
manifest shows enough chronological coverage for model selection. Labels must
be realizable after the assumed fill, and final holdouts must remain sealed from
tuning.

Free public models and weights stay inside the research boundary. Record source,
version, hash, and license context; prefer safe serialization; isolate code that
must load an untrusted format. Public model code and arbitrary checkpoints must
never enter the Execution process.

## Data Storage

Market-data bytes live under `D:\market_data` and are mounted read-only into
research containers. Canonical datasets carry provenance, schema, session,
corporate-action, coverage, and overlap metadata. Overlapping snapshots are
versions of evidence, not independent samples.

Warn before projected free space falls below 20 percent. Do not begin large
acquisition or training work that would cross the 15 percent floor.

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

Agent memory is a logical view over one shared external evidence substrate, not
one database or history document per agent. The planned control paths are:

```text
D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl
D:\thericher-v2\model-artifacts\_control\catalog.sqlite
```

The append-only ledger is the canonical transition history. SQLite is a
rebuildable searchable index over runs, artifacts, lineage, claims,
validations, external assets, and recovery. Large data, traces, and model bytes
remain in their existing external artifact families.

Each active run records enough identity to classify it as `resume`, `restart`,
`reconcile`, `complete`, `unrecoverable`, or `operator`: role, run and attempt
IDs, job/campaign, dataset and artifact hashes, Git/runtime identity, lease or
lock, checkpoint, durable outputs, side-effect state, and next recovery action.
Execution broker state is never inferred from this catalog; KIS remains the
authority for external account orders, fills, cash, and positions.

## Execution Modes

Keep these concepts separate even if current code still has a smaller mode
enum:

```text
off               no broker calls or fills
local_simulation  broker-free fills, existing source: local_paper
kis_paper         KIS virtual account, explicitly authorized
kis_live          KIS real account, separately authorized
```

KIS paper does not require a profitable model. The operator first authorizes
read-only virtual-account access. After reconciliation, Codex proposes a paper
capital envelope using the smaller of actual orderable funds and the intended
shadow live capital; KRW 5,000,000 is the current planning reference. Submission
starts only after that envelope is approved or changed.

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

Paper readiness must not grow into a research promotion packet. It requires
paper/live account separation, persisted idempotent intent, bounded exposure
and loss, durable events, emergency stop, and broker reconciliation. Model
profitability, arbitrary day/trade counts, dashboards, and report chains are
not prerequisites for starting bounded paper evidence collection.

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
