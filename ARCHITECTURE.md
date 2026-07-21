# Architecture

## Core Pipeline

```text
market data -> point-in-time data contract -> opportunity selection
                                           -> per-symbol evidence experts
existing positions -----------------------> entry / hold / reduce / exit policy
opportunity + evidence + position state --> trade policy -> target allocation
target positions --------------------------------------> deterministic risk
                                                        -> broker intent
                                                        -> state / attribution
                                                        -> dashboard / daily review
```

The trading engine is a target-position policy graph, not a monolithic
buy/sell model. At one immutable `as_of` decision timestamp the graph is
acyclic. Across timestamps, only durable portfolio and broker state feed the
next graph evaluation. A learned node can produce evidence or a desired target
state; only deterministic Execution code may create an `OrderIntent`.

## Deployability-First Input Contract

The active paper-trading graph prefers inputs that KIS can provide at the
decision timestamp, not the broadest offline dataset that happens to be
available. A feature that cannot yet be recreated during a KIS paper session is
marked as provisional or offline-only; it is never silently substituted at
runtime. That evidence grade informs interpretation, not whether a virtual-paper
experiment may proceed.

Each active input belongs to one compact, versioned KIS capability record. It
names the non-secret endpoint/category, exchange and symbol scope, raw field,
bar interval, exchange-calendar/session interpretation, completed-bar rule,
freshness budget, history/paging cost, storage-rights status, and a dated
observed response reference. Its state is one of `declared`, `observed`,
`qualified`, or `unavailable`; documentation alone is never `observed`.

A raw timestamp's open-versus-close label needs an independently falsifiable
anchor before it can support a strong completed-bar claim. Until then the input
stays `observed`, carries its uncertainty into paper evidence, and is not used
to make an unlabelled timing claim.

`qualified` KIS-reconstructible fields support normal reusable paper models;
`observed` fields may support explicitly provisional paper experiments with
their evidence grade attached. Offline Tiingo, Norgate, or other lawful
development data may support a prototype, but a paper decision must never
silently mix a different provider into its runtime feature window. The record
is a small engine data contract, not a report family, approval gate, scheduler,
or second data catalog.

The standing private KIS Paper authority permits a local raw cache with
provenance under `D:\market_data`. `unverified` rights remain a visible
limitation and `prohibited` rights stop only the affected source. No cache may
be published, redistributed, or stored in Git. This lets paper work learn from
completed windows without turning data-rights uncertainty into a general
development freeze.

An unavailable input is removed from the active graph and recorded with its
missing dependency. It is not replaced by an inferred value, a hidden provider,
or a paper-trading blocker. A later observed KIS capability can reactivate that
branch through a new bounded contract.

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

## Target-Position Policy Graph

The graph has four product decisions and one non-negotiable execution boundary.
Each decision has a distinct training target, owner, evidence contract, and
attribution field. It prevents a successful-looking signal from hiding whether
the error came from symbol selection, timing, sizing, exit handling, or fills.

1. **Opportunity selection** chooses a point-in-time eligible universe and
   ranks symbols worth evaluating. It runs on slow horizons and can reject a
   symbol without creating a trade signal.
2. **Per-symbol evidence experts** independently evaluate only the completed
   KIS-qualified subset of `1m`, `5m`, `10m`, `1h`, and `3h` inputs. An expert
   can be a rule, statistical model, tree, sequence model, or foundation-model
   benchmark.
3. **Trade policy** fuses valid evidence into `enter`, `hold`, `reduce`,
   `exit`, or `abstain`. Entry and exit use related evidence but are separate
   tasks; an exit is not merely the inverse of a buy signal.
4. **Target-position allocation** converts eligible trade-policy outputs and
   current positions into desired long-only portfolio weights. It accounts for
   expected net edge, uncertainty, volatility, liquidity, costs, concentration,
   correlation, drawdown, and capital availability.
5. **Deterministic risk and execution** validates the delta between current and
   target positions, applies hard limits and emergency state, persists intent,
   and only then creates a broker-facing order intent.

The initial production-shaped scope is long-only. Shorting, leverage, and any
learned direct-order policy require their own later authority and validation.

### Ownership Boundary

- **Data** owns the point-in-time eligibility facts, calendars, completed-bar
  resampling, provenance, and stale/missing conditions. It does not rank a
  strategy's opportunities.
- **Engine Research** owns opportunity scores, multi-timeframe experts, fusion,
  learned allocation proposals, exit hypotheses, and their campaign evidence.
  Its output is a proposed target state with uncertainty, never an order.
- **Execution** owns current positions, cash, hard constraints, feasible target
  deltas, intent persistence, reconciliation, and the broker boundary. It may
  reject or reduce a proposed target but never invents alpha or loads model
  weights.
- **Validation** receives frozen upstream evidence and evaluates an incremental
  layer without tuning it.

### Decision Evidence Contract

Every learned or rule-based node must emit versioned, timestamped evidence,
not a bare vote or an order. The durable record must identify:

- `decision_as_of`, `feature_window_end`, source dataset/snapshot, timeframe,
  and whether every input bar was complete;
- universe or position state used, model/rule version, artifact hash, and
  feature schema hash;
- action or score, calibrated probability when applicable, expected **net**
  edge, uncertainty, horizon, and explicit `valid_until`;
- missing, stale, abstain, and data-quality conditions; and
- the upstream evidence IDs used by fusion, allocation, and exit decisions.

Evidence older than its declared validity window is not silently forward-filled.
The fusion policy must either apply its predeclared stale-evidence treatment or
abstain. This makes an incomplete `1h` or `3h` bar impossible to masquerade as
a completed higher-timeframe signal.

### Layered Proof Rule

The graph is a destination architecture, not permission to build six learned
layers at once. Each layer must earn its complexity against a simpler frozen
baseline on one new eligible campaign contract:

1. deterministic universe filter, one simple entry signal, volatility-targeted
   sizing, and deterministic exits;
2. one independently validated opportunity or single-timeframe signal model;
3. completed-bar multi-timeframe experts, then a calibrated fusion model using
   only upstream out-of-fold predictions;
4. a constrained allocation model, if it improves after-cost robustness over
   deterministic volatility/concentration sizing; and
5. an independent exit model, if it improves over fixed risk exits without
   increasing hidden turnover or tail risk.

All model-family comparisons use chronological, purged and embargoed splits.
Fusion and allocation require nested or cross-fitted upstream predictions: no
layer may train on a prediction produced in-sample by an upstream expert. The
final temporal holdout remains untouched until the entire preceding layer set is
frozen. A failed incremental comparison removes that layer from the candidate
graph rather than being tuned around indefinitely.

The first paper candidate is a fixed, simple bar-only baseline with a small
virtual exposure. It may collect KIS Paper evidence when long historical
validation is limited, provided the input grade and missing-data behavior are
recorded and execution hard stops are active. This does not promote the
baseline, prove an edge, or turn a limited observation into an unqualified
model claim.

### Timeframe Policy

The full hierarchy is a candidate topology, not an automatically enabled
production policy. A timeframe may be explored with observed KIS data when its
evidence grade, staleness, and completed-bar uncertainty are carried forward;
an unavailable timeframe is absent rather than fed a hidden proxy.

- `3h` and `1h`: market regime, direction, and opportunity context.
- `10m`: confirmation, volatility, and trend stability.
- `5m` and `1m`: entry, reduction, and exit timing.

All timeframes are derived from the same exchange-calendar-resampled bar stream.
At a fast decision time, a slower expert may use only its most recently **fully
closed** bar and must expose its age and expiry. Research may test alternative
expert topologies, but promotion must show stable, interpretable, after-cost
out-of-sample value over the simpler graph.

The Data layer has a pure `SessionWindow` resampling primitive for a caller that
already knows one UTC session open and close. It anchors buckets at that open,
rejects out-of-window bars, and exposes skipped partial or gapped buckets. It
does not infer an exchange calendar or daylight-saving rule. Callers must state
the session source and evidence grade they use when activating a timeframe.

### Initial KIS Paper Baseline

The first intended deployable candidate deliberately uses less than the observed
single-request intraday page size instead of equating an API page size with a
model requirement:

- the latest **90 completed `1m` OHLCV bars**, session state, timestamp, and
  explicit missing/stale flags form the primary input window;
- `5m` and `10m` views are deterministic local resamples of those same 90
  completed bars, yielding 18 and 9 completed bars respectively when available;
- `1h` and `3h` experts, order-book features, news, corporate-action fields,
  and external universe labels are inactive until separately qualified; and
- if the rolling KIS-compatible cache lacks a complete window, the baseline
  abstains; exact local resamples and the input's recorded evidence grade are
  required. It does not page a broker on every inference or fill the window from
  another provider.

The `90`-bar value is an initial bounded hypothesis, not a permanent setting.
A `120`, `300`, multi-session, or higher-timeframe window may be introduced
only after observed KIS retention, continuation, rate, and cache-recovery
evidence shows it can be supplied with headroom. The runtime cache is filled by
bounded startup/backfill work and ongoing bars; model inference reads the local
completed-bar cache rather than making a broker request for every decision.

The baseline outputs `enter`, `hold`, `reduce`, `exit`, or `abstain`, a bounded
target exposure fraction, confidence, `valid_until`, and input-status evidence.
It never outputs KIS request fields or an order. Execution alone maps an
accepted target delta to a KIS-compatible paper `OrderIntent`.

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

For a future eligible contract, breadth should contain materially different
families rather than repeated MLP variants: linear and tree baselines, compact
sequence candidates such as GRU/LSTM and TCN, a small attention model when the
data supports it, and a narrowly scoped time-series foundation-model benchmark.
Chronos and TimesFM are forecasting benchmarks, not direct trading policies;
their outputs must pass the same causal, cost, and allocation validation as
locally trained models. Financial language models require separately timestamped
and rights-cleared text data before they may enter a signal experiment.

External design references are inputs to research, not dependencies or evidence
of profitability: [Qlib's model/strategy/execution research architecture](https://github.com/microsoft/qlib),
the original [Temporal Fusion Transformer paper](https://arxiv.org/abs/1912.09363),
[Chronos](https://github.com/amazon-science/chronos-forecasting), and
[TimesFM](https://github.com/google-research/timesfm). Any public code or
weights still follow the provenance, license, safe-serialization, and research
isolation rules below.

Existing short 1m snapshots are development evidence until a Data-owned
manifest shows enough chronological coverage for model selection. Labels must
be realizable after the assumed fill, and final holdouts must remain sealed from
tuning.

For paper deployment, model-byte provenance is not enough: its KIS feature
reconstruction comparison must be frozen before use. The comparison declares a
numeric tolerance for every transformed feature before it runs; a material
difference, stale bar, missing field, or unavailable source causes abstention
or removes the candidate, never an undocumented substitution.

Free public models and weights stay inside the research boundary. Record source,
version, hash, and license context; prefer safe serialization; isolate code that
must load an untrusted format. Public model code and arbitrary checkpoints must
never enter the Execution process.

## Data Storage

Market-data bytes live under `D:\market_data` and are mounted read-only into
research containers. Canonical datasets carry provenance, schema, session,
corporate-action, coverage, and overlap metadata. Overlapping snapshots are
versions of evidence, not independent samples.

The KIS private daily backfill is a small canonical-cache pattern: immutable
`snapshot=*` directories hold raw rows and a manifest, while
`D:\\market_data\\us_equities\\kis_paper_private\\daily\\backfill-v1\\index.json`
holds per-symbol logical date cursors, hashes, venue-attempt evidence, and the
next shared KIS retry time. The index advances only after a snapshot's raw hash
is verified. Its logical cursor is a date with intentional exact overlap, never
an opaque KIS continuation header. An empty accepted venue response does not
become research history. The current data-bearing routes are `QQQ/NAS`,
`SPY/AMS`, and `IWM/AMS`, all requested with `MODP=0_unadjusted`.

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

KIS paper does not require a profitable model or a paper-capital approval. The
operator has standing-authorized KIS virtual-paper credential use, account and
market-data reads, submit/modify/cancel, reconciliation, routine sizing, and
goal-owned scheduling. KIS live remains a separately authorized mode.

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

The dashboard is authenticated, local/LAN-bound, and mostly read-only. The
existing Docker `web` service is a local monitor only; it neither reads KIS
credentials nor calls a broker. A future KIS-paper console is a goal-owned
Execution objective under standing paper authority, not an implicit capability
of the web process.

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

- pause new entries,
- request cancellation of open orders,
- later, pause discretionary strategy reductions when the goal-owned
  paper-execution capability is implemented;
- resume only after explicit local confirmation and fresh reconciliation.

No dashboard action may suppress a hard-risk exit, emergency containment, or
reconciliation requirement. A requested "sell stop" therefore means pausing
discretionary strategy reductions, never trapping a position by blocking a
verified risk exit. Before KIS paper read-only reconciliation succeeds, broker
facts such as holdings, prices, cash, and open orders are shown as `unknown`,
not as empty or locally inferred values. The browser reads a sanitized runtime
snapshot; credentials, account identifiers, and raw broker payloads never enter
the web process.

The dashboard must never expose KIS secrets or raw broker payloads.
