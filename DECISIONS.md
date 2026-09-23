# Decisions

This is append-only. New decisions go at the bottom.

## Current KIS Paper Authority

For current private KIS Paper authority, `AGENTS.md` controls. Historical
entries that mention read-only-only access, capital-envelope approval, one-shot
reservations, or a `raw_market_data_retained` latch are superseded by the
standing-authority decisions on 2026-07-21 and 2026-07-22. They remain evidence
of their original runs, not current operating restrictions.

The operator's current directive is default forward progress for all private
Data, Research, and KIS Paper work. Do not reinterpret an unavailable input,
failed run, model result, raw-retention value, report, or schedule outcome as a
permission condition for a different correctly scoped action. Preserve the
factual record and scope its recovery/no-intent result. `KIS_LIVE_*`, real
capital, paid commitments, unclear rights, and public exposure remain separate
operator boundaries.

## 2026-07-14 - Start v2 as a new private repository

Decision: create `thericher-v2` as a new private GitHub repository.

Reason: v1 is valuable as a reference, but its report, gate, and operator
scaffolding now slows engine progress. v2 starts clean and imports only minimal
proven assets.

## 2026-07-14 - Engine-first scope

Decision: v2 focuses on data, features, models, ensemble, backtest, execution,
state, dashboard, and daily review.

Reason: the product exists to find and operate profitable strategies, not to
generate readiness evidence.

## 2026-07-14 - First paper target

Decision: start paper trading with US equities through KIS. Research Korean
equities in parallel, but do not make Korean live or paper execution the first
critical path.

Reason: US paper first reduces surface area while the engine and KIS execution
loop are being rebuilt.

## 2026-07-14 - Timeframe combination policy

Decision: default to hierarchical timeframe combination.

- 1h and 3h define regime and direction.
- 10m confirms trend stability.
- 1m and 5m drive entry and exit timing.

Research may test weighted ensembles, but production promotion requires
out-of-sample evidence and interpretability.

Reason: free-form multi-timeframe blending is easy to overfit.

## 2026-07-14 - GPU research lane

Decision: include a GPU research container early, but keep the real-time trading
loop independent from GPU runtime dependencies.

Reason: deep-learning research is part of the goal, but execution must stay
reproducible and robust.

## 2026-07-14 - Dashboard exposure

Decision: start with authenticated local or LAN dashboard access. Do not expose
the dashboard directly to the public internet.

Reason: the dashboard includes emergency controls. Remote access can later use a
VPN or tunnel if needed.

## 2026-07-14 - Live capital planning

Decision: use KRW 5,000,000 as the initial live planning cap, with a staged ramp
that starts smaller.

Reason: paper performance does not fully model live slippage, spread, latency,
or operational behavior.

## 2026-07-14 - Emergency controls

Decision: dashboard write actions are limited to two independent controls:

- stop new orders,
- cancel open orders.

Reason: the operator needs emergency control without turning the dashboard into
a trading command center.

## 2026-07-14 - Interim foundation contracts

Decision: core engine contracts use immutable dataclasses, UTC-aware timestamps,
`Decimal` for price and quantity, and `schema_version` fields.

Reason: v2 must avoid hidden floating-point accounting drift and make model,
state, and execution events replayable.

## 2026-07-14 - State source of truth

Decision: JSONL is the append-only event source. SQLite is a rebuildable query
view derived from JSONL.

Reason: keeping one source of truth avoids the state divergence that made v1
runtime artifacts hard to reason about.

## 2026-07-14 - Interim dashboard actions are local only

Decision: dashboard emergency actions write local emergency state only. They do
not call KIS, a broker, or any order endpoint.

Reason: the interim foundation should prove the operator boundary without
creating accidental trading authority.

## 2026-07-15 - Fresh Codex task handoff

Decision: create `HANDOFF.md`, `NEXT_CODEX_GOAL.md`, and
`scripts/start_next_codex_task.ps1` so future Codex work can start from v2
context without dragging v1 thread history forward.

Reason: v2 needs clean context boundaries. A fresh task should read a concise
handoff, verify the repo, and continue with a narrow engine-first objective.

## 2026-07-15 - GPU model artifact root

Decision: store GPU/research model artifacts outside the Git workspace at
`D:\thericher-v2\model-artifacts` by default. Docker research profile mounts
that host path at `/app/model_artifacts`.

Reason: deep-learning experiments can create large artifacts. Keeping them on
the larger D drive protects the repo and C drive while preserving a stable path
for future model registry work.

## 2026-07-15 - Market data resampling anchor

Decision: resample intraday bars into complete UTC-epoch anchored buckets.
Missing or incomplete source bars do not get gap-filled; their target bucket is
skipped.

Reason: data collection and backtest validation need deterministic higher
timeframe bars without hiding market-data gaps.

## 2026-07-15 - Agent stateboards

Decision: maintain compact lane stateboards under `agents/` for engine
research, data, execution, infra, and review. These files track active queues,
held resources, running jobs, and handoff notes only. `AGENTS.md` remains the
policy source and `NEXT_CODEX_GOAL.md` remains the single next objective.

Reason: long GPU research and execution/infra work need coordination without
recreating v1-style report or gate sprawl.

## 2026-07-15 - External market data root

Decision: treat `D:\market_data` as the operator-provided market data root.
Additional data may be acquired there only from no-auth, lawful,
license-compatible sources. Do not store acquired market data in Git.

Reason: data collection and model validation need more history than the Git
repo should hold, and acquisition must not depend on credentials or unclear
data rights.

## 2026-07-15 - Local paper execution foundation

Decision: local paper execution is broker-free and fills accepted orders at the
next completed bar open. Local paper fill events use `source: local_paper`; cash
is rebuilt from fill events, while portfolio snapshots are convenience caches.

Reason: paper execution must be deterministic, replayable, and impossible to
confuse with future broker or live fills.

## 2026-07-15 - Bounded model validation target

Decision: the first model-validation loop uses explicit `Bar` inputs, the simple
momentum model, ensemble decisions, and broker-free local paper execution. The
CLI defaults to deterministic sample data; external `D:\market_data` snapshots
must be passed explicitly. Validation and GPU-plan artifacts are written outside
Git.

Reason: feature/model research, backtest validation, local paper preparation,
and PnL attribution need one repeatable loop before adding broker adapters,
credentials, dashboards, or heavier models.

## 2026-07-15 - Bounded research experiment queue

Decision: short research experiments parameterize the existing validation loop
instead of adding a second replay path. The default queue sweeps a small,
bounded set of momentum lookback, threshold, and timeframe variants on
deterministic sample bars or an explicit local Yahoo snapshot. Metrics and GPU
candidate smoke artifacts are written under the configured model artifact root,
not Git.

Reason: the engine needs repeatable experiment throughput and PnL attribution
before heavier GPU training. Keeping the queue bounded avoids recreating v1
report, gate, or promotion sprawl.

## 2026-07-15 - Walk-forward research attribution

Decision: walk-forward research reuses the bounded experiment queue over capped
chronological bar windows. It records per-window trade count, ending equity,
PnL, replay fill count, replay final position, and max drawdown without adding a
promotion gate.

Reason: model research needs out-of-window behavior and attribution before GPU
time is spent on longer candidates. The artifact remains concise and outside
Git so it improves research velocity without recreating v1 report sprawl.

## 2026-07-15 - Walk-forward GPU candidate smoke

Decision: the first GPU candidate smoke selects one experiment from
walk-forward summaries using a deterministic non-gating heuristic: prefer
positive total PnL, then higher total PnL, lower drawdown, higher worst-window
PnL, and experiment id order. The smoke writes candidate metadata and GPU
readiness outside Git, but does not run GPU training or add GPU dependencies to
the base engine.

Reason: GPU time should start from explicit evidence, but candidate selection
must not become a promotion gate or dependency trap before the research runtime
is proven.

## 2026-07-15 - Research GPU runtime smoke

Decision: the first GPU runtime smoke uses only existing `nvidia-smi` readiness
and writes a `runtime_ready_only` or `prepared_not_trained` artifact under the
external model artifact root. It does not add PyTorch, CUDA, or other heavy GPU
packages to the base engine.

Reason: GPU compute work needs a reproducible research path, but base engine
tests and startup must remain light and broker-free.

## 2026-07-15 - Research GPU compute smoke stays in Docker research

Decision: GPU compute and future training smoke work runs through the Docker
`research` target/profile. The first compute smoke records the selected
walk-forward candidate and GPU readiness, writes under `/app/model_artifacts`
inside Docker, and returns non-fatal `prepared_not_trained` when no research GPU
compute backend is installed. Heavy compute frameworks are not added to the base
engine path.

Reason: the RTX 4090 should be used for model research, but the trading engine,
tests, and local paper loop must stay reproducible without CUDA or ML framework
dependencies.

## 2026-07-15 - GPU training smoke scaffold before backend approval

Decision: add a tiny GPU training smoke scaffold without adding PyTorch, CUDA,
or another heavy framework to the base or research dependencies. The scaffold
uses an injected trainer in tests, imports optional backends lazily, writes
under the external model artifact root, and records non-fatal
`prepared_not_trained` until the operator approves a research-only backend.

Reason: the engine needs a reproducible training seam before long GPU jobs, but
backend selection is an operator-level dependency decision and must not be
silently locked in by code changes.

## 2026-07-15 - PyTorch CUDA approved for Docker research only

Decision: use PyTorch CUDA as the first GPU compute/training backend, installed
only in the Docker `research` target as `torch==2.7.0+cu128` from the PyTorch
CUDA 12.8 wheel index. Do not add PyTorch to `pyproject.toml`, the base engine
image, or the local dev/test dependency path.

Reason: the operator approved PyTorch CUDA, and the RTX 4090 training smoke now
proves the research container can run a bounded GPU optimizer step while the
trading engine remains independent from heavy ML runtime dependencies.

## 2026-07-15 - Lightweight research job runner

Decision: introduce a minimal Engine Research job runner with a single
`gpu_training_smoke` job kind. The runner executes inside Docker `research`,
reuses existing smoke helpers, writes wrapper artifacts under the external model
artifact root, and keeps `agents/*.md` as lane stateboards rather than
autonomous worker processes.

Reason: the GPU research lane needs a repeatable executable queue step before
longer training starts, but a broad multi-agent platform would recreate process
sprawl before it improves model research.

## 2026-07-15 - Bounded GPU candidate training job

Decision: extend the lightweight research job runner with one
`candidate_training` job kind. It consumes selected candidate metadata and
bounded local/sample bar data, trains only a tiny PyTorch model inside Docker
`research` with strict epoch/step/bar caps, and writes metrics plus model
artifacts under the external model artifact root. A successful job records
`candidate_trained_only`; it is research evidence, not a model promotion or
execution approval.

Reason: the RTX 4090 should start producing replayable model artifacts, but the
engine still needs a small, inspectable loop before longer training, model
registry entries, broker adapters, or any live/paper execution authority.

## 2026-07-15 - Bounded candidate evaluation job

Decision: extend the lightweight research job runner with one
`candidate_evaluation` job kind. It consumes external candidate-training
metrics/model artifacts, reuses the training dataset feature names, loads
PyTorch lazily only inside the research evaluator, records held-out
classification and simple baseline metrics, and writes evaluation artifacts
under the external model artifact root. Local-paper conversion is explicitly
deferred to the next goal.

Reason: trained model artifacts need replayable evaluation evidence before GPU
time is spent on deeper training or any candidate output is mapped into paper
trading. Keeping evaluation separate from promotion and broker execution avoids
turning early research into a gate or live authority.

## 2026-07-15 - Bounded candidate local-paper replay job

Decision: extend the lightweight research job runner with one
`candidate_replay` job kind. It consumes external candidate training/evaluation
artifacts, reuses the candidate probability path, maps probabilities to
descriptive buy/sell/hold thresholds, and submits only to the broker-free
`LocalPaperBroker`. Replay artifacts, event logs, PnL, drawdown, and local paper
fill counts are written under the external model artifact root. Docker
`research` mounts `D:\market_data` read-only at `/app/market_data` so replay can
prefer explicit local snapshots.

Reason: candidate models need tradability evidence before deeper GPU training
or model registry work. Running through local paper preserves replayable fills
without introducing KIS credentials, broker submit code, live authority,
promotion gates, or dashboard expansion.

## 2026-07-15 - Bounded candidate replay comparison job

Decision: extend the lightweight research job runner with one
`candidate_replay_comparison` job kind. It consumes or runs candidate replay,
runs a gap-tolerant momentum baseline through broker-free `LocalPaperBroker` on
the same bounded bars, compares PnL, drawdown, trades, fill counts, final
position, and event counts, and writes descriptive comparison artifacts under
the external model artifact root.

Reason: candidate replay needs a simple in-repo baseline before deeper GPU
training or threshold calibration. The comparison remains research evidence,
not a promotion gate, and does not introduce KIS credentials, broker submit
code, live authority, dashboards, or scheduler/agent expansion.

## 2026-07-15 - Bounded candidate threshold sweep job

Decision: extend the lightweight research job runner with one
`candidate_threshold_sweep` job kind. It writes a bounded candidate probability
trace outside Git, then replays a capped buy/sell threshold grid through the
existing candidate local-paper execution path without rerunning inference for
each threshold pair. Sweep artifacts compare each variant to the existing
momentum baseline comparison metrics and record local paper fill counts, PnL,
drawdown, and positions.

Reason: candidate probability output needs calibration evidence before deeper
GPU training. Persisting one trace reduces repeated GPU inference while keeping
threshold exploration broker-free, credential-free, descriptive, and outside
the Git workspace.

## 2026-07-15 - Bounded threshold robustness replay job

Decision: extend the lightweight research job runner with one
`candidate_threshold_robustness` job kind. It loops over a capped set of
explicit local Yahoo `(snapshot, symbol)` slices, runs or consumes one
probability trace per slice, and reuses the existing threshold variant replay
primitive that routes through broker-free local paper. The aggregate artifact
records per-slice PnL, drawdown, fill count, final position, and threshold
metadata outside Git.

Reason: threshold sweep evidence from one CVS slice is not enough to decide
what to train next. Replaying the same variants across a few local slices shows
whether the candidate behavior is robust without adding a new replay path,
baseline gate, scheduler, dashboard, KIS access, credentials, or promotion
decision.

## 2026-07-15 - Bounded multi-slice candidate training input

Decision: extend candidate training and evaluation to accept capped explicit
local Yahoo `(snapshot, symbol)` slices. Each slice is converted through the
existing four-feature candidate dataset builder, then features and labels are
concatenated in input order with per-slice row counts and provenance recorded
in the external artifact. The research job runner exposes this through
repeatable `--data-slice` arguments while keeping PyTorch confined to Docker
`research`.

Reason: deterministic sample bars are no longer enough for model iteration.
The engine needs one bounded path from real local data to a model artifact,
evaluation artifact, and robustness replay without changing feature shape,
downloading data into Git, adding a new replay path, introducing credentials,
or creating a promotion gate.

## 2026-07-15 - Bounded probability-derived threshold calibration

Decision: extend the research job runner with one
`candidate_threshold_calibration` job kind. It runs or consumes one bounded
probability trace per explicit slice, derives a capped deterministic threshold
grid from observed probability quantiles, and then reuses the existing
threshold robustness/local-paper replay path. Calibration artifacts are written
outside Git and deliberately avoid best-threshold, pass/fail, promotion, or
deployment fields.

Reason: the first multi-slice candidate produced zero fills under the static
threshold grid because all observed probabilities were below the lowest static
buy threshold. Calibration should explain and probe that behavior while staying
descriptive, broker-free, credential-free, PyTorch-in-Docker-only, and free of a
new replay path or v1-style gate.

## 2026-07-16 - Bounded calibration holdout replay

Decision: extend the research job runner with one
`candidate_threshold_holdout` job kind. It reads a completed calibration
artifact, consumes its threshold pairs unchanged, and replays those thresholds
on explicit holdout slices through the existing threshold robustness and
broker-free local-paper path. The holdout artifact records source calibration
lineage, holdout slices, probability ranges, PnL/drawdown, fill counts,
local-paper source verification, and missing-data requests when applicable.

Reason: probability-derived thresholds can overfit the same slices that created
them. A disjoint holdout replay checks that circularity before deeper training
while avoiding new replay code, broker access, credentials, dashboards,
schedulers, best-threshold fields, promotion gates, or live/paper authority.

## 2026-07-16 - Bounded candidate breadth queue

Decision: extend the research job runner with one `candidate_breadth_queue` job
kind and a small helper that writes up to three nearby candidate metadata
artifacts outside Git, then calls the existing bounded candidate training and
evaluation primitives for each variant under strict `max_bars`, `max_epochs`,
and `max_steps` caps. The queue records per-variant artifact paths and
probability/evaluation summaries, but no winner, recommendation, pass/fail
field, or promotion gate.

Reason: the engine needs breadth evidence around the current
`m1_lb3_b10_s10` family before spending more GPU time on deeper training. A
thin queue keeps experimentation repeatable and PyTorch-in-Docker-only while
avoiding credentials, broker access, new replay code, dashboards, schedulers,
agent-framework expansion, or v1-style report/gate sprawl.

## 2026-07-16 - Bounded breadth holdout bridge

Decision: add a thin breadth holdout bridge and a `candidate_breadth_holdout`
research job kind for Docker dispatch. The bridge reads an external
`candidate_breadth_queue` artifact, processes at most three variants, resolves
each variant's existing training/evaluation/model artifacts, then calls the
existing threshold calibration and threshold holdout primitives. It records
per-candidate probability summaries, local-paper fill counts, PnL/drawdown
ranges, data requests, and fill-source verification outside Git.

Reason: breadth training/evaluation is not enough to decide where deeper GPU
time should go. The next evidence step must replay the queued candidates on
disjoint holdout slices through the already proven local-paper path while
avoiding new replay logic, KIS access, credentials, dashboards, schedulers,
best-candidate fields, pass/fail decisions, or promotion gates.

## 2026-07-16 - Bounded depth candidate target

Decision: add a thin `candidate_depth_target` helper and research job kind. It
reads the completed external breadth holdout artifact, selects at most one
completed variant with a deterministic `research_scheduling_only` heuristic,
writes a derived candidate artifact outside Git, then reuses the existing
candidate training, candidate evaluation, threshold calibration, and threshold
holdout primitives. The depth target records probability summaries,
local-paper fill counts, PnL, drawdown, source artifact verification, and
artifact paths, but no winner, recommendation, pass/fail field, or promotion
gate.

Reason: breadth holdout evidence identifies where bounded GPU depth training
should spend time next, but it must not become a production selection rule. A
single thin leaf job keeps PyTorch confined to Docker `research`, keeps
artifacts outside Git, reuses the local-paper replay path, and avoids KIS
access, credentials, dashboards, schedulers, autonomous agent expansion, or
v1-style report/gate sprawl.

## 2026-07-16 - Zero-fill local-paper event verification

Decision: local-paper holdout verification treats a missing `events.jsonl` for
a replay variant with `replay_fill_count == 0` as empty evidence, not as an
unreadable artifact failure. Variants with one or more fills still require
their event artifacts to be readable, and non-`local_paper` fill sources still
fail verification.

Reason: threshold variants can complete with no local-paper fills and therefore
have no events to replay. The verification should prove fill sources, not
mistake absence of zero-fill events for broker/non-local activity.

## 2026-07-16 - Bounded depth-vs-breadth evidence comparison

Decision: add a thin `candidate_depth_comparison` helper and research job kind.
It reads the completed external depth target artifact and the breadth holdout
artifact that scheduled it, compares only the selected variant's breadth
evidence against the depth evidence, and writes one descriptive comparison
artifact outside Git. The comparison records probability summary deltas,
local-paper fill count delta, PnL/drawdown deltas, cap deltas, data-slice
evidence, and referenced artifact existence.

Reason: the first depth target needs a compact evidence loop before spending
more GPU time. Comparing existing artifacts is enough; rerunning training or
holdout would duplicate work. The output stays `research_comparison_only` and
does not add KIS access, credentials, broker submit code, PyTorch to the base
path, a dashboard, scheduler framework, best-candidate field, pass/fail
decision, or promotion gate.

## 2026-07-16 - Bounded comparison-informed threshold rerun

Decision: add a thin `candidate_threshold_rerun` helper and research job kind.
It reads the completed external depth comparison and depth target artifacts,
derives a capped stricter threshold grid from the source calibration thresholds
and comparison evidence, then reuses the existing threshold holdout,
robustness, and local-paper replay path. The rerun writes one descriptive
artifact outside Git and labels the work `research_threshold_rerun_only`.

Reason: the depth target increased fill count while worsening the PnL floor and
drawdown, so the next bounded step should test a stricter fill-aware grid
without retraining, optimizing thresholds, ranking pairs, or creating a
promotion rule. Reusing the holdout path avoids KIS access, credentials, broker
submit code, dashboard expansion, scheduler logic, and PyTorch in the base
engine.

## 2026-07-16 - Bounded zero-fill threshold attribution

Decision: add a thin `candidate_threshold_attribution` helper and research job
kind. It reads the completed threshold rerun artifact plus its referenced
robustness, source calibration, and probability trace artifacts, then records
per-slice and per-threshold buy/sell opportunity counts, replay fill counts,
PnL, drawdown, and local-paper verification. The output is
`research_threshold_attribution_only` and records no winner, recommendation,
pass/fail decision, or promotion gate.

Reason: the fill-aware strict rerun produced zero fills because the strict buy
band sat above the observed holdout probability range. Explaining that from
existing artifacts is enough before trying another bounded band; rerunning
training, inference, broker execution, dashboards, schedulers, or report/gate
machinery would add process before evidence.

## 2026-07-16 - Bounded attribution-informed threshold band rerun

Decision: add a thin `candidate_threshold_band_rerun` helper and research job
kind. It reads the zero-fill attribution artifact and its rerun lineage,
derives a capped exploratory band from source calibration thresholds below the
observed probability ceiling, then reuses the existing threshold holdout,
robustness, probability-trace, and local-paper replay path. The output is
`research_threshold_band_rerun_only` and records no winner, recommendation,
pass/fail decision, scheduler, or promotion gate.

Reason: one bounded inside-range replay closes the threshold-only loop by
showing that the candidate can generate local-paper fills again, but the
slice-level PnL/drawdown evidence is mixed. Further progress should branch to
feature/model research rather than repeatedly adjusting thresholds around the
same compressed probability distribution.

## 2026-07-16 - Bounded feature-branch replay attribution

Decision: add a thin `candidate_feature_branch_replay` helper and research job
kind. It reads the completed external feature-branch artifact, resolves its
training, evaluation, and model artifacts, derives a capped replay band from
the feature-branch probability evidence, then reuses the existing
threshold-robustness and broker-free local-paper path. The output is
`research_feature_branch_replay_only` and records no winner, recommendation,
pass/fail decision, scheduler, or promotion gate.

Reason: the first `core_plus_bar_position_v1` feature branch changed the
probability distribution enough to justify one bounded replay attribution step.
Reusing the existing local-paper path converts that evidence into PnL,
drawdown, and fill-source attribution without adding KIS access, credentials,
broker submit code, dashboards, schedulers, or another threshold-only loop on
the old compressed candidate.

## 2026-07-16 - Local-paper source-filtered attribution helper

Decision: centralize fill-source evidence in a pure execution helper that reads
event artifacts, counts fills by `source`, returns local-paper-only fill
payloads, flags mixed or unknown sources, tolerates missing zero-fill event
files, and records unreadable nonzero-fill event artifacts. Existing research
verification paths call this helper instead of hand-rolling source counting.

Reason: future broker and live fills must not be confused with local-paper
research evidence. A small shared helper improves PnL attribution and
paper-trading safety without adding KIS access, credentials, broker submit
code, dashboards, reports, schedulers, or another research artifact family.

## 2026-07-16 - Disabled broker adapter boundary fuses

Decision: define the first broker adapter boundary as disabled by default. The
KIS skeleton exposes disabled capabilities, typed submit/cancel/status
unavailable results with `source: broker_disabled`, and a factory that raises if
broker execution is explicitly requested. The boundary performs no network,
credential, environment, or event-log I/O.

Reason: future KIS paper and live execution needs a clear order lifecycle
surface, but the current engine must remain unable to submit broker orders or
confuse disabled broker outcomes with `source: local_paper` fills.

## 2026-07-16 - Warning-only market-data quality checks

Decision: add a pure `Bar` quality helper that returns descriptive warnings for
duplicate bar keys, non-monotonic timestamps, missing expected 1m intervals, and
incomplete resample buckets. The helper does no I/O, does not mutate bars,
does not gap-fill data, and does not block research.

Reason: repeated GPU validation is now reusing local Yahoo 1m slices. The
engine should make data-quality issues visible before spending more GPU time,
but warnings must not become v1-style gates or reports unless they protect a
future execution hard stop.

## 2026-07-16 - Compact quality summaries in candidate artifacts

Decision: attach compact `data_quality` summaries to existing candidate
training/evaluation source-slice metadata when local Yahoo bars are loaded. The
summary records row count, warning count, non-blocking status, and warning-code
counts derived from `assess_bar_quality`; deterministic samples and
config-only unavailable slices keep their existing empty or placeholder source
metadata.

Reason: the research loop needs slice quality evidence next to model artifacts,
but it does not need another checker, job family, report, or gate. Keeping the
projection compact makes repeated GPU experiments easier to compare without
changing rows, thresholds, replay behavior, broker boundaries, credentials, or
artifact storage policy.

## 2026-07-16 - Bounded calibration job threshold cap

Decision: expose `--threshold-pair-cap` on the existing research job runner for
`candidate_threshold_calibration`, with a conservative job-wrapper default of
three derived threshold pairs. The underlying calibration helper keeps its
existing validation and descriptive output; this only gives Docker research
jobs a smaller runtime control.

Reason: a 3-slice, 80-bar calibration replay with the full derived grid can run
for minutes without writing the final calibration artifact because robustness
variants are replayed sequentially. A small cap keeps calibration usable in the
single-GPU lane without adding a scheduler, new job family, promotion gate,
dashboard, broker behavior, or credential access.

## 2026-07-16 - Explicit bar-pressure feature branch

Decision: add `core_plus_bar_pressure_v1` as one supported candidate feature
set inside the existing training feature builder. It keeps the previous
`candidate_feature_branch` default unchanged, adds explicit
`--candidate-feature-set` selection to the existing research job runner, and
passes `--threshold-pair-cap` through the existing feature-branch replay job.
The feature branch records `feature_branch_axis: bar_pressure` and stays
descriptive only.

Reason: the next research step needed one bounded feature/model branch without
mutating prior `core_plus_bar_position_v1` lineage or adding another job
family. Explicit feature-set selection preserves replayability while allowing
Docker `research` to train/evaluate/replay the new branch with artifacts
outside Git and all simulated fills checked as `source: local_paper`.

## 2026-07-16 - Explicit hidden-units model axis

Decision: expose one model-axis selector, `--hidden-units`, through the
existing research job runner for `candidate_training` and
`candidate_feature_branch` only. The default remains 8, the selector is capped,
and evaluation/replay jobs remain checkpoint-driven rather than accepting a
second architecture value. Training and feature-branch artifacts record a
derived `model_axis` payload with no promotion semantics.

Reason: the next research step needed one bounded model-axis branch without
adding a job family or changing feature-set defaults. Threading the existing
training config knob preserves prior lineage, keeps PyTorch confined to Docker
`research`, keeps artifacts outside Git, and avoids KIS, credentials, broker
submit code, dashboards, schedulers, or model-promotion language.

## 2026-07-16 - Bounded feature-branch replay ceiling guard

Decision: clamp the feature-branch replay buy threshold ceiling below `1.000`
when `max_probability` floors to an invalid replay threshold. The existing
`derive_feature_branch_replay_threshold_pairs` helper now preserves
non-saturated behavior, restores capped pair counts for saturated max evidence,
and emits compact `saturation_guard` metadata only when the clamp is applied.

Reason: hidden-units feature branches can produce saturated max probabilities,
which caused cap-limited replay to return fewer threshold pairs without
changing the local-paper path. A small helper guard improves replay attribution
while avoiding a new job family, threshold optimization loop, KIS access,
credentials, broker submit code, dashboards, schedulers, or model-promotion
language.

## 2026-07-16 - Bounded feature-branch replay opportunity attribution

Decision: add an artifact-only feature-branch replay opportunity attribution
entrypoint that consumes an existing feature-branch replay artifact, resolves
its threshold robustness artifact, reuses the existing probability-trace
attribution helper, and writes one external attribution artifact. It does not
add a research job kind, rerun inference, train a model, or replay broker
orders.

Reason: the guarded hidden4 replay restored the threshold pair cap but still
produced zero fills. Existing robustness traces were enough to show that the
guarded buy thresholds had zero holdout buy opportunities while preserving
local-paper source evidence and broker-disabled source separation. Reusing the
attribution helper avoids another threshold workflow, KIS access, credentials,
broker submit code, dashboards, schedulers, or model-promotion language.

## 2026-07-16 - Bounded regularization model axis

Decision: expose one regularization selector, `--weight-decay`, through the
existing research job runner for `candidate_training` and
`candidate_feature_branch` only. The default remains `0.0`, values must be
finite, non-negative, and no more than `0.1`, and the only runtime sink is the
Docker `research` PyTorch Adam optimizer. Training and feature-branch artifacts
record a descriptive `regularization_axis` payload with no promotion semantics.

Reason: saturated feature-branch probability evidence needed one bounded
regularization probe before trying another model path. Keeping the selector on
the training side preserves evaluation/replay/attribution as checkpoint-driven
flows and avoids KIS access, credentials, broker submit code, dashboards,
schedulers, optimizer-search sprawl, or model-promotion language.

## 2026-07-16 - Bounded feature preprocessing axis

Decision: expose exactly one preprocessing selector,
`--feature-preprocessing feature_standardization`, through the existing research
job runner for `candidate_training` and `candidate_feature_branch` only. The
default remains `none`. Training computes feature means/scales, writes
normalization metadata and a signature to external training/model artifacts,
and evaluation, replay, and probability-trace paths consume the artifact-carried
metadata rather than accepting an independent preprocessing value.

Reason: saturated feature-branch probability evidence needed one bounded input
normalization probe. Binding preprocessing to the checkpoint/artifact lineage
keeps replay deterministic, avoids a broad preprocessing search, keeps PyTorch
confined to Docker `research`, writes artifacts outside Git, and avoids KIS
access, credentials, broker submit code, dashboards, schedulers, or
model-promotion language.

## 2026-07-16 - Bounded source-vs-holdout probability alignment attribution

Decision: extend the existing feature-branch replay opportunity attribution
artifact with a descriptive `source_vs_holdout_probability_alignment` block.
The block records source probability summaries, holdout probability summaries,
signed deltas, threshold gaps, opportunity counts, and local-paper verification
without creating a new research job kind or artifact family.

Reason: the standardized feature branch reduced source-side saturation but its
source-derived buy thresholds still sat above the observed holdout probability
range. The existing attribution helper already consumed replay, robustness, and
trace artifacts, so adding one compact block there avoids duplicate
artifact-only workflows, KIS access, credentials, broker submit code,
dashboards, schedulers, alignment scores, or model-promotion language.

## 2026-07-16 - Bounded disjoint-evaluation feature branch

Decision: allow `candidate_feature_branch` to receive explicit evaluation data
slices separately from training data slices. When no evaluation slices are
provided, the feature-branch path keeps its previous behavior and evaluates on
the training slices or the training artifact lineage. Feature-branch artifacts
surface both training and evaluation source-slice lineage as descriptive
metadata.

Reason: source-derived probability evidence produced buy thresholds above the
observed holdout range. Letting a feature branch evaluate on disjoint local
slices before replaying keeps threshold derivation closer to out-of-sample
probabilities while preserving artifact-driven downstream replay, PyTorch in
Docker `research`, external artifact storage, and no KIS access, credentials,
broker submit code, dashboards, schedulers, disjointness gate, or
model-promotion language.

## 2026-07-16 - Bounded entry-quality diagnostic helper

Decision: add a pure `entry_quality_diagnostic` research helper that consumes
provided probability trace entries, `Bar` data, threshold variants, and
local-paper verification evidence. It records buy opportunities, local-paper
entry linkage, fixed 5/15/30-bar diagnostic marks, adverse/favorable excursion,
and sell-threshold timing. The helper writes no artifacts, performs no network,
credential, broker, or market-data I/O, and emits no ranking, pass/fail,
recommendation, or promotion fields.

Reason: out-of-symbol feature-branch replay produced only two buy opportunities
and both resulting ABNB entries were fee-aware negative. A small reusable
diagnostic helper prevents repeated one-off scripts while keeping the evidence
descriptive, artifact-driven, local-paper-separated, and free of threshold
search, scheduler, dashboard, broker behavior, or model-promotion language.

## 2026-07-16 - Explicit entry-adverse feature branch

Decision: add one `core_plus_entry_adverse_v1` feature-set branch as a superset
of `core_plus_bar_pressure_v1`. It adds exactly two interpretable features,
`upper_wick_share` and `low_vs_prior_low_return`, both derived from the existing
current/prior `Bar` inputs. The branch is available through the existing
candidate training, feature-branch, and research-job paths only, with no new job
kind, CLI, scheduler, dashboard, gate, threshold search, broker path, or model
promotion fields.

Reason: entry-quality diagnostics showed the loss-bearing out-of-symbol entries
had weak forward marks and minimal favorable excursion. One bounded feature
branch can test whether explicit pre-entry adverse pressure and weak
follow-through evidence changes probability/replay behavior while keeping
PyTorch confined to Docker `research`, artifacts outside Git, and all execution
evidence broker-free and labeled as local paper.

## 2026-07-16 - Bounded diagnostic exit-overlay helper

Decision: add a pure `exit_overlay_diagnostic` research helper that consumes
provided trade segments and `Bar` inputs, enforces fixed 2/3/5-bar diagnostic
exit overlays, and can carry conditional latency/adverse metadata without
selecting an exit policy. Overlay outcomes are labeled
`source: diagnostic_overlay` and local-paper entry/exit sources are preserved
as provided.

Reason: repeated one-off exit timing diagnostics needed one reusable
attribution helper before any replay rerun or exit-policy experiment. Keeping
the helper pure avoids broker access, credentials, file or network I/O, CLI
surface, job-kind growth, dashboard work, training, threshold search, and
model-promotion language.

## 2026-07-16 - Bounded diagnostic exit-composite helper

Decision: extend `exit_overlay_diagnostic` with a pure
`compute_diagnostic_exit_composite` helper. It consumes provided diagnostic
overlay segment payloads, inspects one named conditional metadata id,
substitutes a named fixed-horizon diagnostic overlay only when that condition is
met, retains local-paper exits otherwise, and returns descriptive group and
overall metrics with explicit source labels.

Reason: the exit-latency composite diagnostic showed a useful recurring
calculation that should not stay as one-off script logic. A small pure helper
keeps the evidence reusable while avoiding broker behavior, credentials, file
or network I/O, artifact writers, CLIs, research job kinds, dashboards,
schedulers, replay mutation, policy selection, and model-promotion language.

## 2026-07-16 - Bounded research-only exit-latency sandbox helper

Decision: add pure research helpers for exit-latency sandbox marks:
`ExitLatencySandboxSegment`, `ExitLatencySignalRecord`, and
`compute_exit_latency_sandbox_marks`. The helper consumes provided trace timing
records and `Bar` inputs, emits `source: diagnostic_overlay` marks only when a
bounded latency condition is met, and reports missing signal, entry-bar,
signal-bar, or horizon evidence as diagnostic states.

Reason: composite segment evidence is useful but post-hoc. A small
source-labeled sandbox helper lets research inspect exit-latency timing before
any simulator or local-paper replay change, while avoiding KIS access,
credentials, broker behavior, file or network I/O, artifact writers, CLIs,
research job kinds, dashboards, schedulers, threshold search, and
model-promotion language.

## 2026-07-17 - Single-shot Engine Research Agent runner

Decision: add one explicit `thericher-v2-engine-research-agent` CLI with
`seed-gpu-training-smoke` and `run-once`. The runner stores queue, lock, and
run-state artifacts under the external model artifact root, claims at most one
JSON queue item by deterministic filename order and atomic move, uses a single
GPU lock file, and executes GPU work only through Docker `research` by calling
the existing `thericher-v2-research-job` command.

Reason: the Engine Research Agent needed a first executable worker shape rather
than only a stateboard. Keeping it single-shot avoids daemon, scheduler,
notification, dashboard, broad multi-agent framework, auto-commit, broker,
credential, or `.env` behavior while starting the single-GPU queue cadence.

## 2026-07-17 - Bounded Engine Research Agent enqueue command

Decision: extend the single-shot Engine Research Agent runner with one
`enqueue-research-job` subcommand for existing `thericher-v2-research-job`
kinds. Enqueue validates a closed kind set, writes exactly one external JSON
queue item atomically, rejects queued artifact-root overrides and obvious
credential, KIS, or broker terms, and leaves `run-once` as the only executor.
The runner mounts the current `src` read-only into Docker `research` so queued
jobs use current committed source without rebuilding the PyTorch image.

Reason: the runner needed to execute useful bounded research jobs beyond GPU
smoke. A single explicit enqueue command keeps queue behavior reproducible while
avoiding arbitrary shell execution, stateboard-driven behavior, daemon loops,
schedulers, dashboards, broker authority, credential reads, local/base PyTorch,
or model-promotion semantics.

## 2026-07-17 - Single-shot Data Agent runner

Decision: add one explicit `thericher-v2-data-agent` CLI with
`enqueue-data-job` and `run-once` for a closed first kind,
`market_data_inventory`. The worker stores queue, run-state, and inventory
artifacts under `D:\thericher-v2\model-artifacts\data-agent`, claims at most one
queued job per invocation, reads only existing market-data paths, and writes a
descriptive inventory artifact outside Git.

Reason: the operator wants role agents that do real parallel lane work rather
than only markdown stateboards. A non-GPU Data Agent worker creates a second
executable lane disjoint from Engine Research Agent's Docker/GPU queue while
avoiding KIS access, credentials, broker behavior, network acquisition, Docker,
PyTorch, schedulers, dashboards, auto-commit, generic agent orchestration,
quality gates, and report sprawl.

## 2026-07-17 - Bounded feature-input ablation job

Decision: add one research-only `candidate_feature_input_ablation` job kind and
helper. It consumes existing feature-input stability artifacts, filters
candidate-entry rows to `source: diagnostic_overlay`, compares at most three
explicit feature groups, runs PyTorch lazily only inside Docker `research`, and
writes metrics/model artifacts outside Git.

Reason: cross-slice diagnostics showed modest but repeatable feature directions
that needed a small reusable ablation before deeper GPU training. Keeping this
as one bounded research primitive avoids broker access, KIS credentials, replay
mutation, dashboards, schedulers, broad hyperparameter search, report/gate
sprawl, and model-promotion semantics.

## 2026-07-17 - Full-row feature-input ablation mode

Decision: extend the existing feature-input ablation helper with an explicit
row mode. The default `selected` mode preserves prior behavior. The
`all_diagnostic` mode reconstructs candidate-entry rows from existing stability
artifact lineage, probability traces, and local market-data rows, labels those
rows as `source: diagnostic_overlay`, and keeps local-paper fills as source
evidence only. Lineage path resolution is limited to the configured external
model-artifact and market-data roots.

Reason: the selected `24`-row ablation was too small to justify another deep
GPU block. Reusing the same helper over all `659` diagnostic rows gives a
bounded comparison while avoiding replay mutation, broker/KIS access,
credentials, arbitrary local file reads, dashboard/scheduler/coordinator work,
new report families, broad sweeps, and model-promotion semantics.

## 2026-07-17 - Slice-aware feature-input evaluation metrics

Decision: extend the existing feature-input ablation runner with in-sample,
descriptive evaluation metrics: majority-rate context, balanced accuracy,
class recalls, deterministic average-rank AUC, log loss, per-slice metrics, and
per-variant metrics. Row metadata is aligned with diagnostic rows only, and
lineage path resolution rejects traversal outside the configured external model
artifact and market-data roots.

Reason: full-row accuracy matched the adverse/no-lift majority rate, so raw
accuracy alone could overstate signal quality. Adding descriptive metrics inside
the existing artifact keeps the evidence visible without adding a new report
family, gate, scheduler, dashboard, replay mutation, broker/KIS surface,
credential path, local/base PyTorch dependency, or model-promotion semantics.

## 2026-07-17 - Unique-signal feature-input evaluation metrics

Decision: extend the same feature-input ablation payload with duplicate-aware
unique-signal metrics. Signals are keyed by `slice_id`, `symbol`,
`execution_bar_start`, and `offset`; repeated threshold-variant rows are scored
with mean probability; incomplete keys are counted but not collapsed; mixed
labels are counted and skipped from primary unique-signal metrics.

Reason: the full-row diagnostic set contains `659` rows but only `256` market
moments, so threshold-variant duplication can make row-level evidence look more
independent than it is. Keeping unique-signal metrics inside the existing
artifact exposes that structure without adding a new job family, report, gate,
scheduler, dashboard, broker/KIS surface, credential path, replay mutation,
local/base PyTorch dependency, or model-promotion semantics.

## 2026-07-17 - Unique-signal probability-band diagnostics

Decision: extend the unique-signal feature-input evaluation with one
descriptive probability-band diagnostic family: global rank tertiles over
scored unique signals. Band edges are assigned by deterministic sorting on
probability and signal key, reused for per-slice summaries, and never searched
or used as a trading threshold.

Reason: raw pre-entry unique-signal AUC suggested ranking evidence, but AUC
alone does not show whether adverse/no-lift concentration is monotonic or
slice-stable. One global tertile diagnostic makes that structure visible while
avoiding threshold search, per-slice fitting, broker/KIS behavior, credential
paths, replay mutation, report/gate sprawl, dashboards, schedulers, and
model-promotion semantics.

## 2026-07-17 - Raw pre-entry band feature attribution

Decision: extend the same feature-input ablation payload with descriptive raw
pre-entry feature attribution by the existing unique-signal global probability
tertiles. Attribution summarizes only the fixed raw pre-entry feature names,
collapses duplicate threshold-variant rows before banding, excludes missing raw
feature values from summaries, and compares the high-probability tertile to the
overall unique-signal population and the low-probability tertile.

Reason: raw pre-entry probability bands concentrated adverse/no-lift labels,
but the prior artifact did not explain which input features characterized that
band. Keeping attribution inside the existing helper/job makes the evidence
reusable while avoiding threshold search, feature-rule selection, broker/KIS
behavior, credential paths, replay mutation, new job families, report/gate
sprawl, dashboards, schedulers, durable agent workers, and model-promotion
semantics.

## 2026-07-17 - Raw pre-entry local-paper outcome attribution

Decision: add one bounded artifact-only local-paper outcome attribution helper
for raw pre-entry diagnostic context. The helper reconstructs diagnostic rows
from the existing feature-input stability lineage, reads existing local-paper
event artifacts referenced by that lineage, reuses trade-path attribution for
fill pairing, and summarizes local-paper outcomes by raw feature tertiles and
pre-entry buckets.

Reason: raw pre-entry feature attribution described the high adverse/no-lift
context, but not how that context related to existing local-paper fills and
trade paths. One pure helper advances PnL attribution while avoiding replay
reruns, broker/KIS behavior, credential paths, network access, new research job
kinds, dashboards, schedulers, gates, threshold search, feature-rule
selection, durable agent workers, and model-promotion semantics.

## 2026-07-17 - Raw pre-entry attribution contract tightening

Decision: tighten the raw pre-entry attribution contracts without adding a new
job kind, worker, report family, dashboard, scheduler, replay path, or GPU
training. The raw outcome helper now reuses the feature-input unique-signal key
constant, imports local-paper constants without the execution barrel, counts
matched local-paper entry keys separately from local-paper fill events, and the
raw-band policy explicitly records that it is not a feature rule.

Reason: Claude and sidecar review warned that raw pre-entry attribution is near
the report-sprawl boundary. A small contract pass keeps the existing evidence
reusable for feature/model research and PnL attribution while preserving
diagnostic/local-paper source separation, exact entry joins, missing-evidence
reporting, external artifact storage, and no broker/KIS/credential behavior.

## 2026-07-17 - Bounded replay opportunity prefilter

Decision: add one research-only feature-branch replay opportunity prefilter.
The helper reads an existing feature-branch artifact, derives replay thresholds
with the existing helper, consumes at most 12 local-data/probability-trace
candidates, ranks only diagnostic probability gaps, and writes one compact
external artifact. By default it consumes existing trace artifacts only and
does not run Docker/GPU, replay, orders, fills, broker code, credentials,
network, data acquisition, a job kind, worker, scheduler, gate, or report
family.

Reason: repeated blind fresh-symbol replays were producing zero fills because
observed probabilities stayed below derived buy thresholds. A small prefilter
reduces wasted replay work while preserving source separation: ranked context
is `source: diagnostic_overlay`, any later replay must remain existing
broker-free local paper, and the prefilter has no execution, risk, or promotion
authority.

## 2026-08-02 - Treat the verified KIS intraday cache as prospective-input evidence, not a historical validation panel

Decision: freeze `kis-intraday-mtf-availability-receipt-v1` as an offline
availability contract for the verified local QQQ/NAS and SPY/AMS one-minute
caches. At a fixed 15:30 America/New_York cutoff it requires the exact causal
360-minute prefix and complete `1m/5m/10m/1h/3h` tails of `30/6/3/2/2` before a
common session counts. The external receipt stores only source identities,
geometry, aggregate counts, categories, and hashes.

Reason: local minute rows are plentiful, but the 21 aligned regular sessions
are only 21 independent session blocks. Treating individual bars as independent
validation observations would manufacture confidence and invite static-panel
fishing. The receipt therefore qualifies the data only for prospective input
construction and content-bound observation, not for a performance claim,
model selection, GPU appointment, ensemble, Paper input, or broker action.

The next candidate must exclude these historical sessions and accumulate a
forward-only aligned QQQ/SPY sequence. A frozen Engine campaign may be proposed
after 30 fresh pair records establish an independent temporal surface. Claude's
bounded architecture prompt returned no final verdict; record
`review_unavailable`, not agreement or a hold.

## 2026-07-18 - Readiness-driven role agents and recoverable memory

Decision: Codex orchestrates three durable lanes: Data, Engine Research, and
Execution. Validation is temporary and independent; Infra and Review are
invoked capabilities. Lanes advance ready, non-conflicting work without fixed
percentages or forced rotation. `NEXT_CODEX_GOAL.md` remains the one company
objective, stateboards remain current projections, and durable run/evidence
history belongs in an append-only external ledger plus rebuildable catalog.
Only one concise daily operator summary is written.

At each company-goal boundary, Codex also reviews direction, lane readiness,
resources, policy fit, and role lifecycle. It may make reversible no-cost role
and operating-policy changes autonomously; only genuine operator authority or
materially different business/risk choices are escalated.

Reason: the operator has limited daily review time, while useful data,
research, and execution preparation can proceed independently. This structure
preserves ownership and recovery without creating separate goal authorities,
standing process teams, or report sprawl.

The daily summary may report zero broker or order activity only from a fresh,
timestamped runtime snapshot. Missing, invalid, future, or stale evidence is
reported as unknown so a persistent old snapshot cannot create false safety.

## 2026-07-18 - Autonomous free inputs with bounded storage

Decision: Data may acquire no-auth, no-cost, lawful, license-compatible inputs
that directly improve an active engine loop, and Research may adopt comparable
public models, weights, and routine dependencies after lightweight provenance,
license, and security checks. Paid, login-gated, manual-license, major-runtime,
or framework-changing inputs require operator approval. Data and generated
artifacts stay on `D:`; warn at 20 percent free space and stop autonomous
acquisition before falling below 15 percent.

Reason: broad evidence gathering should not wait for routine approval, but cost,
rights ambiguity, unsafe model loading, and storage exhaustion remain real
operator or engineering risks.

## 2026-07-18 - Early KIS paper milestone and falsification review

Decision: KIS paper is an early execution-evidence milestone independent of
model profitability. The operator first authorizes read-only paper account
access; Codex then proposes a bounded paper capital envelope from reconciled
buying power and intended shadow live capital for operator approval. Routine
paper activity inside that envelope does not need repeated approval. Live mode
always requires separate authority.

Claude is a falsification-first challenger at leakage and survivorship
decisions, breadth-to-depth selection, sealed holdout use, unexpectedly strong
claims, correlated ensembles, KIS capital/risk changes, incident recovery, and
major architecture or runtime growth. Its verdict is advisory and scoped to
the named boundary. Emergency containment never waits for review, and secrets,
account identifiers, and raw sealed labels are never sent to Claude.

Reason: paper trading must not be delayed by a profitability bureaucracy, while
capital, leakage, confirmation bias, and architectural drift deserve an
independent challenge before a decision is relied on.

## 2026-07-18 - Byte-bound campaigns and durable fake execution

Decision: catalog-backed campaign runs consume loader-attested Data-owned
`CatalogedBars` created from the same verified file bytes that are parsed into
bars; normal direct construction is rejected. Campaigns
reject raw bar lists, dataset or timeframe mismatches, temporary replay state,
and artifact overwrite. Local-paper JSONL, SQLite, emergency state, and hashes
remain external and replayable. Current short intraday and post-constructed
daily evidence is development-only, not ranking or sealed-holdout evidence.

The broker-neutral fake atomically persists intent before accepting submit,
round-trips JSON state across restart, and fails closed on `outcome_unknown`
until authoritative status and any progressed fill evidence are atomically
merged and cleanly reconciled. This does not enable KIS or grant broker
authority.

Reason: Review reproduced cases where caller-supplied hashes, mismatched
timeframes, deleted replay state, volatile intents, and cached acknowledgements
could make an apparently successful test stronger than its durable evidence.
Binding bytes, timing, source, and recovery closes those failures without a new
worker, report family, gate, broker endpoint, credential path, or scheduler.

## 2026-07-18 - Fixed RAW D1 campaign and sensitivity falsification

Decision: freeze one development-only RAW D1 campaign for `SPY`, `QQQ`, and
`IWM` with exact observed-session boundaries, next-open entry and exit, nonzero
costs, fold-local preprocessing, three fixed candidates, and at most six Docker
PyTorch CUDA fits. Primary and factor-exclusion replays use the same trained
checkpoints. Any after-cost sign or aggregate relative-order instability makes
the sensitivity verdict `unsupported`.

The completed evidence is structurally valid but unsupported: two
`d1-pressure-lb20` cells changed sign and aggregate order changed. No candidate
is selected or promoted, and the result is not a profitability claim. Data now
owns qualification of explicit corporate-action and distribution evidence;
Research may replay existing checkpoints against that evidence without
retraining.

Reason: the bounded campaign proved the data-to-training-to-local-paper recovery
loop while falsification exposed that heuristic adjustment-factor dates can
materially change the research conclusion. More GPU search would compound an
unresolved data assumption rather than strengthen the engine.

## 2026-07-18 - Typed long-reduction pre-submit risk

Decision: pre-submit risk remains a pure decision over the exact durably
persisted request and fresh typed evidence. Long-only sells must prove available
quantity with a matching `PositionSnapshot`; notional alone is insufficient. A
verified reduction may bypass entry-only emergency, loss, order-count,
open-order-count, and maximum-position caps, but durability, account,
open-order, position, and reconciliation integrity still fail closed.

Reason: exits should not be trapped by limits intended to prevent new exposure,
while stale or ambiguous state must never authorize an unsafe sell. This adds no
submit side effect, KIS call, credential path, broker authority, or live mode.

## 2026-07-18 - Explicit-event evidence before sensitivity replay

Decision: the RAW D1 factor-sensitivity question may use explicit distributions
and splits only through a Data-owned, loader-attested external snapshot. The
snapshot must bind raw and normalized bytes, exact r2 lineage, event-date and
session semantics, coverage, provenance, rights, and source-as-of facts. Research
may then reuse the existing six checkpoints for 36 fixed replay cells with zero
training; the parent `unsupported` verdict remains sticky and the result cannot
rank, promote, select, open a holdout, or claim profitability.

No current no-auth source proved both usable preservation rights and complete
split/no-split coverage for SPY, QQQ, and IWM. Acquisition therefore stopped
fail-closed. A free Tiingo account/token is the smallest remaining source path,
but creating or reading that credential requires operator approval and grants
no paid-data, KIS, broker, or live authority.

Reason: adjustment-factor heuristics materially changed the research conclusion,
while a missing event row is not evidence that no event occurred. A narrow
offline contract and no-retraining replay resolve that assumption without more
GPU search, report/gate sprawl, or credential creep.

## 2026-07-18 - Scoped Tiingo and KIS paper read-only authority

Decision: the operator authorized the ignored root `.env` `TIINGO_API_TOKEN`
for standard Tiingo EOD retrieval of SPY, QQQ, and IWM, and `KIS_PAPER_*` for
one read-only virtual-account discovery of masked identity, cash, orderable
funds, positions, and open orders. Secrets and unmasked account identifiers may
not enter logs, tests, artifacts, Git, reports, or Claude prompts.

`THERICHER_MODE=off` remains fixed. This authority does not include KIS submit,
modify, cancel, paper capital allocation, `KIS_LIVE_*` access, live behavior,
paid data, or unrelated `.env` keys. After successful paper reconciliation,
Codex proposes a capital envelope for a separate operator decision.

Reason: authenticated EOD data closes the current corporate-action evidence gap,
while read-only paper facts advance execution readiness without conflating
credential availability with order or capital authority.

## 2026-07-18 - Explicit-event replay preserves the unsupported verdict

Decision: accept `raw-d1-explicit-events-20260718-r3` only as retrospective,
development-only replay evidence. It reused the fixed six checkpoint bytes on
CPU, trained zero models, executed 18 baseline and 18 candidate cells, kept all
fills `source: local_paper`, and ended flat. The summary SHA-256 is
`3cac5f0b14e602c6a0043bb141fa7d6add1ca02b8ab4e214145443a1d8711609`.
The parent factor-sensitivity verdict remains `unsupported`; r3 cannot rank,
select, promote, or support a profitability claim.

Reason: explicit Tiingo event evidence removed the current date-mapping
assumption without changing the original candidate set, checkpoints, or
training. A compact read-only attribution is the next useful question; blind
GPU search would not resolve the existing falsification result.

## 2026-07-18 - Replay attribution is accounting consistency only

Decision: accept the external r3 attribution only as a hash-bound accounting
check of fixed local-paper replay cells. It verifies source and evidence hashes,
FIFO realized after-cost PnL, fees, slippage, fill counts, replayed cash, and
flat positions per cell. Its output carries the parent `unsupported` verdict,
states that the fills are shared evidence, and omits cross-cell PnL aggregation
because the cells overlap and are not independent.

Reason: matching accounting over the same simulated fills establishes internal
consistency, not realistic execution quality, edge, or expected performance.
Keeping that boundary in the artifact prevents a descriptive PnL view from
quietly becoming selection or profitability evidence.

## 2026-07-18 - Tiingo raw-D1 source sensitivity remains non-independent

Decision: accept `raw-d1-tiingo-source-sensitivity-20260718-r1` only as one
hash-bound, retrospective, development-only source representation check. It
reused the six fixed r2 checkpoints on CPU, trained zero models, executed 36
local-paper cells, and finished each flat. Its summary SHA-256 is
`2e91c133fd12e0e28a7011eb0c1d3f661fe0fffab094ab00b679d3a566a14ff3`.
The raw-D1 loader pins the compressed dataset hash and verifies its decompressed
canonical CSV against the attested parent Tiingo bytes, preserving content
integrity across Windows and Docker gzip implementations.

Across the corresponding r2 explicit-event cells, decision count, trade count,
and after-cost-PnL sign did not change. This does not reverse the parent
factor-sensitivity verdict: the raw-D1 data shares r2's observed-session
calendar and is not independent validation. It cannot rank, select, promote,
open a holdout, support profitability, or trigger new GPU training.

Reason: the check falsifies only a narrow bar-source representation concern
while retaining the original calendar and all frozen model inputs. A broader,
explicitly scoped development dataset is more valuable than extending this
fixed-ETF campaign or adding a new report/gate layer.

## 2026-07-18 - Broad Yahoo daily reference is development-only

Decision: accept exactly one static, hash-bound broad-Yahoo daily reference for
predeclared `SPY`, `QQQ`, and `IWM`. It pins the `2026-06-23` canonical gzip and
manifest, exposes only their common session window beginning `2000-05-26`, and
returns a dedicated development-universe wrapper rather than a campaign-ready
input. It is explicitly inception-truncated and survivor-selected; PIT
membership, delisting coverage, and raw corporate-action semantics remain
unproven. It cannot justify training, campaign replay, paper trading, ranking,
holdout, promotion, or profitability claims.

Reason: the snapshot gives a reproducible read-only feature-development input
without pretending that current screener membership represents historical
membership. The narrow wrapper preserves byte lineage and prevents accidental
direct use by existing campaign APIs without adding a provider framework,
registry, artifact family, scheduler, or data gate.

## 2026-07-18 - Development-only daily features stay behind Data reattestation

Decision: the broad-Yahoo wrapper may feed exactly one in-memory Engine feature
materializer through a Data-owned reattestation path. The raw parser accepts
only Data-module callers; the materializer is the sole allowlisted external
consumer. It returns five-session and one-session raw-close returns,
same-session high/low range, and one-session volume change after completed
session close, preserving the source wrapper, hash, and limitations. It cannot
create labels, scores, candidates, artifacts, campaign inputs, paper orders, or
profitability claims.

Reason: that makes an exploratory feature substrate reproducible and
no-lookahead without treating a survivor-selected, raw-corporate-action-unknown
source as execution or model-selection evidence. Tests cover chronological
alignment, immutable result metadata, future OHLCV isolation, source tampering,
and attempted `CatalogedBars` or direct raw-parser bypasses.

## 2026-07-18 - Development-only outcomes remain explicit future evidence

Decision: keep next-observed-session outcomes inside the existing allowlisted
feature module rather than opening another raw-bar accessor. Before deriving an
outcome, it re-attests the fixed source and recomputes the canonical feature
result. Each immutable row pairs a feature at completed session `t` with
`raw_close(next observed session) / raw_close(t) - 1`, records the future
session and calendar-day gap, and omits terminal feature rows. The outcome has
its own raw-corporate-action limitation and cannot serve as a decision, campaign
input, paper order, ranking, promotion, or profitability claim.

Reason: explicit timing prevents a future label from appearing as an available
feature, while using the existing trusted-module boundary avoids another raw
input API. Tests reject forged/tampered source state and generic stream access,
verify all fixed symbols against future OHLCV changes, and preserve the
`CatalogedBars` campaign boundary.

## 2026-07-18 - Full-history Tiingo evidence stays descriptive

Decision: accept one immutable Tiingo standard-EOD full-history record for
`SPY`, `QQQ`, and `IWM`, queried from `1900-01-01` through confirmed session
`2026-07-10`. Its raw response hashes, normalized hash, coverage, and
`divCash`/`splitFactor` fields are offline-attested outside Git. The loader
rejects redirects before an authorization header can be forwarded, requires each
response to reach its confirmed `source_as_of`, and requires common coverage
after all three instruments exist.

This record is development evidence only. It does not establish point-in-time
membership, delisting coverage, source independence, ranking, holdout validity,
campaign eligibility, paper-trading eligibility, model selection, or profit.

Reason: a frozen retrieval improves reproducibility and makes a bounded raw
source-alignment check possible without pretending that one provider's present
history solves survivorship, execution, or model-quality questions.

## 2026-07-18 - Exact raw source alignment is unsupported

Decision: do not add a reusable cross-source alignment helper, tolerance,
normalization, rescale, source preference, or derived artifact. A read-only,
loader-attested smoke compared the r2 Yahoo-lineage raw snapshot
`sha256:3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e`
with the full-history Tiingo snapshot
`sha256:9ee21b6d955320b3855955b2072749e239b4b15e382dfbb6521e18f6f41a0016`.

For the predeclared Tiingo-side latest 60 common sessions with `divCash=0` and
`splitFactor=1`, every symbol had a difference in at least one raw OHLCV field
on all 60 sessions. Exact `Decimal` matches in `open/high/low/close/volume`
were `1/2/3/2/1` for IWM, `1/2/4/2/0` for QQQ, and `6/1/4/2/0` for SPY.
This is an exact representation observation only; it does not establish either
source's correctness, adjustment semantics, interchangeability, independence,
PIT validity, execution quality, or profitability.

Reason: adding a post-hoc tolerance after this falsifier would turn the check
into a way to rationalize provider differences. Preserve both immutable inputs
and move to an independent, bounded engine-loop task instead.

## 2026-07-18 - Intraday baseline keeps decision and execution timeframes separate

Decision: accept one offline, local-paper-only pipeline smoke for a Data-attested
1-minute stream. For each supported `1m`/`5m`/`10m`/`1h`/`3h` bar, the first
complete resampled bar with two following contiguous 1-minute bars is a
deterministic decision input; the two 1-minute bars perform the local-paper
entry and flatten. Each timeframe uses an isolated event store and must have
exactly two `source: local_paper` fills plus a replayed flat final position.

The result exposes source identity, counts, timing identity, fill-source
verification, and terminal position only. It creates no PnL result, candidate,
campaign, model artifact, ranking, holdout, or profitability claim. Temporary
work is discarded by default; durable event evidence requires an explicit root
outside Git.

The read-only smoke re-attested
`us_equities.yahoo_intraday_starter.1m.snapshot=2026-07-09-shadow-t0-8d-probe`
with dataset hash
`sha256:8a21be83e26ffad950a0b8a37a37c349d4c57de5526f52ff13103cf26c659bd6`.
CVS, FCX, and KO completed all five timeframe cells with two local-paper fills
and flat replayed positions; no persistent artifact was needed.

Reason: the existing generic validator requires same-timeframe contiguous
execution and would either reject normal session gaps or tempt the system to
invent higher-timeframe execution bars. Keeping completed-bar decisions and
next-bar 1-minute execution explicit preserves timing while remaining a narrow
pipeline smoke.

## 2026-07-19 - Tiingo IEX r1 records the returned window, not requested history

Decision: accept one immutable private-use Tiingo IEX 5-minute snapshot for
fixed SPY/QQQ/IWM as Data-owned descriptive evidence only. The operator-approved
`TIINGO_API_TOKEN` was used for exactly three fixed HTTPS requests with
`resampleFreq=5min`, explicit OHLCV columns, `afterHours=false`, and
`forceFill=false`; no other credential, KIS call, order, GPU, model, campaign,
or paper path was used. The external snapshot is
`fixed_etf_intraday/canonical/tiingo_iex_5m/snapshot=2026-07-19-tiingo-iex-5m-r1`
with dataset hash
`sha256:1531d803fb259c5f2233cc1b5f94441eb52bab9f31938232644879cc4aa1fcb6` and
manifest hash
`sha256:a1dee1cddf12e22b9448806094ce6fbbcc6aa16ed13719ab720f3e9fbd1d3ab8`.

This is a separate, narrow IEX authority alongside the earlier standard-EOD
authority, not a broad Tiingo-product or credential authorization. For the
current next goal it permits only the one or two exact IEX scope probes named
in `NEXT_CODEX_GOAL.md`; it does not authorize paid upgrades, redistribution,
other Tiingo endpoints, other `.env` keys, KIS, or any order/capital action.

Although the query requested 2017-08-01 through 2026-07-10, each response
contained its newest 10,000 bars, yielding only 129 common New York sessions
from 2026-01-13 through 2026-07-10. The manifest preserves both requested and
actual coverage. Do not label r1 as full history or infer that an earlier range
is unavailable; the next bounded Data question is whether an explicitly older
window returns non-overlapping bytes. Do not overwrite r1.

The loader retains raw response hashes, canonical gzip and manifest hashes,
rejects redirects, Git destinations, symlinks, overwrite, bad OHLCV, duplicate
or unordered timestamps, non-5-minute or out-of-session timestamps, low disk
space, and tampering. It reattests offline, but deliberately returns a separate
snapshot object rather than `CatalogedBars`, `MarketDataProvider`, campaign, or
local-paper input. IEX-only volume is not consolidated volume; timestamp
boundary semantics, adjustments, corporate actions, PIT membership,
independence, execution quality, ranking, promotion, and profitability remain
unsupported.

Claude CLI was unavailable because it was not logged in. A temporary Review
Agent supplied a `supported with limits` check; that review was a drift brake,
not an approval.

Reason: this gives the engine a replayable, hash-bound intraday source without
quietly turning a provider-limited response into a market-wide performance or
execution claim. Preserving the cap makes a later chunking decision evidence-led
rather than an unbounded download loop.

## 2026-07-19 - Tiingo IEX date-window access supports a bounded archive attempt

Decision: accept the nonpersistent SPY scope probe as `windowed access
supported`. The exact 2024-01-02 through 2024-06-28 request returned HTTP 200,
10,000 rows, fields `date/open/high/low/close/volume`, first timestamp
`2024-01-02T19:40:00Z`, and last timestamp `2024-06-28T19:55:00Z`. It did not
write raw bytes, a hash, cache, artifact, or snapshot. The response is
non-overlapping with r1, so Tiingo IEX honors the historical date window for
this bounded observation.

This does not prove the provider's cap contract or complete requested-window
coverage: it again returned exactly 10,000 rows and began partway through its
first session. The next Data objective is therefore one predeclared archive of
the disjoint 2017-08-01 through 2026-01-12 period, using 21 five-calendar-month
windows, three fixed ETFs, 63 exact requests in three 21-request batches, and
an estimated external footprint below 90 MiB. Any chunk reaching 10,000 rows,
returning an out-of-window session, or failing source validation must fail the
archive rather than silently entering it.

This supersedes the prior entry's current-goal IEX probe wording only: the
operator-approved token may now be read solely for those predeclared archive
requests, through the same safe reader. It still does not authorize another
Tiingo product, paid upgrade, redistribution, other credential, KIS, order,
capital, model, campaign, paper, GPU, or live activity. R1 remains immutable
and separate.

Reason: one date-filtered observation is enough to replace an availability
guess with a bounded archive plan, but not enough to justify an unbounded
historical download or a research-quality claim.

## 2026-07-19 - Strict Tiingo IEX pre-r1 archive stops without publication

Decision: retain the bounded r2 chunked archive contract and its strict `Bar`
validation, but close the exact 2017-08-01 through 2026-01-12 Tiingo IEX
retrieval plan after its permitted validation-related retries. Do not retry it
automatically, relax high/low containment, repair/fill a rejected source bar,
or create a partial snapshot.

The first archive attempt rejected an unreproducible SPY OHLCV row in the first
window. A nonpersistent exact-window probe subsequently returned
8,502/8,501/8,502 SPY/QQQ/IWM rows with no simple OHLC violation and retained
no bytes. The final permitted attempt later rejected SPY
`2018-04-25T15:25:00Z` because high/low did not contain open and close. No raw
response, cache, hash, artifact, final r2 directory, or staging directory was
retained.

Reason: accepting, altering, or silently dropping a malformed source bar would
make the archive look complete while breaking its raw-to-canonical attestation.
The outcome does not prove a provider defect, complete-history absence, source
reliability, or any research, validation, campaign, paper, or profitability
claim. A later long-history requirement needs a newly approved source plan.

## 2026-07-19 - Norgate trial is the smallest public-evidence PIT candidate

Decision: make no purchase and add no provider. The official-public comparison
selects Norgate US Stocks Platinum only as the smallest **trial candidate with
public price and footprint** for the present daily PIT research blocker. Its
six-month price is USD 346.50; it documents delisted securities, historical
index membership, major-exchange listing identification, daily price/volume,
and corporate-action indicators. Its published US Platinum footprint is a 2 GB
download and 9.1 GB on disk, which remains well above the local 20 percent
warning and 15 percent stop thresholds at the observed 40.60 percent free space
on `D:`.

The source has material constraints: membership is provided as a per-date
plugin answer rather than raw constituent lists, the database is proprietary
and Windows-oriented, Python support is Windows-only, and the personal-use
EULA prohibits redistribution and requires deletion of Data and Derived Data
when a subscription lapses. A free three-week trial is therefore the next
operator decision, not a data acquisition authorization. It must verify the
actual Python fields, unadjusted OHLCV export, corporate-action lineage,
per-date membership semantics, and licensed host-to-Docker boundary before any
separate purchase question.

Sharadar is not selected for the trial, but it is not absent: its official `SEP`
page documents daily US listed/delisted OHLCV from 1998, adjusted/unadjusted
prices, corporate-action, ticker-change, and delisting-reason fields, plus
Tables API and bulk export. The current price is login-gated, and the public
evidence reviewed does not establish historical index or per-date exchange
membership, a storage estimate, or personal-use rights. SEP therefore resolves
part of the blocker but cannot be treated as a decision-ready complete PIT
universe source without a vendor conversation.

Reason: selecting a source with verified coverage and constraints is more
valuable than extending model work on survivor-selected evidence. Recording one
trial decision avoids both a paid-data leap and a new provider/gate/report
framework.

## 2026-07-19 - Norgate trial is compatibility-only

Decision: record the operator-created Norgate US Stocks Platinum trial as a
Windows/Python compatibility result only. The operator selected
`D:\market_data\us_equities\norgate_us_platinum_trial` and ran an update; the
directory then held 429 files / 6.12 GiB and had a later file time than the
retained C: copy. Preserve the C: copy. Do not treat this as proof that D: is
the sole active database or that cleanup is safe.

Bounded local `norgatedata==1.0.77` queries exposed daily OHLCV, Turnover,
Unadjusted Close, Dividend, Index Constituent, Major Exchange Listed, and
Capital Event fields. Short membership/listing requests obeyed the requested
range. `capital_event_timeseries` returned the wider trial horizon despite a
short-range request, so future consumers must explicitly clip results and its
date-filter contract remains unproven. The trial's observed history is about
two years. A Docker `engine` runtime probe listed 166 top-level files through
the D: directory's `ro` market-data mount, but that is only a technical mount
fact, not a licensed container database or export boundary.

Claude's falsification-first review returned `supported-with-limits` for this
compatibility claim. It does not establish point-in-time universe correctness,
source correctness, event timing/lineage, long-history coverage, provider
integration, campaign eligibility, paper use, or a case for purchase. No
provider, cache, `CatalogedBars` path, raw export, artifact, model, GPU job,
KIS action, or order path is created.

Reason: connector availability and field names are useful evidence, but treating
them as historical semantics would reintroduce leakage and survivorship risk.
One known-fixture semantics check is the next bounded question; it is not a
subscription decision.

## 2026-07-19 - Norgate fixture observations remain date-scoped

Decision: retain only two limited local observations. A tight `PLTR` historical
membership request returned its requested `2024-09-18` through `2024-09-27`
window and changed `Index Constituent` from false to true on `2024-09-23`, the
date S&P DJI made the addition effective before the open. A tight `SMCI`
capital-event request ignored its requested `2024-09-26` through `2024-10-04`
range and returned the full observed trial horizon; after an explicit in-memory
clip, its seven requested-window rows contained one `Capital Event` marker on
`2024-09-30`. That matches the issuer's stated split-effective date, while
split-adjusted trading began on `2024-10-01`.

Claude's falsification review returned `supported-with-limits` for those literal
date observations only. The capital-event marker must not be treated as the
price-adjustment date, ex-date, event availability time, event type, or ratio.
The next bounded check compares the marker with the local `Close` to
`Unadjusted Close` ratio transition across the same window. A mismatch or an
ambiguous transition remains `unsupported` rather than an invitation to repair
or reinterpret source data.

Reason: the membership fixture corroborates one observed per-date transition, but
the SMCI effective-after-close versus next-session trading distinction is exactly
where a superficially matching event marker can leak future information. Neither
fixture establishes PIT availability, universe completeness, delistings, general
corporate-action lineage, a provider contract, campaign eligibility, or a
purchase decision.

## 2026-07-19 - Norgate capital-event timing is non-actionable by default

Decision: record one more literal `SMCI` stored-field observation and add no
consumer code. A `2024-09-27` through `2024-10-02` daily price request returned
four ordered, non-duplicate rows. Its derived `Close`/`Unadjusted Close` ratio
changed only on `2024-10-01`. The corresponding capital-event request again
returned 501 rows across the wider trial horizon; explicit in-memory clipping
left four rows with one nonzero `Capital Event` marker on `2024-09-30`. The
issuer states that its 10-for-1 split became effective after the close on
`2024-09-30` and split-adjusted trading began `2024-10-01`.

Claude's falsification review returned `supported-with-limits` for the literal
one-session ordering only. The conservative operational consequence is a
prohibition: a capital-event marker cannot be assumed to be the local
price-ratio-transition date or a same-session actionable signal without a
separate source-timestamp contract. It does not claim when Norgate populated
the marker, that all events lag by one session, or that the ratio isolates
split adjustment.

The next bounded question may inspect the existing query signature and public
setting documentation, then classify the one observed ratio-change magnitude
against the issuer's 10-for-1 split without changing any local Norgate setting.
If those facts do not establish the field meaning, record `unsupported` and
stop this semantic branch rather than infer a general convention.

Reason: the stored marker and ratio transition differ on the very fixture where
the issuer's after-close effective time matters. Refusing same-session use is a
safe limitation, whereas generalizing the lag or price-field semantics would
create an unmeasured leakage surface.

## 2026-07-19 - Norgate split-field meaning remains unsupported

Decision: close the bounded Norgate semantics branch without mutating a local
setting or adding consumer code. The local `price_timeseries` signature exposes
query-level `stock_price_adjustment_setting` and `padding_setting`; its observed
default argument is `StockPriceAdjustmentType.TOTALRETURN`, with `CAPITAL`,
`CAPITALSPECIAL`, `NONE`, and `TOTALRETURN` enum members. Under that unchanged
call behavior, the four-row `SMCI` window's `Close`/`Unadjusted Close` ratio
transition category was tenfold on `2024-10-01`, consistent with the issuer's
10-for-1 split and the prior marker-then-ratio ordering.

Official Norgate material says price adjustment is configurable, capital
reconstructions include splits, and pre-ex-date prices are adjusted by the
previous/new share ratio when that adjustment is selected. It also labels
`Capital Event` as effective for holding at the close on the day before an
ex-date. Claude returned `supported-with-limits` only for the literal
magnitude-consistency observation. The evidence does not bind Python
`TOTALRETURN` to the cited UI semantics, show that the ratio isolates splits
from dividends or other adjustments, establish source timestamps, or support a
general rule.

Reason: further semantic resolution would require changing a local setting or
widening fixtures, neither of which is justified by this trial question. The
branch is therefore `unsupported` for provider/campaign field meaning. A future
load-bearing use must reopen it under its own bounded data contract.

## 2026-07-19 - GPU research uses finite eligibility-driven batches

Decision: reduce avoidable GPU idle time only with a finite, pre-enumerated
research batch whose dataset is hash-bound and explicitly development-training
eligible and whose campaign contract fixes target, costs, temporal split,
metrics, and stop rules. This does not authorize a job today.

When eligible, breadth runs CPU naive/linear/tree baselines plus compact
PyTorch MLP and TCN candidates with two fixed seeds each, serially on the one
GPU. Depth admits at most two candidates with three seeds only after temporal
sensitivity and a Claude challenge. Ensemble work requires independent
out-of-fold predictions and starts with equal-weight probability averaging and
disagreement abstention. CPU may prepare the already-enumerated batch while the
GPU runs. No daemon, scheduler, automatic refill, sealed-holdout tuning,
untrusted-weight loading, or execution-process model loading is allowed. Idle
is the default when those preconditions are absent or paper reliability needs
the resources.

Reason: Claude's `supported-with-limits` drift review found the mechanics
consistent with existing safety boundaries, but warned that a generic
`keep one GPU occupied` rule would become queue-depth pressure. This policy
therefore records prohibitions and finite activation conditions rather than a
utilization target. The current RAW D1, broad Yahoo, Tiingo IEX, and Norgate
trial observations do not open this batch.

## 2026-07-19 - Norgate raw-daily access stays host-only and non-cataloged

Decision: add one `NorgateRawDailyBarProvider` behind the existing
`MarketDataProvider` shape. It is Windows-host-only, accepts only bounded US
`1d` UTC-midnight queries, lazy-loads the optional official package, and calls
`price_timeseries` with query-local `StockPriceAdjustmentType.NONE`,
`PaddingType.NONE`, and an explicit `numpy-recarray` response. It maps only
`Date`/OHLCV to existing `Bar` values in process and rejects malformed,
out-of-window, or unordered responses rather than repair or persistence.

The host smoke used an ephemeral official `norgatedata==1.0.77` dependency and
returned four validated `SPY` bars for `2024-09-27` through exclusive
`2024-10-03`; no raw row, price, cache, artifact, dataset, or project dependency
was retained. Claude's architecture review and an independent static review
both returned `supported-with-limits`. The adapter's date label is an engine
convention, not a source timestamp fact. It does not establish field semantics,
PIT correctness, a Norgate export right, a catalog, campaign eligibility,
model quality, paper use, or a purchase decision.

Reason: a minimal raw-D1 seam is needed to test the installed trial without
turning proprietary local data into a Docker bridge or a prematurely promoted
research source. A later historical-universe question must be its own bounded
contract before any extraction or model work.

## 2026-07-19 - Norgate has no direct historical-universe list API

Decision: close the bounded Norgate direct-enumeration branch as
`unsupported`. Official package documentation describes
`index_constituent_timeseries(symbol, indexname, ...)` as a per-symbol
membership series, while `watchlist_symbols(watchlistname)` and
`database_symbols(databasename)` have no as-of parameter. Local
`norgatedata==1.0.77` signatures match those shapes.

Two permitted in-memory host calls corroborated the contract without retaining
source data: `S&P 500 Current & Past` produced a 541-item list with no as-of
input, and a bounded PLTR membership request for 2024-09-23 through 2024-09-24
produced a two-row `Date`/`Index Constituent` recarray inside the requested
window. This validates only list-versus-per-symbol API shape. It does not prove
membership publication time, complete historical constituents, delisting
coverage, exact effective timestamps, a direct historical-list source, or
model/PIT eligibility.

Claude returned `unsupported` for the direct-list claim; the independent Data
review agreed on the function shapes. Do not add a scraper, export, inferred
universe, or convenience adapter to evade this conclusion. A future fixed
candidate-union plus per-symbol membership **matrix** is a distinct source
construction and needs its own bounded contract, source hashes, retention
rules, and leakage review.

Reason: confusing a union list with an as-of universe recreates survivorship
bias at the data boundary. Preserving the two documented primitives separately
leaves a testable path without pretending the vendor exposes a stronger API.

## 2026-07-19 - Norgate membership matrix remains source evidence only

Decision: retain one host-only external snapshot at
`D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`.
It has a deterministic 541-item `S&P 500 Current & Past` candidate union and
266,647 sparse per-symbol/date membership rows from 2024-07-18 through
2026-07-17. The matrix SHA-256 is
`d28060bfa5d81f913edc6d3500a46b7fdbc6bd00c8746e39068894b036758b55`; the
manifest SHA-256 is
`1bbf0ac04b653605b32496e09f0b6728f250b54f149f2f28858bef5ca32f5d8a`.
The package was the ephemeral host-only `norgatedata==1.0.77`; D: had 40.44%
free space before and after construction. The external snapshot includes its
own EULA deletion marker and no staging directory remains.

The manifest records `pit_eligible=false`, `campaign_eligible=false`, and
`model_eligible=false`. A missing sparse row is not interpreted as false
membership, the union count is only an observed tripwire, and the source gives
no membership publication-time proof. Claude returned `supported-with-limits`
for this limited construction, not for a historical universe or research claim.
No Docker bridge, provider/catalog, raw-price extraction, campaign, GPU job,
paper order, or service was added.

Reason: this preserves the vendor's actual two-part source shape and its
retention obligation without silently turning a convenience union into a
survivorship-safe universe or model input.

## 2026-07-19 - Norgate raw-D1 alignment does not select a source

Decision: retain one bounded host-only raw-D1 alignment snapshot at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_raw_d1_alignment\snapshot=2026-07-18-norgate-raw-d1-alignment-r1`.
It queried `SPY`/`QQQ`/`IWM` from 2022-11-22 through 2026-06-22 with Norgate
query-local `NONE` adjustment, `NONE` padding, and `numpy-recarray`, then
compared raw OHLCV decimals against the existing hash-pinned Tiingo raw-D1
loader. Dataset SHA-256 is
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993`; manifest
SHA-256 is `c37ca34c02df84ebd3f7d684ad87f27c62e36607d8f7ca3751504115205c6a91`.

The result is `literal_raw_ohlcv_difference`. Norgate returned 483 sessions
per ETF, from 2024-07-18 through 2026-06-22; Tiingo has 896 sessions and 413
additional earlier sessions per ETF. There are no Norgate-only sessions. On
the common sessions, all five OHLCV fields matched on 96 `SPY`, 111 `QQQ`, and
201 `IWM` sessions. Open and close matched for every common session, but high,
low, and especially volume counts differ. This is not evidence that either
source is preferable or that either is incorrect.

Claude returned `supported-with-limits`: an equality or difference count can
describe the representations but cannot prove adjustment semantics, timing,
PIT correctness, or training eligibility. The snapshot's external marker and
manifest prohibit source preference, campaign, model, paper, and PIT use. No
Docker client, provider/catalog, campaign, GPU job, KIS action, or live/paper
order was added.

Reason: the source terms called raw are provider-defined and the Norgate return
coverage is shorter. Treating observed differences as a winner would be a
source-selection claim unsupported by this experiment.

## 2026-07-19 - Norgate trial history is an entitlement limit

Decision: close the fixed-ETF Norgate daily-history audit as `supported` for
the local trial's available price coverage. Nine bounded host-only `NONE` /
`NONE` / `numpy-recarray` calls across the three fixed symbols returned zero
rows for `2000-01-03` through `2022-07-17` and `2022-07-18` through
`2024-07-17`, then 483 rows each from `2024-07-18` through `2026-06-22`.
The response fields were stable and no call failed. No raw row, cache, export,
or new external artifact was retained.

Official [trial terms](https://norgatedata.com/subscribe/freetrial.php) say US
Platinum trial daily price history is limited to two years; the public
[trial page](https://norgatedata.com/freetrial.php) and
[FAQ](https://norgatedata.com/faq.php) say the same. The observed boundary is
therefore consistent with the entitlement, not evidence of a query defect or a
local NDU setting that Codex should change. Official subscription material lists
longer US history by paid tier, which is an operator cost decision.

Reason: retrying with changed settings or repeatedly sampling older windows
cannot create trial entitlement and would consume time without improving an
engine loop. Keep the trial's current two-year local facts; pursue no-cost,
approved alternatives before proposing any purchase.

## 2026-07-19 - Tiingo broad-data expansion starts with a capped pilot

Decision: retain the completed Tiingo standard-EOD coverage probe as technical
reachability evidence only, and expand next through one deterministic,
30-symbol raw-daily acquisition pilot rather than a 541-symbol automatic pull.
The probe queried 2024-07-18 through 2026-07-17, issued exactly 12 requests,
recorded 11 nonempty HTTP-200 responses plus one HTTP-404, and persisted no
selected symbols, raw rows, prices, volumes, or token. Its metadata-only
summary is under
`D:\thericher-v2\model-artifacts\data-agent\tiingo-eod-coverage-probe\snapshot=2026-07-18-tiingo-eod-coverage-probe-r1\summary.json`, SHA-256
`4b2ef16520fdd530ae7cf6bbadc9dbe46cd9526670d859c2484097d3def9fce0`.

Current official [Tiingo terms](https://app.tiingo.com/tos/) and
[general API documentation](https://www.tiingo.com/documentation/general) allow
the operator's internal personal use and prohibit redistribution. Public
[Starter pricing](https://www.tiingo.com/about/pricing) lists 500 unique symbols
per month, below the external Norgate union's 541 candidates. The pilot therefore
uses a deterministic subset, records unavailable requests as gaps without proxy
or ticker substitution, and writes exact external source evidence only under
`D:\market_data`. It cannot infer membership, point-in-time availability,
source completeness, or a tradable historical universe.

Claude returned `supported-with-limits`: 12/541 is only a small technical
sample, and the direction reverses if published terms disallow the retention
pattern or if observed gap/rate behavior makes the bounded pass unreliable.
No model, GPU, campaign, paper, broker, or source-selection authority opens
from this decision.

Reason: a small raw-data pilot validates the real acquisition contract and
protects the free-tier limit before a larger private dataset is retained. It
advances the data loop without turning a date-less candidate union into a
survivorship-safe research universe.

## 2026-07-19 - First Tiingo raw-daily pilot remains source evidence

Decision: retain the completed 30-request Tiingo standard-EOD raw-daily pilot
at `D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r1` as private-use source evidence
only. It completed without retry at `2026-07-18T21:04:10.820971Z`, retained 29
available raw responses and one HTTP-404 gap, and produced 13,724 canonical
raw-field rows. Dataset SHA-256 is
`ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56`; manifest
SHA-256 is `69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f`.
The snapshot includes the hash-attested Tiingo private-internal-use marker
required by the reviewed retention contract.

The 29 available candidates have 18 common returned sessions, while individual
histories range from 18 to 501 rows. This is insufficient for a common-panel,
point-in-time, campaign, model, GPU, paper, source-selection, or profitability
claim. The next reversible step is one separately bounded, disjoint 30-symbol
shard, not a scheduler or automatic bulk pull.

Reason: successful transport and raw provenance prove the acquisition mechanics
but do not solve survivorship, publication-time, listing-history, or common
coverage limitations. Preserving those limits avoids using GPU work to create a
misleading research result.

## 2026-07-19 - Tiingo r2 shard improves coverage but not eligibility

Decision: retain the completed, r1-bound Tiingo standard-EOD r2 shard at
`D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r2` as private-use source evidence only.
It re-attested r1 before selection, excluded all 30 predecessor ranks, enforced
one hour of pacing, issued exactly 30 requests with no retry, and retained 29
available raw responses plus one HTTP-404 gap. Dataset SHA-256 is
`6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`; manifest
SHA-256 is `76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
The r2 snapshot contains 14,529 canonical raw-field rows and its 29 available
candidates share 501 returned sessions.

R2 does not repair the date-less candidate union, historical membership,
publication-time, listing-history, or delisting limitations. R1 and R2 together
have 58 available candidates but only 18 common sessions because the r1 returns
are uneven. Neither snapshot, separately or combined, is a point-in-time,
campaign, model, GPU, paper, source-selection, or profitability input. The
next step is a bounded offline coverage audit, not automatic collection.

Reason: the second shard proves that some rank regions have consistent returned
history, which is useful data-coverage evidence. It does not validate a
tradable universe or justify consuming GPU capacity for a misleading model run.

## 2026-07-19 - Tiingo aggregate audit defers a third coverage shard

Decision: retain one offline, aggregate-only audit at
`D:\thericher-v2\model-artifacts\data-agent\tiingo-daily-coverage-audit\snapshot=2026-07-18-tiingo-daily-coverage-audit-r1\summary.json`,
SHA-256 `e81ed382b9a68b0430a680c2c762a692822370a5a30cc96d21174065da0abb0c`.
It re-attested the two exact raw/canonical/rights snapshots without a token,
network, broker, Docker, or credential read. R1 has 18 common returned
sessions, R2 has 501, their combined intersection remains 18, and 56 existing
candidate groups cover the R2 returned window.

Defer a third Tiingo shard when its only proposed value is raising the combined
common-session floor: adding candidates cannot increase an existing
intersection, and the short-history R1 group is binding. The 56-group filter
is a private descriptive observation only, not a point-in-time universe,
campaign, model, GPU, paper, source-selection, or profitability input.

Reason: the audit resolves a concrete acquisition question using existing
evidence and avoids spending source quota or GPU time on an invalid inference.
The next data question is whether the already-installed Norgate trial can
produce a separately bounded fixed-ETF raw-D1 development source; it must not
merge these Tiingo snapshots into a model dataset by implication.

## 2026-07-19 - Norgate fixed-ETF trial raw-D1 is development-source evidence only

Decision: retain the host-only fixed `SPY`/`QQQ`/`IWM` Norgate trial snapshot
at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\snapshot=2026-07-18-norgate-trial-raw-d1-r2`.
It contains 1,449 raw OHLCV rows over 483 common sessions from 2024-07-18
through 2026-06-22. The data SHA-256 is
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993`; the
manifest SHA-256 is
`5c8a5f06e618aaf3ec0ee7dc58ec9f545839fbfc87dc5476d52a8b4b4602458c`.
The immutable external directory includes raw data, conservative exclusion
metadata, hashes, and a trial-lapse deletion marker. The source build used
ephemeral `norgatedata==1.0.77`, without a project dependency, network data
API, credential read, broker call, Docker query, or Git-resident data.

The manifest records `NONE` only as a requested stock-price adjustment setting.
It explicitly clips a range-padded capital-event response and observed zero
nonzero markers, neither of which establishes adjustment semantics or absence
of events. Claude's falsification-first verdict was `supported-with-limits`.
Therefore r2 is only development-source evidence: all training, model, GPU,
campaign, point-in-time, paper, ranking, and source-preference eligibility
remain false. Preserve r1 as superseded recovery evidence rather than editing
or deleting it. The only next semantic action is one bounded field-level probe
that may refine conservative exclusions; it cannot promote this source.

Reason: the snapshot gives Data a reproducible local source fact while keeping
unknown corporate-action and adjustment behavior out of research conclusions.

## 2026-07-19 - Norgate dividend markers are exclusion-only sidecar evidence

Decision: retain one immutable, external sidecar at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\dividend_marker_exclusions\snapshot=2026-07-18-norgate-trial-raw-d1-r3-dividend-exclusions-r1`.
It re-attests the exact r2 parent dataset hash
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993` and r2
manifest hash `5c8a5f06e618aaf3ec0ee7dc58ec9f545839fbfc87dc5476d52a8b4b4602458c`.
The sidecar manifest SHA-256 is
`d5de2b77d02e4f7eb5b84392b8b5287b319c9218c034aa9e9613d80c57b4dd3c`.

One bounded host-only `price_timeseries` probe with requested `NONE` adjustment
and `NONE` padding returned an exact 483-session `Dividend` field response for
each fixed ETF. Each had eight nonzero source markers, yielding 24 total
markers and 71 marker-plus-adjacent observed-session exclusions. The sidecar
stores marker-derived exclusions and a deletion marker, not dividend amounts or
raw rows.

Claude's pre-probe verdict was `uncertain`: it required exact parent-session
coverage and at least one nonzero marker for every fixed symbol, otherwise r2
had to remain unchanged. The measured response met that condition. This does
not establish event time, ex-date, payment date, adjustment semantics,
point-in-time availability, completeness, or absence of unmarked events.
Therefore r3 is exclusion metadata only and does not change any training,
model, GPU, campaign, PIT, paper, ranking, or source-preference eligibility.

Reason: excluding a source marker plus neighboring observed sessions is a
conservative, low-blast-radius operation while keeping all economic and timing
interpretations out of the engine.

## 2026-07-19 - Norgate broad panel is development-training evidence only

Decision: retain one externally stored, static Norgate raw-D1 panel at
`D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
It re-attests the fixed 541-item candidate-union/membership snapshot and the
fixed-ETF r2 calendar parent, then preserves raw OHLCV only for the 523
candidates whose responses exactly match all 483 returned sessions from
2024-07-18 through 2026-06-22. The remaining 18 candidates are recorded as
session mismatches without repair, substitution, or source merge. The data hash
is `sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`; the
manifest hash is
`sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.

Claude's falsification-first verdict was `supported-with-limits`. The candidate
union is date-less, the static exact-session selection is survivorship and
availability selected, the 100-symbol threshold is operational rather than a
coverage or quality proof, and requested `NONE` adjustment semantics remain
unverified. Accordingly, the panel's sole positive flag is
`development_training_eligible` for later engineering preparation. It is not
membership, point-in-time, adjustment, source-preference, campaign, model, GPU,
ranking, holdout, paper, or profitability evidence.

Reason: a reproducible, broad, locally available development substrate is more
useful than idling research indefinitely, while explicitly isolating the known
survivorship and corporate-action limitations from model-selection and capital
decisions. A later model target must re-attest this exact lineage, freeze target
timing, temporal splits, costs, baselines, and stop rules before any CUDA run.

## 2026-07-19 - Static-panel CUDA result is partial engineering evidence only

Decision: close the first static Norgate engineering loop as two completed MLP
jobs and two compute-rejected, untested TCN jobs. The verified feature artifact
is `D:\thericher-v2\model-artifacts\norgate-broad-development-features\r2-3c1b21bde92e4623`
with data hash `sha256:3f03d6cdc669e174c7cc1c79edb0921d1781f79e364302df88a38d6a314e72e7`
and contract hash
`sha256:29fca05b61c9702967b59c66ac60a8b8a06de73b309b9e292b64a544b059779a`.
The r3 CPU linear date-mean accuracy was `0.50269`; MLP seeds 71 and 113 were
`0.49865` and `0.50028`. Neither was strong or selected.

The TCN is not judged ineffective. Two bounded attempts for seed 71 produced no
checkpoint, predictions, or summary before manual stop after observed lower
bounds of 904 and 1,252 seconds. The first static batch therefore is not a
four-model comparison. The external r3
`cuda/temporal-conv-compute-rejection.json`, SHA-256
`7ffe6db283af7a1c5287614967342c036f29d8eb9b0ab80c08254bb3a34cb3bc`, records
the untested resource classification. TCN seed 113 was not started.

Claude's `supported-with-limits` review permits closing the static work only
with that wording. Future TCN work begins with a harness diagnosis and CUDA
preflight on a verified future dataset; it must not use these stops as a
performance or model-quality result. No seed expansion, model selection,
ensemble, PnL, paper, or live authority opens.

Reason: the panel remains survivor/availability conditioned with unresolved
raw-adjustment and corporate-action semantics. Additional model variants would
compound selection bias without adding a valid decision boundary.

## 2026-07-19 - Docker permits verified external data mounts only

Decision: retain the existing Git-boundary protection for market-data snapshots,
with one read-only verification exception: a market-data root physically nested
under a container repository path is accepted only when that root itself is an
OS mount point. This allows the configured D: bind mount at `/app/market_data`
to reattest in Docker without treating an ordinary Git subdirectory as external
data. Non-mount nested paths remain rejected and the artifact root remains
external/mounted only.

Reason: Docker path layout alone cannot distinguish `/app/market_data` from a
checked-in directory. The mount-point condition preserves the data-outside-Git
invariant while making the verified research container portable.

## 2026-07-19 - Research source mounts are read-only and commit-scoped

Decision: the research Compose profile may bind-mount `./src` and `./scripts`
read-only to run current verified source without rebuilding the large CUDA
image. Its container filesystem is read-only with a disposable `/tmp`; external
market data remains read-only, artifacts remain on the external artifact mount,
and network isolation remains enabled. A research result using those mounts must
record the committed source revision or explicitly be treated as uncommitted
engineering evidence.

Claude's short drift check was `supported-with-limits`: the mount can shadow
the image-installed source, so a dirty or unrecorded host source revision would
make provenance uncertain. The reattestation here used source commit
`1b77ce0250f869befd5ba3b26b61e4ee3249b7a8` and verified 237,325 feature rows
against the existing artifact and contract hashes.

Reason: this eliminates a stale-image execution mismatch without expanding
network, credential, broker, model-promotion, or artifact-storage authority.

## 2026-07-19 - Tiingo/Norgate cross-source cohort is engineering evidence only

Decision: retain one compact external cohort at
`D:\thericher-v2\model-artifacts\tiingo-norgate-cross-source-cohort\tiingo-norgate-cross-source-cohort-r1`.
Its only file is `manifest.json`, 79,969 bytes with SHA-256
`dbc2b25ca514262355c9e4e2bf834889f16358058315b21eb24556b2ccdb1213`. It
reattests Tiingo r2 data/manifest hashes
`6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1` and
`76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`, plus
the Norgate broad-panel data/manifest hashes
`3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d` and
`a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.

The cohort records only 29 rank/symbol links, 501 Tiingo sessions, the first
483 Norgate-overlap sessions, 18 Tiingo forward-only sessions, 153 returned
Tiingo action markers, and 3,316 conservative `t-20..t+2` exclusions. It
never merges price fields or exposes bars, features, labels, training, model,
ranking, ensemble, campaign, paper, PnL, or profitability inputs. Its Engine
intake is metadata-only and enforces those false scopes.

The Tiingo verifier first checks the pinned compressed-byte hash, then compares
the decompressed canonical CSV with the raw-response reconstruction. This
preserves fixed-input identity while allowing the verifier itself to run across
host and Docker gzip implementations. Host and Docker reattestation agreed.
Claude and independent validation both returned `supported-with-limits`:
attestation does not prove Tiingo upstream truth, point-in-time membership,
survivorship, Norgate adjustment semantics, or an independent model result.

Reason: the engine needs a narrow source-side falsification substrate before
opening a fresh model contract, without turning weak source agreement into a
false claim of tradability or spending GPU time on a silently mixed dataset.

## 2026-07-19 - Source-separated batch contract opens one finite engineering run

Decision: retain the immutable external contract at
`D:\thericher-v2\model-artifacts\norgate-tii-source-separated-contract\norgate-tii-source-separated-contract-r4\contract.json`,
SHA-256 `ddba0d578bf5ddaefe10c0c72b63ad8873a27c2243787e504d3c4e8fac0bf76e`.
It reattests the Tiingo/Norgate cohort and Norgate feature artifact, fixes 29
rank/symbol pairs, and separates sources: Norgate alone supplies prices,
features, and labels; Tiingo supplies only attested rank/session/returned-marker
metadata. The 18 forward-only Tiingo sessions are prohibited. The Tiingo marker
mask leaves 10,053 pairs; an exact Norgate-only raw-discontinuity rule removes
149 more, leaving 9,904 rows: 6,434 development, 50 purge, and 3,420 validation.

The next batch is fixed to naive and regularized-linear CPU baselines plus
MLP-32/seed-71 and MLP-64/seed-113 PyTorch CUDA jobs, one at a time with
180-second and 4,096-MiB caps. It fits development rows only; purge is unused;
validation is fixed engineering evaluation and cannot tune, rank, promote, or
select a winner. No tree, TCN, extra seed, depth work, ensemble, paper, PnL,
profitability, or live implication opens from this decision.

Claude and independent Validation returned `supported-with-limits`. The static
survivor/availability construction, non-PIT `t+2` Norgate discontinuity filter,
unverified raw-adjustment/action semantics, and returned-marker dates remain
material limitations. Any future PIT, holdout, paper, or live use needs a new
contract rather than inheriting this one.

Reason: a small hash-attested batch can exercise the CUDA research loop without
mistaking resource utilization or static-source performance for trading evidence.

## 2026-07-19 - Close r4 after deterministic CUDA bootstrap failure

Decision: close `norgate-tii-source-separated-batch-r1` as inconclusive,
CPU-only engineering evidence. Its immutable CPU summary is
`D:\thericher-v2\model-artifacts\norgate-tii-source-separated-batch\norgate-tii-source-separated-batch-r1\cpu-baseline.json`,
SHA-256 `a6f181b504aa9cb6c6b55af59096c3d5c7e4363dc69978b82bb5a4239a80c4ad`.
The first predeclared CUDA job stopped before prediction/checkpoint creation
with the CUDA deterministic-algorithm CUBLAS workspace error; its failure JSON
is SHA-256 `0f93bec411c74aad8980d68af524f046f47051be8230295d48c518808a47217c`.
MLP-64 was not started after the shared fault became known. Do not retry either
r4 MLP or reuse its validation slice, and do not turn the CPU metrics into a
model, negative-result, ranking, or profitability claim.

Commit `ae0d3ec` requires `CUBLAS_WORKSPACE_CONFIG=:4096:8` in the Docker
research profile and fails closed when it is absent. A network-disabled,
synthetic-only CUDA deterministic linear smoke then passed on the RTX 4090; it
used no market data and is infrastructure evidence only. Claude's recovery
verdict was `supported-with-limits`: the predeclared protocol has no environment
retry clause and CPU validation was already written, so closure is more faithful
than a silent rerun.

Reason: preserve a clear boundary between a reproducibility repair and a model
result, while freeing Data to find a fresh unspent contract candidate.

## 2026-07-19 - Local replacement inventory finds no fresh training candidate

Decision: retain the compact external Data inventory at
`D:\thericher-v2\model-artifacts\data-agent\local-replacement-inventory\local-replacement-inventory-r2\summary.json`,
SHA-256 `c7c1de08e33b3ea2a70688a9ec71903ba39ea00531c38bacf43bd053a5c1cf8d`.
It reads only six known local manifests, makes no network or credential access,
and records pinned lineage, chronology, and source limitations. Its conclusion
is `no_local_fresh_training_candidate`.

The Norgate broad panel is the closed r4 parent; Tiingo r2 has only 18 sessions
beyond its end and retains a static non-PIT universe; fixed ETF evidence is
exhausted or unsupported; and Tiingo IEX remains short, descriptive, and
training-ineligible. The broad Yahoo snapshot may support only a later
Data-owned loader/schema preflight, never a model contract, promotion,
strategy-inference, or profitability claim.

The next safe data action is one prospective standard-Tiingo-EOD refresh for
the already authorized `SPY`/`QQQ`/`IWM` scope. It is future lineage only and
does not open GPU work. A fresh model contract still requires private-use US
daily data with historical listing/delisting, an as-of universe, and verifiable
corporate-action/adjustment provenance. Norgate US Stocks Platinum or an
equivalent vendor requires a separately approved purchase; no cost or enrollment
is authorized here.

Reason: preserve research velocity through clean forward collection while not
spending GPU time on a known non-PIT, reused, or unsupported historical slice.

## 2026-07-19 - Target-position policy graph and staged local paper console

Decision: make the durable engine architecture a **target-position policy
graph**, replacing the underspecified `models -> ensemble -> sizing` path. At a
single immutable `as_of` decision time, the graph is acyclic and has these
separate responsibilities:

1. point-in-time opportunity selection and symbol ranking;
2. parallel per-symbol evidence experts over completed `1m`, `5m`, `10m`,
   `1h`, and `3h` bars;
3. entry/hold/reduce/exit policy with explicit abstention;
4. constrained long-only target-weight allocation; and
5. deterministic risk, intent persistence, reconciliation, and execution.

Existing position state may feed the exit policy and allocator, but a learned
node may never emit an order. Every rule or model must emit timestamped
evidence with source/feature lineage, model identity, expected net edge,
uncertainty, horizon, `valid_until`, and missing/stale state. Faster decisions
can use only fully completed slower bars and must expose their age; no
in-progress higher-timeframe value or silent forward fill is permitted.

The graph is introduced incrementally, not as six learned layers at once:

1. establish a deterministic universe/signal/volatility-targeted-sizing/exit
   baseline;
2. admit one opportunity or single-timeframe model only after its own
   chronological evidence;
3. add multi-timeframe experts, then calibrated fusion on nested or
   cross-fitted upstream predictions only;
4. add a learned allocator only if it improves after-cost robustness against
   deterministic concentration and volatility constraints; and
5. add an independent exit model only if it improves over fixed hard exits
   without hidden turnover or tail-risk deterioration.

Every added layer needs a frozen campaign contract, purged/embargoed temporal
splits, an untouched final holdout, matched cost/slippage assumptions, and
layer-level replay attribution. Shared in-sample expert predictions may not
train fusion or allocation. A failed layer is removed from the candidate graph
rather than tuned indefinitely. This structure guides the future breadth queue:
linear/tree baselines, compact sequence candidates, small attention models when
data supports them, and narrowly bounded Chronos/TimesFM benchmarks are model
families, not pre-approved winners or direct trading policies.

Claude's falsification-first architecture review returned `uncertain`. It
supports the separation and evidence-not-orders boundary but requires nested
cross-fitting at expert/fusion boundaries, frozen historical universe membership
before downstream fitting, no cross-layer shared tuning, and incremental rather
than end-to-end validation. The verdict does not authorize training, data
promotion, KIS access, capital, or order submission.

The eventual Docker-local KIS paper console is a separate Execution objective.
It will read a sanitized, fresh reconciliation snapshot and show mode,
connectivity/freshness, holdings, prices, cash/equity, open orders, and safety
state. Its initial controls are local pause-new-entries and cancellation request.
A later pause of discretionary reductions may never block hard-risk exits,
emergency containment, or reconciliation. The web process may not read broker
credentials or call KIS; it gains no submit authority until the existing
read-only, capital-envelope, and separate submission approvals are complete.

No present data contract becomes model-eligible, no new role/daemon/framework is
created, and the current Tiingo prospective-data objective remains unchanged.

Research references, used as design inputs only: [Qlib](https://github.com/microsoft/qlib),
[Temporal Fusion Transformer](https://arxiv.org/abs/1912.09363),
[PyPortfolioOpt](https://pyportfolioopt.readthedocs.io/en/latest/UserGuide.html),
[Chronos](https://github.com/amazon-science/chronos-forecasting), and
[TimesFM](https://github.com/google-research/timesfm).

Reason: this preserves the operator's desired hierarchy of symbol selection,
entry timing, sizing, and exits while keeping model uncertainty, execution
safety, and PnL attribution separable. It avoids a monolithic neural policy or
unbounded MLP/Transformer search, and it makes a useful KIS paper console an
execution-learning tool rather than a premature public trading interface.

## 2026-07-19 - No-paid-data path and bounded KIS data-fit preparation

Decision: the operator has ruled out new paid market-data purchases,
subscriptions, renewals, and upgrades. The project will use lawful free sources,
the already approved Tiingo free-tier scope, and the existing Norgate trial
within their recorded rights. A missing historical point-in-time universe,
delisting lineage, adjustment semantics, or broad intraday history remains a
material limitation; it must be disclosed on any model result rather than turned
into a purchase request or silently repaired with a static survivor universe.

This limitation blocks a claim of generalizable historical model edge, not a
future bounded KIS virtual-paper execution-learning phase. Execution may run a
separately bounded, read-only KIS paper probe during trading or non-trading
hours; only future submission and fill behavior requires a market session. It
will verify only connectivity and data fitness: a declared overseas daily-series
request, a declared intraday-bar request with its continuation behavior, returned
timestamp boundaries, response count, adjustment fields/semantics when present,
and documented rate or retention limits. It may write only rights-permitted
market-data evidence under `D:\market_data` and sanitized metadata under the
artifact root. It may not print or persist credentials/account identifiers,
change `THERICHER_MODE`, query or submit an order, allocate paper capital, or
use `KIS_LIVE_*`.

The probe must not assume that an API offering daily and intraday endpoints is a
long-history research replacement. The observed response, retention window,
paging behavior, corporate-action treatment, storage rights, and exchange-delay
semantics decide that. Until then, KIS data is an unverified prospective or
development candidate only. Norgate trial-derived rows likewise remain subject
to the trial's retention and derived-data rights; do not promote them merely
because they are locally present.

Claude's falsification-first review returned `supported-with-limits`. It
requires explicit as-of checks for KIS bars, a split/dividend observation when
available, rate/paging evidence, and relative rather than absolute interpretation
of baselines built on a non-PIT static universe. A KIS term or response that
prohibits required retention, is materially delayed/restricted, lacks usable
action treatment, or fails bounded paging reverses the data-fit conclusion; it
does not authorize an automatic workaround.

Reason: this keeps the project moving toward real paper-execution evidence
without pretending that free/trial historical data proves an edge, reopening a
paid-data path, or letting broker connectivity become order authority.

## 2026-07-19 - KIS-native observed input boundary

Decision: adopt KIS runtime availability as the active paper-model boundary.
The operator requires a practical, free-data path to paper evidence, so an
unavailable input is removed from the active graph rather than deferred behind a
paid source. Offline data may still develop a prototype, but its feature schema
must be reconstructed from KIS-compatible completed bars before a paper model
can use it. This is a deployability rule, not a claim that KIS history repairs
point-in-time membership, survivorship, or historical model validation.

One bounded, paper-credential, read-only capability probe completed during the
non-trading weekend. It created no order, cancellation, account mutation, mode
change, or live request. Its sanitized market-data summary is
`D:\thericher-v2\model-artifacts\execution\kis-paper-market-data-probe\20260719T054216611479Z\summary.json`.
For `QQQ`, the unadjusted daily request returned 100 OHLCV rows from
`2024-08-09` through `2024-12-31` with continuation header `F`; its retention
and multi-page daily history remain unverified. The adjusted request returned
`HTTP 500` / `EGW00201`, so adjusted price and corporate-action inputs are
unavailable for the initial contract. The `1m` endpoint returned 120 bars for
`2026-07-17` and a continuation request returned another 120 earlier bars with
one observed boundary overlap; it exposes local and Korea timestamp fields plus
raw OHLCV and volume. This qualifies only the fact that KIS can page raw `1m`
bars, not a complete retention, rate, storage-rights, or adjustment conclusion.

The paired account probe summary is
`D:\thericher-v2\model-artifacts\execution\kis-paper-account-readonly-probe\20260719T053923268036Z\summary.json`.
It proved a KIS paper `NASD` balance/position response and an empty `AMEX`
response without retaining account values or symbols. `NYSE` balance, open
orders, and orderable funds returned `EGW00201`; they remain unresolved
endpoint/sandbox or non-trading-hour behavior, not empty account facts. The
existing read-only client now uses the observed working token content type
(`application/json`) and accept header, with no widening of its allowlist.

The initial runtime candidate is therefore a fixed, small-exposure, raw-bar-only
baseline: 90 fully completed `1m` OHLCV bars and deterministic `5m`/`10m`
resamples. It must abstain on an incomplete cache. `1h`, `3h`, adjusted prices,
corporate actions, order book, news, external universe labels, learned models,
ensembles, learned allocation, and learned exits remain inactive until their
own KIS/reconstruction evidence exists. Claude's falsification-first review
returned `supported-with-limits`: a page cap is not a lookback requirement,
capability observations must be dated, transfer tolerances must be predeclared,
and the limited-validation exception applies only to the simple baseline.

Reason: this turns observed KIS constraints into an executable model design and
keeps paper readiness moving without making weak historical evidence, an API
page size, or a failed sandbox endpoint look stronger than it is.

Implementation: the broker-free foundation now has a compact KIS capability
record, an in-memory completed-bar cache, a narrow raw-minute read-only parser,
a common target-exposure proposal, and a fixed 90-`1m` / 18-`5m` / 9-`10m`
baseline that maps only through deterministic local-paper execution. The
research module never creates an `OrderIntent`; Execution maps a ready target
delta. Local fills remain `source: local_paper` and replay from the event store.

Qualification permits an in-memory runtime feature only; it does not grant raw
data persistence. A confirmed storage-rights status remains necessary before
market bytes or a cache are written under `D:\market_data`. This preserves the
paper-first path without turning an unverified retention right into a hidden
archive.

The first post-implementation raw-minute client check surfaced a local boundary
bug: OAuth token responses do not need the market-data `rt_cd` field. After the
client was corrected to require only HTTP success and a token, its fake response
test and one bounded real paper read succeeded. The real `QQQ`/`NAS` response
returned 120 raw bars in descending exchange-time order from `19:59` through
`18:00`, with `next` present and `more=0`; it retained no raw price, token,
account, or order data. Its sanitized evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-raw-minute-client-probe\20260719T060205390Z\summary.json`
with SHA-256
`81e80a4c7a55e90cfde73e1349e83aa504f5f86589c3c5ac8e0122e4128c6f72`.
This strengthens the dated raw-page observation only; time conversion,
completed-bar behavior, overlap handling, rate, and storage rights remain
unqualified.

The read-only client now reuses a successfully issued token within one bounded
client instance, so a first page plus its explicit continuation needs one token
attempt rather than one credential request per page. The token is not persisted,
logged, or shared with execution; a new bounded objective creates a new client.

Claude's falsification-first verdict on the in-memory versus persistent-storage
boundary was `uncertain`. It specifically requires a discriminating timestamp
mapping, an in-progress-bar completeness observation, and a repeatable
continuation overlap rule before qualification. It found the current blast
radius low because the KIS execution adapter remains disabled and the foundation
maps only to `local_paper`; that constraint must remain in force.

## 2026-07-19 - Raw-minute timestamp labels need an independent anchor

Decision: do not promote the KIS raw-`1m` capability from a self-consistent
one-shot response alone. A bounded offline harness now constrains a future
regular-session probe to one client/token, one first page, and at most one
continuation; it writes only row counts, timestamp bounds, overlap facts, and
booleans under the external artifact root. It does not read credentials or
make a request until explicitly executed during its narrow session window.

Claude's falsification-first verdict is `uncertain`: matching KIS exchange and
Korea fields can disprove an internal mismatch, but cannot by itself prove
whether the row timestamp labels the opening or closing minute. Therefore the
harness may report internal facts but cannot output a promotable capability
without an independent label-semantic anchor. Failure artifacts accept only
closed reason codes, avoiding arbitrary response or exception text.

Reason: a one-minute timestamp shift would create a silent completed-bar and
feature-time error even if all same-response consistency checks pass. Retaining
the capability as `observed` is a narrow data-contract limitation, not a new
report/gate system or a reason to delay unrelated local-paper work.

The official KIS sample for the same raw-minute endpoint additionally specifies
`PINC=0` for the first request, `PINC=1` for continuation, and a `KEYB` one
exchange-local minute before the preceding page's oldest bar. The narrow client
now applies that documented no-overlap continuation contract and fake tests
prove its request shape. This corrects future paging behavior only; no KIS
request was made and it does not resolve the raw timestamp-label limitation.

## 2026-07-19 - One-shot raw-minute probe and baseline capability gate

Decision: harden the active raw-`1m` probe before consuming its one allowed
paper-token attempt. The runner now pins the repository and external artifact
roots, uses the shared external control root for its atomic objective-specific
reservation, rejects HTTP redirects, and limits each page to 120 rows before
any possible token request. A
rerun with that reservation exits before configuration or network access. A
continuation must be both non-overlapping and exactly contiguous at the
one-minute boundary; it is skipped if the narrow execution envelope has elapsed.

The bar-label condition is now a dated metadata-only anchor with an identifier,
evidence reference, UTC observation time, and explicit `bar_open` or
`bar_close` semantics rather than a caller-supplied boolean. No such anchor is
currently present, so the next real probe can record `observed` evidence but
cannot promote the capability. A complete exchange-calendar implementation is
not added for this single shot; Codex verifies the specific regular session,
including holidays and early closes, immediately before invocation.

Engine now requires a matching `qualified` KIS capability before the fixed
90-`1m` baseline can construct a proposal. It otherwise emits an explicit
`unqualified` abstention, and direct baseline inputs must be complete,
contiguous, and identical to their local `5m`/`10m` resamples. This turns the
existing paper-time data rule into code without adding a model, broker path,
scheduler, raw-data cache, or external order authority.

Claude's falsification-first verdict was `supported-with-limits`: the missing
gate and gap check were real, the one-shot reservation must not reuse the
timestamp run id, and an absent independent label anchor must remain a hard
promotion limit. The follow-up changes remain offline; no KIS request or
credential read occurred while making them.

## 2026-07-19 - Keep the one-shot raw-minute probe observed-only

Decision: simplify the KIS raw-`1m` v4 probe so its only completed outcomes are
sanitized `observed` or `rejected`. Remove metadata-anchor loading and forbid a
one-shot result from becoming `candidate_qualified` or updating a capability.
The target raw-`1m` capability stays `observed` after this objective. A later,
independent Data objective may assess timestamp-label evidence and must receive
the required Claude challenge before any promotion.

Reason: a writable local metadata file cannot by itself establish that a raw KIS
timestamp labels a bar open rather than close. Treating it as a qualification
input would overstate one snapshot's evidence and open a silent feature-time
risk. The smaller observed-only contract preserves paper-readiness learning
without adding a report, gate, calendar service, or promotion workflow.

Implementation: the runner now permits only the preverified 2026-07-20 Nasdaq
session window, based on Nasdaq's official 2026 calendar at
`https://www.nasdaqtrader.com/Trader.aspx?id=calendar`. It rejects all other
dates before configuration, reservation, or network access. Its external
one-shot state records `reserved -> network_started -> summary_written`; if the
summary cannot be persisted after a network boundary, `network_started` remains
as a non-retryable recovery fact. The continuation query is validated against
the first page's cursor and documented prior-minute key. Reservation descendants
are resolved and rejected if a symlink/junction can escape the external control
root or enter Git.

The paper config loader accepts only the approved nonsecret `THERICHER_*`
runtime keys before the two paper app keys, then stops. Any unexpected
pre-paper key fails closed; it does not progress to the KIS token boundary.
The fixed baseline now also rejects a non-`US` market for the `QQQ`/`NAS`
capability before a ready proposal can reach local paper.

Claude's falsification-first verdict was `supported-with-limits`: simplify the
probe, pin the one-shot date, and keep source-provenance widening out of the
generic `Bar` contract until a real KIS-to-`Bar` adapter exists. Codex retained
the additional child-path validation because resolving only the external root
does not protect a pre-existing `reservations` junction. All changes and tests
remain offline; no credential or KIS request occurred.

## 2026-07-19 - Harden the bounded raw-minute observation before its one token

Decision: close the final preflight gaps before consuming the permitted raw
`1m` observation. The runner rechecks a fresh New York clock after its approved
paper-config read, immediately before its network-start lifecycle transition,
and again in the harness immediately before the first page request. A delay or
suspend therefore produces a sanitized rejected/no-op path rather than a stale
window call. The initial reservation and each transition now flush marker bytes
with `fsync`; a write/durability failure leaves a non-retryable marker rather
than reopening the token boundary.

The external summary writer now accepts only typed observed evidence or typed
sanitized failure input and creates its own projection. It cannot persist an
arbitrary caller dictionary with prices, rows, response bodies, or credentials.
The paper configuration reader now consumes an unapproved key byte-by-byte and
fails before reading its value, so a malformed/reordered `.env` cannot make a
later `KIS_LIVE_*` or account value part of the probe input. The fixed baseline
also pins `US` `QQQ`/`NAS` to the `overseas_stock_intraday` capability category.

Independent role review found that generic `Bar` objects do not yet carry a
source-capability identity. Codex deliberately does not add a caller-supplied
provenance string that would only simulate that assurance. The current observed
capability remains fail-closed; a future actual KIS-to-`Bar` adapter must bind
provenance before a qualified runtime stream can reach this baseline.

Claude's falsification-first verdict on execution timing was
`supported-with-limits`: one cold-start cron could miss the narrow safe-second
range, while a small date-limited external preflight fan-out is safer only when
every invocation shares this host's `D:` reservation. The active local Codex
automation therefore has six fixed KST checks within the one 2026-07-20 Nasdaq
window. Only the first successful reservation can reach the one token; every
other invocation exits before credential loading. This is an external,
objective-expiring operating aid, not repository scheduler code or a durable
job family.

The safe-time comparison now normalizes seconds before testing the fixed New
York minute boundary, while preserving the separate `10` through `45`
safe-second rule. This keeps the final `15:40` KST-mapped interval available
without admitting an earlier/later second, another minute, or another date.
Focused sanitizer coverage also injects fake volume, cursor, account-identifier,
and raw-row values and proves that the typed external summary does not retain
them. No credential or KIS request was used while making this correction.

## 2026-07-19 - Historical KIS support probe remains metadata-only

Decision: accept the operator's narrow KIS paper authorization for one
historical capability observation: `QQQ` and `SPY` only, one `KIS_PAPER_*`
token, at most three daily pages and three raw-`1m` pages in total. The only
recorded outcome is technical support/data fitness metadata: fixed scope, call
counts, date/timestamp bounds, daily OHLCV field presence, pagination facts,
and raw-minute overlap/boundary facts. No raw quote, price, volume, row,
cursor, response body, token, credential, account identifier, or account value
may be printed or persisted.

The authorization excludes order, cancel, account, position, buying-power,
open-order, and every live endpoint. `THERICHER_MODE=off` remains required. The
single-token client has a direct-only, redirect-rejecting allowlist for OAuth,
overseas daily, and overseas raw-`1m` requests; tests reject broker and live
paths before transport open. Its external lifecycle reservation is append-only
and non-retryable even if a marker snapshot disappears.

Claude's falsification-first review returned `supported-with-limits`: the
request and page bounds must be enforced before credential-bearing traffic, and
the result cannot be treated as evidence of retention, rate limits, adjustment
or corporate-action semantics, point-in-time coverage, storage rights, or model
fitness. This decision does not widen the separate 2026-07-20 raw-minute
observation, whose output remains `observed` or `rejected` and not promotable.

Reason: the small sample gives the active KIS-compatible-input investigation a
dated technical fact while preserving the no-archive, no-account, no-order, and
no-model-promotion boundaries. It is a bounded engine-loop probe, not a new
provider, scheduler, report, or data contract.

## 2026-07-19 - Simplify raw-minute session confirmation

Decision: remove the separate raw-minute session-clearance artifact and helper
script. Before the one date-limited raw-minute runner can read its paper config,
it now requires an explicit `--confirm-no-exception` flag. The external
automation performs the independent official Nasdaq calendar check immediately
before supplying that flag. The runner still pins its date/window, rechecks the
clock, and uses the durable external one-shot reservation/ledger to block every
retry after a possible network boundary.

Claude's follow-up simplification review returned `uncertain`: the large
one-shot surface can become process sprawl, but the shared reservation ledger
and typed secret-safe projection remain justified by concurrent date-limited
preflight and raw-data boundaries. Codex therefore removed the extra clearance
state while retaining direct-only request allowlisting, one-token reuse,
non-retryable lifecycle evidence, and tests for confirmation-before-config.

Reason: calendar confirmation is an invocation fact, not evidence that needs a
second durable artifact. This reduces state, code, and operational steps
without weakening the actual KIS side-effect or secret boundaries.

## 2026-07-19 - Enforce the active KIS market-data scope below CLI scripts

Decision: make the credential-bearing KIS market-data boundary itself enforce
the current operator authorization. Both query construction and the direct-only
transport now permit only `QQQ`/`SPY` on `NAS`, the exact raw-`1m` or daily
request shape, and at most three requests of each kind per client. An
out-of-scope route, symbol, exchange, interval, continuation shape, or fourth
page fails before `opener.open`. Add lifecycle regression tests proving that an
indeterminate historical summary write or transition leaves the one-shot
reservation non-retryable before configuration loading.

Reason: script-level limits were correct, but a lower public client/transport
surface could still form a broader request. The active approval is a narrow
technical observation, so its smallest enforceable authority belongs below the
script call site rather than in operator discipline alone.

Independent Validation found the broader request surface and the missing
historical lifecycle regression coverage. Claude's short falsification-first
verdict was `supported-with-limits`: use the pre-connection transport chokepoint
and beware treating a real listing venue as interchangeable with the active KIS
query code. The current operator authorization explicitly fixes both `QQQ` and
`SPY` requests to `NAS`, so the boundary retains that flat scope. If KIS rejects
`SPY` on `NAS`, record a limited/rejected capability fact; do not widen to a
second exchange without a new authorization. This is a scope-narrowing
correction, not a promotion or new authority; focused tests remain offline and
no KIS request or credential read occurred while making the change.

## 2026-07-19 - Local-paper post-fill restart recovery

Decision: when a broker-free `local_paper` fill has been durably appended but
the following derived portfolio snapshot is interrupted, a later sequential
retry may return the original fill rather than append another one. Recovery
requires exactly one accepted order and one recorded local fill for the client
id, then revalidates the complete signal and execution bars plus their stable
fingerprints, deterministic price, fee, and timestamp. Any mismatch, missing
identity, duplicate fill, changed fee/slippage configuration, or malformed
event fails closed. Recovery replays the authoritative event log and does not
write another fill or snapshot.

Reason: the append-only fill is the accounting authority, while the portfolio
snapshot is a convenience projection. A post-fill interruption must not turn a
known fill into either a duplicate trade or an unrecoverable caller error. This
is sequential local-simulator restart behavior only; concurrent fill calls and
KIS paper/live recovery remain outside its claim.

Claude's falsification-first verdict was `supported-with-limits`: deterministic
bar-derived economics and single-fill identity are load-bearing, and a mutable
fee setting or revised bar must reject the retry. Focused tests simulate the
interruption, prove one replayable `source: local_paper` fill, and reject both a
revised same-time execution bar and changed fee schedule. No credential,
network, KIS, account, order, or live behavior is involved.

## 2026-07-19 - Bind KIS baseline qualification to the full capability contract

Decision: a `KisMarketDataCapability` with `state=QUALIFIED` is structurally
necessary but no longer sufficient for the fixed KIS 90-`1m` baseline. The
baseline also requires a separately typed qualification binding whose canonical
SHA-256 covers every capability-contract field, including scope, raw fields,
time semantics, completed-bar rule, freshness, paging facts, storage rights,
evidence reference, and observation time. Its Data-owned trusted registry is
empty today, so every real caller remains fail-closed even if it constructs a
matching `QUALIFIED` capability object.

Exchange and symbol scopes are membership sets, so their normalized tuple order
is sorted before fingerprinting; a reordered but equivalent scope cannot lose a
valid binding.

Reason: the active KIS observations are metadata-only and must not become a
paper-time model input through caller assertion. The additional binding makes a
changed capability fail the match rather than silently inheriting old
qualification. It is structural provenance only, not proof that a referenced
external artifact was reviewed; validating that evidence and populating a
production registry is a later Data-owned objective.

Claude's falsification-first verdict was `supported-with-limits`: canonical,
total fingerprint coverage and immutable values are load-bearing, while a bare
second boolean would be ceremony. Tests use a test-only registry binding to
retain the pure baseline and local-paper coverage, then prove that no binding
or a binding for a changed capability produces an `unqualified` abstention and
no local-paper intent. No credential, KIS call, data read, artifact, model,
broker, or execution authority changes.

## 2026-07-19 - Add explicit-session resampling without calendar activation

Decision: retain the existing generic UTC-epoch `resample_bars` behavior and
add a separate Data-owned `SessionWindow` primitive for caller-supplied UTC
open/close bounds. It accepts only one homogeneous `1m` stream, anchors target
`5m`/`10m`/`1h`/`3h` buckets at the declared session open, rejects every
out-of-window bar, and returns complete bars plus explicit skipped bucket
starts for gaps, duplicates, incomplete source bars, or a short terminal
bucket. An empty declared session reports every missing full bucket and its
terminal partial bucket rather than appearing complete. It never joins a second
session or infers an exchange calendar or DST.

Reason: the architecture needs session-aligned higher timeframes, but the
current KIS observations cannot safely supply an inferred calendar. Keeping the
window explicit makes the arithmetic useful without silently extending the
KIS/model/paper authority or changing the established UTC-epoch path.

Claude's falsification-first verdict was `supported-with-limits`: every output
must be fully covered by contiguous source timestamps inside one declared
window, and skipped data must stay visible rather than disappear silently.
Synthetic summer/winter caller-supplied sessions, gaps, duplicates, partial
terminal buckets, and adjacent-session rejection provide that boundary. No
KIS call, credential, data file, artifact, model, GPU, broker, or timeframe
activation is added.

## 2026-07-19 - Keep KIS baseline decision time distinct from feature time

Decision: a ready fixed KIS baseline proposal now records `decided_at` from
the immutable caller `as_of` rather than backdating it to the final completed
bar. It retains `feature_window_end` separately, incorporates both timestamps
as separate provenance fields, and uses only stable market/symbol/status,
reason, feature-window, and content-fingerprint inputs for the deterministic
proposal id. It abstains with
`baseline_input_expired` when `as_of` is at or after
`feature_window_end + 10m`. The usual capability and caller freshness limits
still apply first; neither may extend this structural expiry.

Reason: a delayed evaluation must not appear to have happened when its input
bar closed, and a proposal must not remain executable across the next fixed
bar boundary merely because a caller supplied a broader freshness budget. The
separate fields preserve causal/replay lineage without adding a clock service,
KIS adapter, model, dataset, or order path.

Claude's falsification-first verdict was `supported-with-limits`: preserve the
feature timestamp, use the immutable evaluation time for every ready and
abstaining decision, and make the expiry boundary fail closed. Focused tests
use a test-only twenty-minute capability freshness budget to prove that the
independent ten-minute expiry still wins. No credential, KIS request, raw
market-data access, model training, broker submission, or live behavior is
added.

## 2026-07-20 - Preserve the bounded historical KIS rejection

Decision: accept the one allowed QQQ/SPY historical KIS market-data attempt as
terminally `rejected` with the sanitized reason `daily_response_rejected`.
Its immutable summary is
`D:\thericher-v2\model-artifacts\data-agent\kis-paper-historical-data-probe\20260720T001125Z\summary.json`,
SHA-256 `3883d32289bd06196ca28823cc041d0780172add4848661d185c24e07cde0c8f`.
It used one paper token and two daily attempts, made zero raw-`1m` attempts,
called no account/order/live endpoint, and retained no raw market data. The
external lifecycle reached `reserved -> network_started -> summary_written`,
so this objective cannot be retried.

Reason: the approved probe was a narrow technical observation, not an archive
or a capability-promotion path. A rejected daily response establishes neither
a general endpoint failure nor daily fields, paging, continuation, timestamps,
storage rights, data quality, point-in-time coverage, or model fitness. It
cannot alter the independently scoped raw-`1m` `observed` state.

Independent Data and Validation review confirmed the lifecycle, bounded scope,
sanitization, and retry prohibition from the summary and external control
evidence. No Claude review is needed because no promotion, data-contract
change, capital decision, execution-risk change, or model claim is proposed.

## 2026-07-20 - Fail closed local emergency-state persistence

Decision: make the local emergency-state JSON transition atomic with a
same-directory temp file, flush/fsync, and replacement. Serialize state
transitions with a sidecar exclusive lock within one host runtime or one Docker
runtime, so concurrent stop and cancel requests merge rather than clearing an
already requested stop. Any unreadable or malformed JSON state, including a
timezone-less timestamp, resolves to a stop-new-orders state.

Reason: emergency controls are deterministic execution safety, so interrupted
files or stale read-modify-write races must never make a local-paper entry look
permitted. The Docker named runtime volume is Linux-local; a Windows host path
is separate, so cross-runtime shared-file coordination is not claimed.

Independent validation reproduced the original cross-process lost-update risk,
then confirmed the spawned-process regression and malformed-timestamp
fail-closed behavior. This is local-paper-only safety work: it reads no
credential, opens no network connection, calls no KIS endpoint, and changes no
paper/live submission authority.

## 2026-07-20 - Preserve the raw-minute one-shot across local config and OAuth delay

Decision: retain the one-shot reservation as the only atomic external-attempt
gate, but prevent local configuration defects from consuming it. The runner
first confirms that no reservation exists, preflights only the approved paper
configuration, then rechecks both time and reservation immediately before
atomic reservation. A configuration failure therefore creates no attempt marker
or summary. A blank dashboard-token placeholder may remain before the paper
keys, but a nonempty value is rejected before it is retained; the committed
template places dashboard configuration after the narrow paper-app block.

The raw-minute client now obtains its one permitted OAuth token before a final
clock check immediately preceding the first raw-page GET. If OAuth latency
crosses the fixed time boundary, no raw-page request is sent and the already
reserved attempt records a sanitized rejected outcome. Continuation keeps its
existing pre-request time check. This adds no endpoint, credential scope,
market-data retention, capability promotion, broker order, capital, or live
authority.

The durable `O_EXCL` marker is created before the matching ledger append. A
stale concurrent precheck can therefore lose at marker creation without writing
a duplicate `reserved` ledger record. If ledger persistence then fails, the
marker remains as a non-retryable fail-closed recovery fact rather than
reopening the token boundary.

Claude's falsification-first verdict was `supported-with-limits`: an initial
reservation check followed by configuration is necessarily a local
time-of-check/time-of-use window, but the final atomic reservation remains the
only gate for a possible KIS request. Focused fake-transport tests cover a
concurrent stale precheck, a successful token whose post-OAuth clock is outside
the raw GET window, and a request gate immediately before the transport GET. No
real credential, KIS request, artifact, or order was used while making this
correction.

## 2026-07-20 - KIS virtual-paper read-only development authority

Operator statement (verbatim): "kis 호출 전부 승인할게 호출해서 개발하는게
좋잖아, 내가 호출 승인한것도 문서에 남겨둬 어차피 kis에 내가 실제 현금을
넣어둔게 없어서 호출해도 괜찮아".

Decision: apply that direction to `KIS_PAPER_*` only. Isolated, typed
virtual-paper development work may use paper OAuth plus read-only account,
position, buying-power, open-order, and market-data endpoints. It must retain
only sanitized typed evidence, never credentials, account identifiers, or raw
broker payloads. The dashboard remains credential-free and broker-free; it may
consume only a separately produced sanitized snapshot.

The statement does not name `KIS_LIVE_*`, a paper-order submit/cancel action,
or a paper capital amount. Therefore live credentials remain unavailable, and
external paper order submission/cancellation remains blocked until a fresh
reconciliation produces a specific capital envelope that the operator approves.

Reason: development benefits from evidence from the virtual broker, while
account access, live access, and capital-moving actions have materially
different risk surfaces. Recording both the operator's exact instruction and
the applied interpretation prevents a later broad reading from silently adding
live or order authority.

Claude's falsification-first verdict was `supported-with-limits`: the wording
supports KIS virtual-paper read-only development, but not a live or order
authorization. The decision reverses only on an explicit operator statement
naming `KIS_LIVE_*` or approving a paper capital amount and order submission.

## 2026-07-20 - Isolate KIS paper console reconciliation from the web runtime

Decision: the local console consumes a versioned generic paper-account snapshot
from a Docker runtime mounted read-only in the web service. A separately
invoked `kis-readonly` Compose profile receives only the four `KIS_PAPER_*`
values, performs one typed virtual-paper reconciliation, atomically publishes a
complete or fact-free unavailable snapshot, and writes a minimal external
result. The snapshot expires after five minutes; missing, stale, malformed, or
partial state is never rendered as an empty account. The web process has no KIS
client, broker path, or credential environment.

The one bounded real reconciliation completed at `2026-07-20T07:34:11.455838Z`.
Its minimal evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260720T073411455838Z-complete.json`,
SHA-256 `9b7b12848f28ced98d674ac224d2f576e02df279cf57a581ef5500e9159614fb`.
It retains only status, timestamps, currencies, counts, and a runtime-payload
digest. The first evidence write encountered a lexical in-container artifact
root check after the sanitized runtime snapshot completed. The check now admits
only the configured `/app/model_artifacts` mount below the repository path; a
fresh complete snapshot can recover missing minimal evidence with no KIS I/O.
This recovery classified the run as `complete`, not a broker retry.

Reason: a browser-facing monitor must not be a credential or broker boundary,
but KIS paper reconciliation is useful execution evidence. The narrow bridge
keeps the external fact surface small, allows a failed evidence write to be
recovered without another broker call, and does not create a daemon, scheduler,
report family, general KIS client, submission path, capital allocation, or live
capability.

Claude's falsification-first verdict was `supported-with-limits`: atomic final
publication, strict freshness, an isolated credential path, and a recovery path
that never refreshes data are load-bearing. Focused fake-transport, snapshot,
web-isolation, Compose, and Docker-local HTTP tests cover those boundaries.
The next decision is a specific paper-capital envelope for the operator; this
decision does not authorize one.

## 2026-07-20 - Keep paper-capital candidates distinct from cash and execution

Decision: snapshot schema v2 renames the generic console fact formerly called
cash to `orderable_foreign_funds`, pins it to the exact producer field
`ord_psbl_frcr_amt`, and expires it at `now >= expires_at`. It is explicitly
not settled cash, account equity, margin capacity, or general buying power. The
separate `reference_orderability` fact remains a one-reference-request
compatibility signal and is never a sizing input.

`execution.paper_capital_proposal` is a pure calculation over the sanitized
runtime snapshot and an operator-supplied same-currency ceiling. It can return
only `abstain` or `awaiting_operator_approval`; a candidate is the lesser of
the source-labelled funds amount and the operator ceiling. It abstains for any
missing, unavailable, future, exact-expiry, currency-mismatch, zero-funds,
nonempty-position, or open-order state. It neither invokes KIS nor reads an
environment value, creates an intent, writes an approval or artifact, changes
mode, calls a broker, converts FX, or supplies an order path. The Docker profile
has no network, credentials, port, or writable runtime mount.

Reason: a read-only amount associated with a reference order query is useful
operator evidence but cannot be silently promoted into total equity or
executable buying power. Keeping the proposal transient and fail-closed gives
the operator a bounded capital question without weakening later risk and broker
reconciliation requirements.

Independent Validation found the earlier nonzero proposal unsupported until
currency, reference-orderability, expiry, position/open-order, producer, and
isolation conditions were explicit. Claude's falsification-first verdict is
`uncertain`: producer semantics and any future approval persistence remain
separate decision surfaces. This implementation records neither a nonzero
envelope nor an approval. The next required operator choice is a cap in the
fresh snapshot's native currency; `USD 500` is only the Codex recommendation
when that currency is USD.

## 2026-07-20 - Close the bounded raw-minute v4 observation without retry

Decision: close the single `QQQ` / `NAS` raw-`1m` v4 observation as terminal
`rejected`, not `unavailable`, after its sanitized summary recorded
`minute_response_rejected`, one OAuth token attempt, and two minute-page
attempts. Its external-only artifact is
`D:\thericher-v2\model-artifacts\execution\kis-paper-raw-minute-qualification\20260720T174018Z\summary.json`,
SHA-256 `2e87ef096dad2d6e06f71a0d653c8c245b40c11dc0be08f3f8c6af5532c1a23a`.
The reservation/ledger lifecycle is `reserved -> network_started ->
summary_written`; it blocks every retry. No raw market data, price, volume,
token, account identifier, or broker body was retained.

The two page attempts mean only that the client reached its continuation path
after accepting enough first-page structure to obtain a cursor. The rejection
does not establish the second response's HTTP status, KIS code/body, on-wire
request correctness, paging semantics, timestamp labeling, completed-bar
freshness, retention rights, or a KIS-wide outage. It neither promotes nor
negates the pre-existing raw-minute `observed` capability, and the trusted
qualification registry remains empty.

The immutable result's failure summary timestamp precedes its reservation by a
few milliseconds because the prior runner reused its initial clock in a caught
error path. Do not rewrite external evidence. The runner now keeps the latest
durable lifecycle timestamp, and the shared marker transition rejects any
retrograde timestamp before appending a ledger state. Focused fake-client and
state-machine tests cover both changes.

Reason: one bounded failed observation must remain recoverable and falsifiable
without becoming a generic retry loop or an unsupported causal story. A future
offline objective may inspect the code-level continuation-request contract, but
cannot claim what was on wire or returned; a future network observation would
need its own scope and decision boundary.

Claude's falsification-first verdict was `supported-with-limits`: terminal
disposition is supported, while HTTP/KIS cause and actual on-wire request form
remain unresolved. The decision reverses only if durable sanitized evidence is
shown to be inconsistent with the recorded terminal lifecycle.

## 2026-07-20 - Align the raw-minute request builder without diagnosing v4

Decision: align the narrow local raw-minute request builder with the current
public KIS sample without reopening the terminal v4 observation. The inspected
sample and helper (official `open-trading-api` Git blobs
`65709af1b9474e65373686764a0dcf5e22d83d4a` and
`8dca2ae4031db12b7c4ce0c449758c54768e54ad`) support the existing endpoint,
TR ID, `PINC`/`NEXT`/`KEYB` convention plus `custtype=P`, empty first-page
`tr_cont`, and continuation `tr_cont=N`. The local client now applies those
headers and drops `FILL_GUBN`, which is unsupported by that inspected sample.

This is a source-alignment decision, not proof that `FILL_GUBN` was invalid or
that either difference caused `minute_response_rejected`. The v4 summary retains
no request headers/query, HTTP status, body, or response header, so the actual
on-wire form, rejection cause, and response-driven pagination convention remain
unresolved. Exact fake-transport and in-memory-`urllib` tests freeze only local
construction. No credential, KIS request, account endpoint, artifact rewrite,
capability promotion, retry authorization, or paper/live authority change was
made.

Claude's falsification-first verdict was `supported-with-limits`. This decision
reverses only if a later authoritative KIS source contradicts the recorded
source version or an independently scoped, separately authorized observation
provides sanitized evidence that materially changes the request contract.

## 2026-07-20 - Validate first-page order before a raw-minute continuation

Decision: a raw-minute qualification runner may derive its documented
one-minute-prior `KEYB` from the first page's final row only when the original
exchange timestamps are strictly descending in one-minute steps. If a cursor is
present but a first page is swapped, duplicate, or gapped, the runner keeps the
first-page metadata observation and suppresses the continuation GET. It does
not sort rows, infer a replacement boundary, use Korean labels, or add a new
failure category.

Fake-transport coverage proves each malformed first page uses one token and one
raw-page request, records the cursor as available but unrequested, and exposes
only `first_page_descends_one_minute=False` in its sanitized summary. The valid
two-page `KEYB` path remains separately covered. No credential, KIS call,
artifact mutation, capability change, retry authority, capital decision, or
paper/live behavior was introduced.

Reason: request-contract alignment alone cannot make an arbitrary final row a
safe page boundary. Stopping locally before the second side effect reduces the
blast radius of malformed input while retaining the bounded first-page evidence.
It cannot qualify `1m`, derived `5m`/`10m`, inactive `1h`/`3h`, or change the
empty trusted registry.

## 2026-07-21 - Close the bounded KIS console reconciliation unavailable

Decision: close the separately authorized Docker `kis-readonly` reconciliation
at `2026-07-20T18:35:34.353908Z` as terminal `unavailable` with the typed safe
reason `balance_rejected`. Its external-only minimal evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260720T183534353908Z-unavailable.json`,
SHA-256 `5586e223883c12104d58d31412e816fa1eae9cc308326639c28a6861e36105d2`.
It records only timestamps, unavailable state, a runtime-payload digest,
`paper_only=true`, and `submit_capability=false`; no account, price, position,
credential, raw response, or native-currency fact is retained in external
evidence.

Reason: the purpose was a fresh bounded reconciliation snapshot, not diagnosis
or recovery of a prior KIS result. Independent Data review confirms that this
account-only result cannot qualify any KIS market-data timeframe or alter the
empty trusted registry. Independent Validation confirms the profile has no
submit, cancel, modify, live, capital-setting, or public-listener path. Do not
retry this run, inspect the Docker-local account snapshot, infer a broker or
authorization cause, propose a paper capital envelope, or widen any authority.

Claude's falsification-first verdict for the next offline execution lane is
`supported-with-limits`: reuse the existing broker-neutral `BrokerOrderRequest`
and disabled adapter, and build only a public-source-attested KIS paper
long-only limit-order field mapping. Do not add another request contract,
transport, Compose profile, or enablement switch. If official public material
cannot pin the relevant wire fields tightly enough for falsifiable offline
tests, close that mapping as unsupported rather than guess or make a KIS call.

## 2026-07-21 - Isolate KIS virtual-paper US buy-limit body fields

Decision: accept one pure, offline mapping from the existing
`BrokerOrderRequest` and a caller-supplied `NASD`, `NYSE`, or `AMEX` exchange
to the seven virtual-paper US buy-limit **body** fields supported by the
official KIS sample pinned at revision
`885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc`:
`OVRS_EXCG_CD`, `PDNO`, `ORD_QTY`, `OVRS_ORD_UNPR`, `SLL_TYPE`,
`ORD_SVR_DVSN_CD`, and `ORD_DVSN`. The mapper admits only a positive whole-share
US buy limit order, never derives an exchange from generic `US` or a ticker,
and emits no account identifiers, contact fields, endpoint, header/TR ID,
credential, environment, idempotency, or transport context.

The official source uses the virtual-paper TR ID in the request header, so that
value intentionally remains outside this non-transmittable body fragment.
The source example supplies blank contact and management fields but does not
establish a universal account-independent default; those fields remain outside
the mapper. `create_kis_broker_adapter()` remains disabled, and no adapter,
profile, artifact, KIS call, order action, capital action, or live behavior was
added.

Independent Data review returned `supported-with-limits` for the pinned field
provenance. Independent Validation found that the initial I/O test imported
the module before installing its blockers; the test now imports it after the
credential/file/network blockers and confirms mapping plus the existing disabled
adapter stay offline. The completed raw-minute `13:30` through `15:40` New York
window remains only historical one-shot probe context, never a future
paper/live schedule or trading-window preference.

Reason: a narrow body fragment lets future separately authorized work reuse
known field names without silently introducing an executable KIS request or a
second broker lifecycle. The next safe preparation is the corresponding pure
long-only sell-limit body fragment, whose holding proof must remain in the
existing deterministic risk boundary.

## 2026-07-21 - Isolate KIS virtual-paper US sell-limit body fields

Decision: extend the same pure body-only module with a separate US sell-limit
mapper for `BrokerOrderRequest(side="sell")` plus an explicit `NASD`, `NYSE`,
or `AMEX` exchange. It emits the same seven non-account fields as the buy
fragment, with official-source-attested `SLL_TYPE="00"`, and preserves
virtual-paper limit-only `ORD_DVSN="00"`. It rejects buys, market orders,
unsupported exchanges/markets, malformed symbols, fractional or nonpositive
quantity, invalid prices, and invalid request types.

The mapper does not accept a position, query holdings, infer a short-sale
permission, persist an intent, or authorize a sale. Existing deterministic
target/risk code remains responsible for proving a long reduction and rejects
an oversized sell before any later broker boundary. It retains the prior
credential/file/network/import guard and disabled-adapter verification.

The public source's US virtual sell comments name `VTTT1001U`, while its generic
implementation derives a different virtual form by prefixing the real sell TR
ID. This source inconsistency makes a header/TR-ID resolver unsupported here.
No such resolver, account/contact default, endpoint, transport, Docker profile,
KIS call, artifact, paper capital, order action, or live behavior was added.

Reason: a paper engine needs a safe exit-side representation, but only as a
non-transmittable fragment until a separately authorized and source-resolved
transport contract exists. The next generic execution step is a limit-only
projection from `OrderIntent` to the existing broker request contract; it must
not select or fetch a price.

## 2026-07-21 - Keep explicit-price intent projection broker-neutral

Decision: add one pure `order_intent_to_broker_order_request` helper in the
existing broker-contract module. It accepts only an `OrderIntent` whose limit
price is already explicit, copies client ID, symbol, market, side, quantity,
limit price, decision ID, creation time, and schema version into the existing
`BrokerOrderRequest`, and delegates all shared-contract validation to that
destination contract. A target-position market intent remains non-projectable.

The helper does not choose, fetch, round, clamp, or timestamp a price. It also
does not persist an intent, risk-approve it, connect to the KIS body mappers,
create a route/header payload, enable an adapter, access a credential or file,
or call a broker. Tests block environment, file, and network paths while also
proving that the default KIS adapter remains unavailable. Independent
Validation's review was `supported-with-limits`; its limitation was static
review only, while the full local test suite passed.

Reason: this closes the generic contract gap without making a target-derived
market intent look executable. The next execution question is not another
convenience wrapper: official public evidence must first resolve or reject the
known virtual-paper US sell route/TR-ID inconsistency before any header or
transport contract is considered.

## 2026-07-21 - Leave KIS virtual-paper US route/header contract unsupported

Decision: record the virtual-paper US limit-order route/header/TR-ID tuple as
`unsupported` and add no transport-facing contract. The pinned official KIS
example at revision `885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc` and the current
official `examples_user` order implementation both state live US sell
`TTTT1006U` and comment virtual sell `VTTT1001U`, while their generic demo
conversion transforms the real ID to `VTTT1006U`. The common official wrapper
uses a configuration-derived base URL and generic headers; it does not make the
virtual route/header/TR-ID combination explicit. The public portal landing page
did not supply a normative endpoint contract.

Claude's falsification-first verdict and independent Validation review are both
`unsupported`. The direct kill test is an official virtual-US order
specification or official testbed material that gives an unambiguous route,
mandatory headers, and sell TR-ID while reconciling the conflict. Until then,
the disabled adapter and body-only mappers remain unchanged. No credential,
account state, KIS call, order, cancellation, artifact, capital, or live
behavior occurred in this audit.

Reason: a plausible prefix rule could send a future paper order to the wrong
broker contract. The cost of preserving a disabled adapter is negligible next
to that blast radius. This conclusion does not block independent KIS market-data
capability work, which remains read-only and non-ordering.

## 2026-07-21 - Prepare a distinct bounded KIS raw-minute observation

Decision: keep the terminal `kis-paper-raw-minute-qualification-v4` result
immutable and prepare a new `kis-paper-raw-minute-observation-v1` rather than
reuse its date, `13:30` through `15:40` time window, reservation, artifact, or
qualification logic. The new path is literal `QQQ` / `NAS` raw `1m`, one paper
token, one first page, and at most one continuation. It defaults to no execute;
real execution requires `--execute`, a caller-declared date matching the current
New York weekday regular session, and `--confirm-regular-nasdaq-session` after
an independent holiday/early-close check.

It reuses only the existing generic external one-shot durability primitives with
its distinct objective ID. The observer retains only sanitized request counts,
timestamp bounds, field presence, and continuation facts outside memory. It
never writes raw rows, prices, volumes, cursors, token/account data, or response
bodies, and no result can promote timestamp semantics, completed bars,
retention/storage rights, derived timeframes, a model input, a strategy, an
order route, or execution authority. After `network_started`, any recovery is
retry-blocking. The guard is an operational request boundary, not a trading-
window policy. The marker namespace is objective-specific; the append-only
control ledger remains shared and malformed ledger evidence fails closed for
every objective rather than being repaired or ignored automatically.

Claude's falsification-first review and the independent Execution and Validation
reviews were all `supported-with-limits`. Focused fake-transport tests verify the
token and two-page bound, redaction, dry-run and invalid-session isolation,
marker/ledger recovery, external-artifact location, and no second GET after a
closed final page gate. No credential, KIS request, artifact, or reservation was
used while preparing this path.

Reason: this isolates a small, inspectable market-data fact while preserving
the permanent v4 no-retry state and keeping KIS order/account capabilities
separate from data observation.

## 2026-07-21 - Authorize owned KIS-paper scheduling and capacity qualification

Decision: the operator authorized `KIS_PAPER_*` read-only development calls for
active engine work and removed the prior scheduler prohibition. Codex may create
owned schedules for collection, research, validation, and paper-readiness work
without a fresh approval for each routine invocation, provided each job has a
named owner, explicit input/output bounds, durable evidence path, stop and
recovery behavior, resource/concurrency limit, and no secret output. This
authorizes goal-scoped scheduling, not a general agent platform or an unbounded
daemon.

The current `thericher-kis-raw-minute-observation-v1` Codex automation is a
self-expiring one-shot with current-session/date and official-calendar guards.
It cannot retry, roll forward to a later session, widen its endpoint/symbol/page
scope, call account/order/live endpoints, retain raw rows, or promote a KIS
capability. Claude's pre-schedule drift check was `supported-with-limits`: the
schedule must keep its guard in the invoked path and preserve the one-shot
reservation after any partial outcome.

Existing KIS evidence supports only the narrow claim that an unadjusted daily
page and two raw-`1m` pages were returned once for `QQQ`/`NAS`; it does not
support a large-history or bulk-archive claim. After v1 reaches a terminal
summary, the next data objective is a separately bounded capacity map that
measures daily retention anchors, raw-minute continuation depth, duplicate/gap
behavior, response outcomes, and first throttle/rejection. It will not use an
open-ended download or retain raw KIS bytes until source/storage rights and a
provenance manifest are established.

`KIS_LIVE_*`, paper submit/modify/cancel, nonzero paper capital, and
`THERICHER_MODE` changes remain separate decisions. The schedule authority does
not change them.

Reason: KIS-compatible data is central to the intended paper engine, and the
former blanket scheduler ban delayed useful evidence. Small staged capacity
tests provide more decision value than treating a few successful pages as proof
of an archive.

## 2026-07-21 - Close v1 and use independent KIS historical-capacity maps

Decision: close `kis-paper-raw-minute-observation-v1` as a terminal,
replay-blocked result. It ran once at `2026-07-21T13:43:14Z`, completed
`reserved -> network_started -> summary_written`, made one token attempt and
two raw-minute page attempts, and recorded only `rejected` /
`minute_response_rejected`. No account/order endpoint or raw market-data
retention occurred. The prior one-shot scheduler did dispatch late rather than
never dispatching; its exact delay cause is unproven, and the completed
automation remains paused.

Implement two fresh, independent capacity-map objective IDs instead of retrying
v1 or the older historical probe. `kis-paper-daily-capacity-map-v1` uses one
KIS Paper token for two fixed `QQQ` / `NAS` daily anchors and at most four
pages. `kis-paper-raw-minute-capacity-map-v1` uses its own token and reservation
for up to eight `QQQ` / `NAS` raw-minute pages. Each records only sanitized page
counts, date/timestamp bounds, page ordering, continuation, and boundary
duplicate/gap facts; a first response, throttle, or transport rejection ends
only that track. KIS read-only calls and goal-owned scheduling are already
authorized, so neither map has a regular-session calendar guard.

Claude's falsification-first verdict is `supported-with-limits`. Its decisive
reversal is reusing a spent objective ID/reservation or letting a track keep
probing after its first rejection. The maps remain capacity evidence, not an
archive or rights determination: raw KIS rows may move to `D:\market_data` only
under the next collector contract with recorded source/storage basis and
provenance.

Reason: actual KIS data calls now provide more useful evidence than preserving
a completed narrow observation as a standing constraint. Independent tracks
let daily-depth and minute-continuation evidence proceed without one endpoint
failure suppressing the other, while retaining a clear recovery boundary.

## 2026-07-21 - Record terminal KIS capacity-map evidence

Decision: retain the two capacity-map results as terminal `rejected` evidence
and do not replay either objective. `kis-paper-daily-capacity-map-v1` completed
with one token and three daily page attempts. Its first two `QQQ` / `NAS` pages
were accepted with 100 rows each and bounded dates `2026-07-17 -> 2026-02-24`
then `2026-02-24 -> 2025-10-01`; its third request rejected before the planned
second anchor. `kis-paper-raw-minute-capacity-map-v1` completed with one token
and two page attempts. Its first 120-row page was strictly descending and
one-minute-contiguous from `12:08Z` through `14:07Z`, advertised continuation,
and its second request rejected.

Each separate reservation and ledger records `reserved -> network_started ->
summary_written`, the summary SHA-256 matches its marker, and its artifact
directory contains only `summary.json`. The results establish accepted first
pages and daily two-page chronological progress only. They do not establish an
8-page minute depth, the second daily anchor, a rate-limit cause, cross-page
continuity, archive retention, storage rights, data/model qualification, or
paper-execution readiness. The first minute page has no prior boundary, so its
`boundary_contiguous_to_previous=false` is comparison-unavailable, not a gap.

Reason: the KIS endpoint is demonstrably callable and returns useful bounded
data, while the repeated continuation rejection requires a fresh paced
collection objective rather than a claim that KIS cannot supply history or an
unbounded retry loop.

## 2026-07-21 - Permit a bounded private KIS Paper cache

Decision: use the operator's stated private, personal, noncommercial, and
nonpublic project scope to permit a small KIS Paper market-data cache under
`D:\market_data`. The first collector remains limited to a named symbol,
endpoint, request budget, atomic output, and provenance manifest. It may not
publish, serve, redistribute, or imply an entitlement to a general KIS archive.

The public KIS Developers documentation identifies the overseas daily and
raw-minute endpoints and recommends managed long-lived access tokens. Its public
partner guidance requires exchange information-use contracts for affiliate or
corporate applications that surface market data; the review found no public
individual-account clause that clearly permits or forbids a local cache. Claude
returned `supported-with-limits`: the small, deletable cache is reversible at
low blast radius, but this is not affirmative proof of storage rights. Stop the
cache and escalate immediately if the applicable KIS API/account terms prohibit
retention or if the project becomes externally served or redistributed.

Reason: the operator explicitly requested KIS-derived learning data and has
authorized KIS calls. A two-page private daily cache has material development
value and can be contained, deleted, and audited without expanding to a public
market-data product.

## 2026-07-21 - Make KIS Paper and goal-owned scheduling standing authority

Decision: the operator has explicitly authorized all private `KIS_PAPER_*`
development work: credential use, market/account/order reads, paper
submit/modify/cancel, reconciliation, routine paper sizing, and goal-owned
scheduling. Remove the prior approval gates for a paper capital envelope,
profitability packet, dashboard, report family, trade count, and individual
paper call. Codex may now advance KIS Paper execution when its implementation is
ready rather than waiting for an additional business decision.

This does not change `KIS_LIVE_*`: live credentials and real-money routes stay
unreadable and unavailable. The surviving paper requirements are technical,
not approval gates: paper-vs-live route separation, no secret output, durable
idempotent intent before a paper side effect, and reconciliation before an
unknown outcome is retried. A goal-owned scheduler must preserve those same
properties; it may not convert a transient unknown outcome into unattended
duplicate submission.

Historical metadata-only probe artifacts remain immutable facts about those
past runs. They do not constrain current collection. New collectors use their
own manifests and record the actual raw-retention outcome without inheriting a
legacy reservation policy.

Claude's falsification-first verdict is `supported-with-limits`. Its reversal
condition is any implementation change that reaches a live route, exposes a
secret, or makes an interrupted paper submission unreconciled and duplicable.

Reason: the former interpretation made paper execution depend on process gates
that did not improve the engine. The operator wants rapid virtual-paper learning
while retaining only the minimum facts needed to keep paper behavior truthful
and recoverable.

## 2026-07-21 - Permit progressive private KIS data backfill

Decision: the standing KIS Paper authority includes progressive, resumable
private cache collection under `D:\market_data` for active engine work. A named
collection job still records source, scope, hashes, deduplication, storage, and
recovery facts, but a successful small pilot no longer requires a fresh operator
approval before a later scheduled or chunked backfill expands useful coverage.

The boundary is product use, not a page-count gate: keep KIS-originated data
local, private, unserved, and unredistributed; retain the D: free-space floor;
and stop only if applicable KIS or exchange terms prohibit retention. This does
not authorize a public market-data product or `KIS_LIVE_*` access.

Reason: learning-quality data needs to grow beyond a single two-page experiment,
and the operator explicitly prefers forward progress over approval scaffolding.

## 2026-07-21 - Record the first retained KIS Paper daily cache

Decision: accept the completed `kis-paper-private-daily-collector-v1` as the
first retained private KIS cache. It stored 199 unique `QQQ` / `NAS` daily rows
after deduplicating one exact overlap from 200 input rows. The manifest is at
`D:\market_data\us_equities\kis_paper_private\daily\snapshot=20260721T145228Z-qqq-nas-modp0-v1\manifest.json`,
with manifest SHA-256
`f124f47187ee5c3f2d1d840cd56de47a79ca4a8577026c5afbccef2c07b05c10` and raw
file SHA-256
`13a904a2e68c0405535fd67d96bd2b630036cc76ddc3d6b9d2a016e229291c4d`.

The collector's control record records the actual retained snapshot. This is
evidence bookkeeping, not a collection quota or approval mechanism.

Reason: it verifies the private D: retention path, atomic manifest/hash pairing,
deduplication, and pacing against a real KIS response. It supports the next
resumable daily backfill objective without reopening an approval question. It
does not by itself prove broad historical coverage, intraday availability,
model quality, or a live route.

## 2026-07-21 - Start resumable KIS private daily backfill

Decision: keep the completed one-shot QQQ collector as immutable evidence and
use a separate cursor/index worker for ongoing private KIS daily cache work.
Each invocation owns at most two daily pages, verifies a two-second in-chunk
pace, writes and hashes an immutable D: snapshot first, then atomically advances
only the corresponding symbol/date cursor. An orphan snapshot is reconciled
offline before a new KIS token request. Exact cross-chunk overlap is deduped;
conflicting overlap defers that symbol without cursor movement.

The first data-bearing worker chunks established `QQQ/NAS`, `SPY/AMS`, and
`IWM/AMS`, each with 199 unique rows from 200 input rows and one exact boundary
dedupe. Earlier NYS attempts remain in the external index as venue evidence:
SPY's token was rejected before daily data and IWM produced an accepted empty
response. Neither is canonical research history. The worker uses a persisted
two-minute shared retry after a token rejection or completed network chunk,
because a second token requested 24 seconds after a successful QQQ chunk was
actually rejected. This is a transport adaptation, not an approval or page
quota.

The cache remains `MODP=0_unadjusted`, private, local, unserved, and outside
Git. It is insufficient for model research until the strict common-session
loader freezes at least 756 completed sessions for all three ETFs. No GPU work,
model promotion, or corporate-action conclusion follows from these chunks.

Reason: the first real cache proved that a small retained KIS path works; a
minimal index/cursor lets it grow without reintroducing one-shot markers or
per-call operator gates, while preserving enough evidence to recover honestly.

## 2026-07-21 - Remove terminal one-shot KIS scaffolding and make paper authority explicit

Decision: remove the terminal metadata-only KIS historical probe, capacity-map,
and raw-minute qualification scripts, modules, and tests from the executable
surface. Their external summaries remain historical evidence, but no active
collector, schedule, or paper workflow inherits their one-shot reservation or
fixed non-retention behavior. The active KIS daily backfill records whether it
actually wrote a raw snapshot and is authorized to retain private market data on
`D:\market_data`.

The operator has confirmed standing authority for all private KIS Paper work,
including market/account/order reads, virtual order submit/modify/cancel,
routine sizing, reconciliation, raw data retention, and goal-owned schedules.
There is no paper capital, profitability, report, dashboard, trade-count, or
per-call approval gate. Existing KIS clients remain hard-coded to the virtual
paper host; `KIS_LIVE_*` and real-money routes remain unreadable and
unavailable. Paper idempotency, reconciliation, and secret-safe logging remain
technical correctness requirements rather than operator checkpoints.

Claude's short drift-check verdict was `supported-with-limits`: removing process
gates is coherent for virtual paper work, provided paper clients cannot build a
live route. The current market-data and account clients enforce an exact virtual
host, and future order transport must preserve that property.

Reason: the old one-shot controls were historical experiments, not a useful
engine capability. Leaving them executable and prominent made a factual
non-retention marker look like a continuing restriction and slowed the intended
data-to-paper development loop.

## 2026-07-21 - Use an offline KIS daily panel and fast local-paper smoke

Decision: the active private KIS daily cache is consumed through one offline,
hash-attested common-session loader for `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS`.
It has no KIS client, credential lookup, or network dependency; it accepts only
the fixed US panel and canonicalizes target order before deriving its dataset
identity. A `raw_market_data_retained` value is read only as evidence that a
chunk has bytes to load, never as a permission switch.

The first deterministic consumer is
`daily-three-etf-relative-strength-v0`: positive 20-session relative strength
selects at most one ETF, then local paper enters at `t+1` open and exits at
`t+2` open. It writes artifacts outside Git and all fills remain
`source: local_paper`. The 397-session run is an execution smoke, not a claim
of profitability. The 756-session target remains useful for a later frozen
comparative split, but it does not authorize or block KIS Paper work.

For bounded research runs, the append-only JSONL event log may defer its
rebuildable SQLite projection until the end of the run. This preserves event
replay while avoiding repeated full SQLite rebuilds; the default event-store
behavior remains immediate rebuild for ordinary callers.

Reason: the project needs a direct data-to-decision-to-local-paper loop now,
without turning a historical-data target or a factual retention marker into an
approval process. The deferred projection is a small runtime efficiency change,
not a new worker, scheduler, or report family.

## 2026-07-22 - Preserve validated daily partials and stop at the IWM source-quality limit

Decision: when a bounded KIS daily collection has a fully validated first page
but its continuation fails, commit that first page as a hash-attested `partial`
chunk, retain the safe failure reason, advance only to its oldest validated
date, and verify partial chunks in the same overlap and cursor-seam path as
ordinary committed chunks. A wholly invalid first page never advances. The
offline loader admits only these attested partial rows; it does not repair or
invent missing rows.

The live private IWM daily cache reached a 694-session common panel with QQQ
and SPY. Further expansion hit a KIS page containing one internally
OHLC-inconsistent row. A no-value structural diagnostic found 99 otherwise
parseable rows, but Claude's falsification review correctly rejected accepting
them: the inconsistency could indicate field misalignment and positional model
windows would be biased across a price-conditioned omission. The affected page
therefore remains excluded and IWM historical expansion stops at its current
lower boundary. This is a source-quality limit, not a KIS Paper, local-paper,
or model-research approval boundary.

The deterministic daily local-paper artifact now writes one external `run.json`
alongside JSONL/SQLite evidence. It records strategy parameters, local-paper
costs, data/index hashes, event hash/count, and code revision; daily decision
events are also projected into the rebuildable SQLite decision view.

Claude's verdict was `supported-with-limits` for preserving a validated first
page and `supported-with-limits` for a row-level exclusion only if the failed
predicate were a benign implausibility class. The observed predicate was OHLC
inconsistency, so row-level acceptance was not adopted.

Reason: this preserves useful verified KIS history without silently treating a
bad source row as clean data, avoids an infinite retry loop, and leaves the
available 694-session panel free to support the next bounded CPU validation.

## 2026-07-22 - Make private KIS Paper authority fully standing and markers factual

Decision: the operator has standing-authorized every private `KIS_PAPER_*`
engine action: market/account/order reads, virtual order submit/modify/cancel,
routine sizing, reconciliation, raw market-data retention on `D:`, and
goal-owned schedules. No paper-capital, profitability, dashboard, report,
trade-count, per-call, or past-run approval gate applies. Historical one-shot
records and `raw_market_data_retained` values are factual evidence for their own
run only; they cannot reserve, disable, or require a new approval for later
correctly scoped private-paper work.

`KIS_LIVE_*`, live routes, and real-money behavior remain unavailable. The
paper-only host boundary, secret-safe logging, intent-before-side-effect, and
unknown-outcome reconciliation remain implementation correctness requirements,
not operator approval checkpoints. This decision does not claim that an order
transport already exists; it authorizes building and running one once the
paper-only implementation is complete.

Claude's short drift-check was `uncertain`: the current read-only KIS client
has a client-side allowlist gap for injected transports, and no complete paper
order transport exists. Resolve that code gap before treating a future submit
adapter as paper-ready; it does not suspend data, research, local simulation, or
other already safe KIS Paper work.

Reason: earlier one-shot experiment remnants made an evidence field look like a
continuing permission system. The project needs fast, repeatable private-paper
iteration while preserving the few technical facts required to distinguish a
real stored snapshot or broker action from a failed attempt.

## 2026-07-22 - Freeze honest KIS daily comparative geometry and burn the exposed suffix

Decision: add a Data-owned hash-bound chronological slice helper and a small
offline comparative runner for the private KIS daily panel. The active
694-session panel has dataset hash
`sha256:4495dea26c5a27e6949b2b0dad05d82f4c555748191ed45cb880d7a242ced9b7`.
After two two-session gaps, its exact usable 690 sessions divide into 414
development (60%), 138 validation (20%), and 138 nominal holdout (20%)
sessions. Development and validation receive separate derived dataset hashes;
the runner never passes purge, embargo, or holdout bars to their relative-
strength, cash, or fixed-quantity buy-and-hold references.

The external contract is at
`D:\thericher-v2\model-artifacts\kis-daily-comparative-validation-v1\kis-daily-comparative-20260722T100000Z\contract.json`
with contract hash
`sha256:ca11faa8341cdfab97b8f98bb64e33d7a5c779019de324595f58fd619d6c0810`.
All comparator fills are replayable `source: local_paper`; each run retains a
run manifest, event hash, data hash, costs, and code revision outside Git.

The nominal final 138 sessions are **not sealed**. The prior 595-session
relative-strength smoke began on `2024-04-03` and continued through the current
panel end, which overlaps the new suffix. The contract therefore records
`burned_precontract` and permits only historical comparison, never a claim of
unopened holdout performance or model promotion. This is an interpretation
limit, not a KIS Paper, scheduler, GPU, or operator-approval gate; prospective
paper data can provide fresh out-of-sample evidence immediately.

Claude's falsification verdict was `uncertain`: it confirmed the two-session
gap covers the current `t+1` entry / `t+2` exit horizon, but correctly found
that no split mechanism existed and that the old smoke had already crossed the
proposed holdout. The new isolated slice contract resolves the first issue and
records the second instead of relabeling it away. The unadjusted
corporate-action limitation and fixed three-ETF survivor universe remain visible.

Reason: a small, reproducible local-paper comparison is useful now, but an
honest research record is more valuable than pretending an already observed
historical suffix is fresh validation data.

## 2026-07-22 - Add a narrow KIS virtual-paper buy canary without reopening live execution

Decision: the first executable KIS order surface is one separate, bounded
virtual-paper canary rather than enabling the generic broker adapter. It can
create only an explicit US whole-share **buy limit** request on the fixed
virtual host with `VTTT1002U`, optionally cancel that acknowledged order with
`VTTT1004U`, and check account/positions/open orders plus `VTTS3035R` before
replacing an ambiguous outcome. It cannot read `KIS_LIVE_*`, construct a live
host, create a sell request, or turn the dashboard into a broker client.

The canary validates host, method, path, query, headers, and body before every
transport invocation, including injected test transports. Its direct transport
disables inherited proxies and rejects redirects. A durable private intent is
fsync-persisted before submission; a later run reloads that intent by run ID
and compares stable identity fields rather than regenerating a fresh timestamp.
It never resubmits an unknown result. Private recovery state has its own Docker
volume; the shared runtime and external artifact contain only a fingerprint,
redacted order reference, status, counts, and emergency/reconciliation facts.

Claude's final falsification verdict was `supported-with-limits`. It found two
test gaps: body/header/query negative coverage and a post-cancel matching open
order path. Both were added. Its review also exposed a reference-prefix defect
between the sanitized canary and open-order identifiers; the adapter now
compares the common raw-ID hash under the open-order projection before it can
declare cancellation clean.

The first Docker canary recovery attempt found an artifact mount-path check
that treated `/app/model_artifacts` as Git-local; the exact mounted path is now
allowed while ordinary repository paths remain rejected. The first actual
virtual token/account attempt then returned `auth_rejected` before account data
or submit, so no KIS order was sent. The safe evidence is under
`D:\thericher-v2\model-artifacts\execution\kis-paper-canary` and
`...\kis-paper-console-bridge`; no token, account identifier, raw request, or
raw response was retained in Git or dashboard state.

Reason: this advances paper-execution learning with the smallest useful broker
surface while keeping recovery truthful. The external token rejection is a
credential/application recovery task, not a capital, profitability, or
one-shot approval barrier.

## 2026-07-22 - Preserve a safe KIS canary reconciliation cause

Decision: retain a closed-vocabulary reconciliation failure code in the
credential-free canary runtime projection, external evidence, and local
dashboard. The code is limited to implementation-owned values such as
`auth_rejected` and `transport_failure`; raw KIS response content, tokens,
account identifiers, and free-form exception text remain excluded. Older
runtime projections remain readable with no failure detail.

Reason: a generic unavailable state forced recovery to rely on a separate
console-bridge artifact. Preserving the known safe cause makes the next
operator recovery step explicit without creating a new approval gate, retry
loop, or secret-bearing observability path.

## 2026-07-22 - Keep ambiguous virtual-paper canary outcomes unresolved

Decision: persist the canary's cancellation choice with its private intent and
serialize all run IDs in one canary-state root during reconciliation and order
handling. A persisted submitted order resumes cancellation only when the broker
snapshot still matches its durable order identity. Any non-200 or non-success
submit response, cancellation ambiguity, or matching completion record after a
cancel remains `outcome_unknown`; it cannot become a clean rejection or trigger
a replacement submit. This is deliberately conservative about partial fills
until a separate order-specific fill-attribution contract exists.

Reason: independent execution review identified restart, response-ambiguity,
and concurrent-run paths that could otherwise leave an accepted virtual order
open or permit a false-clean outcome. The fixes are local to the narrow canary
and add no scheduler, report family, paper-capital gate, or live route. Claude
CLI was asked for a short falsification check but did not return before its
bounded timeout, so no conclusion relies on that absent verdict.

## 2026-07-22 - Default-progress KIS Paper authority and retention evidence

Decision: all private `KIS_PAPER_*` data, account, order, reconciliation,
routine sizing, raw-retention, and goal-owned schedule work proceeds under
standing authority. `KIS_LIVE_*`, live routes, and real-money behavior remain
unavailable. A historical `raw_market_data_retained: false` result records only
that its own snapshot did not retain raw bytes. It cannot reserve an endpoint,
disable a later correctly scoped job, create an operator question, or turn a
normal retry into a hold.

The collector and offline loader retain their separate data-integrity checks:
an absent raw file is not usable research input, and a hash/field mismatch is
reconciled rather than silently accepted. Those checks describe data truth and
broker recovery; they are not paper-development approval gates.

Claude's falsification-first verdict was `supported-with-limits`: static
inspection found no active source path that reads historical reservation files
or uses a false retention value to suppress a new KIS Paper call. The remaining
uses are per-snapshot provenance and data-integrity checks, which stay intact.

Reason: earlier one-shot probe artifacts made a factual storage field appear
like ongoing authority. The project should progress by default inside private
paper authority while retaining only the technical checks needed to distinguish
a stored snapshot from missing or corrupted data.

## 2026-07-22 - Retire the first frozen daily L2 trade-quality gate

Decision: run one fixed CPU L2-logistic `enter`/`abstain` gate over the existing
daily three-ETF relative-strength selector, without changing selection, sizing,
entry, hold, exit, or execution. The runner accepts only the hash-attested
prefix through its post-validation embargo, not a full catalog containing the
burned historical suffix. The Data loader still verifies complete raw-file
hashes, row fingerprints, and committed row counts before exposing the prefix.

The post-commit run at
`D:\thericher-v2\model-artifacts\daily-three-etf-l2-trade-quality-gate-v1\kis-daily-trade-quality-20260722T170000Z`
used commit `8a4c4a8b6309c4a2674a4abd9b7cbcc9314667c4`, 155 development
entries (85 positive, 70 negative), and 58 validation decisions. It improved
the observed candidate mean normalized after-cost return (`0.0001684` versus
`-0.0004646` selector), Brier score, and maximum drawdown, but the primary
moving-block-bootstrap lower bound and the 2 bp/side stress lower bound were
both `0.0`. It is `retired`; there is no retune, promotion, ensemble reuse, or
execution change. All replay fills remain `source: local_paper`.

Claude's prefix-design drift-check verdict was `supported-with-limits`: a
prefix process cannot re-derive the parent full-panel dataset hash, so integrity
rests on the frozen index hash plus manifest/raw hash and row-fingerprint
attestation, and on the frozen prefix segment hashes. The runner-level contract
test and core full-catalog rejection keep that limit explicit.

Reason: a compact linear baseline is useful falsification evidence, but a
positive average without a robust lower bound is not a trading claim. Refusing
the burned suffix at the core boundary preserves the useful historical result
without treating it as a route to repetitive tuning or a blocker for independent
paper and data work.

## 2026-07-22 - Expose the static Norgate trial panel as read-only Bar series

Decision: add one public loader in `data.norgate_trial_development_panel` for
the existing Norgate trial broad-D1 snapshot. It reuses the current verifier and
parses the same hash-attested panel byte buffer into immutable per-symbol D1
`CatalogedBars`; no Norgate SDK, network, credential, database parsing, cache
write, model artifact, KIS call, GPU job, selector, PnL path, or paper order is
involved. The loader preserves the original candidate ranks rather than
renumbering the 523 selected symbols, retains the exact source scope and
limitations, and requires caller-pinned dataset ID/hash.

The actual local snapshot re-attested as 523 symbols, 483 common sessions, and
252,609 rows from `2024-07-18` through `2026-06-22`; selected ranks span 1..541
because 18 candidate ranks are absent. The manifest's negative scope remains
unchanged: model, GPU, paper, campaign, ranking, point-in-time, and sealed
holdout uses are false. It makes no PnL or adjustment-semantic claim.

Claude's earlier direction check was `uncertain` only because its isolated
environment could not inspect the local D: snapshot. Direct manifest and
hash attestation resolved that factual question. Independent review found no
P1/P2 regression; its byte-swap and caller-identity concerns are now focused
tests rather than a new process layer.

Reason: the existing Norgate snapshot already had a verified source contract,
but only private parser access. A small immutable series boundary makes its
engineering data reusable without duplicating feature pipelines or laundering a
survivorship-selected trial panel into strategy evidence.

## 2026-07-22 - Remove paper-workflow approval remnants

Decision: retire the unused `paper_capital_proposal` module, its Compose
profile, and its `awaiting_operator_approval` / operator-ceiling workflow. The
operator has standing-authorized private KIS Paper sizing and submission, so a
separate capital proposal was process scaffolding rather than an execution
invariant. Positions and open orders remain inputs to deterministic sizing and
risk at the executor, not manual-approval blockers.

The KIS read-only reconciliation now reports only `read_only` scope and
`account_snapshot_complete`; it no longer emits a permanent
`safe_to_submit=false` proxy. A fresh executor still requires the fixed virtual
host, persisted idempotent intent, and reconciliation of an unknown broker
outcome immediately at the request boundary. The read-only console bridge also
persists a minimal failure diagnostic (allowlisted endpoint, transaction ID, and
HTTP status) outside Git so `balance_rejected` can be recovered without raw
broker bodies, account identifiers, or secrets.

Claude's short drift-check was `supported-with-limits`: removing workflow
latches is appropriate under standing paper authority, but the virtual-only
route must remain fail-closed and independently checked at every submit call.

Reason: the old capital proposal and read-only wording made implementation
capabilities look like operator approvals. Removing them shortens the paper
iteration loop while retaining the few technical controls that prevent an
unknown or live-routed broker side effect.

## 2026-07-22 - Project the KIS virtual request-limit code without raw responses

Decision: extend the KIS Paper read-only failure projection with an optional
`upstream_code` only when the in-memory `msg_cd` value is a short uppercase
alphanumeric code beginning with a letter and containing a digit. The
read-only discovery and console bridge share this validator; `msg1`, raw bodies,
tokens, account identifiers, order references, and arbitrary free text remain
excluded. The rebuilt bridge's one bounded invocation returned `EGW00201` at
`balance` / `VTTS3012R` with HTTP 500 and no order request.

KIS's official sample repository identifies `EGW00201` as a per-second request
limit exceedance. The next implementation is therefore a small injectable
monotonic pacing policy for real virtual read-only transport, not an automatic
retry loop, an approval gate, or a new broker surface. Claude's
falsification-first verdict was `supported-with-limits`: the rate diagnosis fits
the rapid six-request bridge sequence, but one observation does not establish
headroom or rule out every account-side cause.

Reason: a code-only diagnostic makes the recovery precise while preserving
private evidence boundaries. Source pacing targets the observed cause without
reintroducing one-shot reservations, paper-capital approvals, or secret-bearing
observability.

## 2026-07-22 - Pace virtual read-only requests instead of retrying the rate limit

Decision: put an instance-local, injectable monotonic pacing policy in the real
KIS Paper read-only urllib transport. It validates a request before pacing; the
first valid external dispatch is immediate, every later valid dispatch waits at
least one second, and a failed external attempt still consumes its slot. Fake
and offline injected transports remain unpaced. No retry loop, scheduler,
credential expansion, order route, or live route was added.

The rebuilt bridge completed one bounded account/open-order snapshot at
`20260721T223701135634Z-complete.json`, after the earlier `EGW00201` rate-limit
fact. Its sanitized artifact records only one position, zero open orders, USD
currency labels, timing, and a runtime hash; it emitted no raw account or
price data and sent no order.

Claude's short falsification verdict was `supported-with-limits`: a temporal
pacing fix is the smallest match for `EGW00201`, but one successful run does
not prove broad rate headroom or exclude every future account-side failure. The
canary's distinct transport needs the same behavior before the first authorized
virtual order cycle.

Reason: source pacing is an execution-reliability property, not an approval
gate. It resolves the observed virtual limit without reviving one-shot
reservations or hiding failures behind automatic retries.

## 2026-07-22 - Preserve the first ambiguous paced virtual canary outcome

Decision: reuse the read-only injectable monotonic request pacer in the real
virtual-paper canary transport. A current-image run,
`canary-20260721T225034Z`, completed its initial reconciliation and then ended
as `outcome_unknown` with `submit_transport_unknown`. Its safe evidence has no
broker order reference, but that absence cannot prove that KIS received no
submit side effect. Preserve the exact durable run for one reconciliation-only
recovery; do not retry, replace, modify, or cancel it based on this ambiguous
result.

The shared pacer affects real urllib transports only. Tests prove valid
external canary requests are spaced, a failed external attempt consumes its
slot, and invalid requests do not reach pacing or the network. Fake transports
remain immediate. Claude's concise pre-run falsification verdict was
`supported-with-limits`: the bounded virtual-only run, persisted intent, and
reconciliation plan were appropriate, while the external outcome itself still
needed recovery evidence.

Reason: retaining ambiguity is execution correctness, not a paper-capital,
profitability, one-shot, or manual-approval gate. It prevents duplicate orders
without blocking other authorized private Paper, data, or research work.

## 2026-07-22 - Complete one reconciliation-only recovery of the ambiguous canary

Decision: execute exactly one recovery of
`canary-20260721T225034Z` through its persisted `outcome_unknown` state. The
current image reached virtual account reconciliation without an order submit,
modify, or cancel route. Its sanitized evidence reports an available account,
zero open orders, zero completion rows, and no matching open/completion entry.
It still remains `outcome_unknown` with `reconciliation_unresolved`, because a
run without a durable broker order reference cannot turn the absence of current
matches into proof that its earlier submit had no side effect.

The recovery-only path now has a direct deterministic transport-counter test:
even with `cancel_after_submit=true`, an `outcome_unknown` resume may make the
token POST required for reconciliation but cannot send a buy-limit or cancel
POST. Claude's second falsification verdict was `supported-with-limits`; the
test covers the adversarial durable phase but cannot independently prove KIS's
external state beyond the bounded snapshot.

Reason: this preserves the ambiguous intent without creating an approval,
capital, profitability, or one-shot hold. A future separately identified
canary remains allowed after safe submit-failure diagnostics improve; it is not
a replacement submit for this run.

## 2026-07-22 - Classify a fresh virtual canary rejection without retaining its body

Decision: classify non-200 canary submit responses as closed `4xx`/`5xx` codes,
classify an already-known rate-limit code as `submit_rate_limited`, and classify
a non-success KIS response as `submit_kis_rejected`. The current implementation
does not retain the KIS response code or message text. Focused tests inject a
KIS-style code and secret-like free text, then prove that only the closed result
reaches runtime/evidence.

One independent current-image canary, `canary-20260721T232137Z`, reached clean
initial reconciliation and produced `submit_kis_rejected`. Its safe evidence
reports an available account, zero open orders/completion rows, no matching
entry, and no broker order reference. The state remains `outcome_unknown` to
avoid guessing a side effect or retrying this specific intent.

Claude's pre-run falsification verdict was `supported-with-limits`. It accepted
the virtual-only surface, raw-message omission test, and one-run blast radius,
while noting that its conclusion depends on the reported implementation and
cannot itself inspect the broker route.

Reason: the new diagnostic narrows a real KIS rejection without creating a
permission gate. The next independent run may project a strictly validated
short KIS-style code when present, which can guide configuration correction
without retaining a raw broker body or making a duplicate submission.

## 2026-07-22 - Preserve a missing safe KIS rejection code and avoid mapping guesses

Decision: retain a strict shared validator for a short KIS-style upstream code
and project it only when `msg_cd` matches. The state, runtime, evidence, and
console projection accept the optional safe field while remaining compatible
with prior files that lack it. Tests prove a valid code is retained and invalid
code or free-form `msg1` is absent everywhere outside the transient response.

The independent virtual canary `canary-20260721T233837Z` reached clean initial
reconciliation and again returned `submit_kis_rejected`, but no valid safe code
was available. It is preserved and not retried. Official KIS sample code
confirms the existing virtual US buy endpoint, `VTTT1002U`, and field set; its
price endpoint documents `last` and `zdiv`. The direct evidence therefore does
not justify changing the documented order mapping.

Reason: a fixed `$1` limit submitted outside a known US session is a weak
execution probe. The next independent canary should derive a private limit from
an allowed KIS quote and use a regular-session run window. This is an execution
quality improvement, not an operator approval, capital, or one-shot gate.

## 2026-07-22 - Remove artificial KIS Paper quotas and approval latches

Decision: the operator's standing private `KIS_PAPER_*` authority covers
repeated market/account/order calls, submit/modify/cancel, routine sizing,
raw-market-data retention, and recurring goal-owned Paper schedules. There is
no capital-envelope, per-call, per-goal, one-shot, report, profitability, or
trade-count approval requirement. Paper cadence and the number of distinct
virtual intents are ordinary Execution choices.

An ambiguous broker result still pauses only replacement of its exact durable
intent until reconciliation. It does not freeze a distinct later Paper intent,
another due schedule, Data collection, Engine Research, or the company goal.
`raw_market_data_retained: false` is only provenance for the old snapshot; it
cannot suppress later collection or broker work. A missing raw file remains
unusable input, and a hash/field conflict remains a data-integrity fault, but
neither is a permission boundary.

The retained technical invariants are intentionally narrow: virtual-paper host
isolation, no secret/raw broker output, persisted idempotent intent before a
Paper side effect, reconciliation before resubmitting that same ambiguous
intent, source pacing, and data-integrity/provenance checks. `KIS_LIVE_*`, live
hosts/routes, and real-money behavior remain unavailable. Research diagnostics
must describe compatible GPU-backend availability rather than imply a missing
operator approval.

Claude's falsification-first verdict was `supported-with-limits`: removing
artificial Paper latches is compatible with standing authority provided the
virtual-host pin and no-resubmit-until-reconciliation rule remain non-negotiable.

Reason: v1-style approval scaffolding and one-shot markers were consuming more
development time than they protected. The private Paper system should iterate by
default, while technical controls preserve correct attribution and prevent a
duplicate or live side effect.

## 2026-07-22 - Add a quote-derived recurring virtual-paper session

Decision: add one narrow `kis-paper-session` worker and Compose profile. During
the weekday 09:30-16:00 America/New_York time window it sends only the
allowlisted virtual SPY quote request (`HHDFS00000300`, `NAS`, `SPY`), parses
only a KIS-success result plus positive `last` and valid `zdiv` in memory,
derives a one-share limit 25 bps below last with downward decimal rounding, and
passes the existing private intent to the virtual-only canary. It rechecks both
limit expiry and the weekday ET time window immediately before submit, then
requests cancellation after accepted submission. Quotes, prices, credentials,
account identifiers, raw broker data, and raw order identifiers cannot enter the
public runtime, evidence, Git, or console boundary.

The scoped external local automation `thericher-kis-paper-quote-session` runs
the worker once per weekday at KST 23:35, which remains inside the US regular
time window across daylight-saving changes. It replaces two paused historical
one-shot raw-minute automations that no longer matched authority. The first
off-session Docker exercise safely returned `not_due` / `outside_regular_session`
and wrote only sanitized external evidence; the first due result remains a
runtime observation for the schedule, not a new approval step.

Claude's falsification-first verdict was `supported-with-limits`. It would
reverse only if a Live variable, host, or route became reachable from the submit
path. The implementation hard-pins the virtual host, injects only
`KIS_PAPER_*` into the service, and tests the absence of `KIS_LIVE` from Compose.

Reason: a quote-derived limit makes the Paper probe a realistic execution
learning loop instead of another fixed-price diagnostic. A single narrowly owned
daily worker advances Paper evidence without rebuilding a broad scheduler,
capital-approval chain, or agent platform. Its weekday time-window helper does
not assert a complete holiday or early-close calendar; that is a source-semantics
question for the next KIS-native intraday data objective, not a manual approval
gate.

## 2026-07-22 - Add resumable KIS-native intraday cache under standing Paper authority

Decision: replace the historical minute-probe shape with a reusable private
cache for `QQQ/NAS` and `SPY/AMS`. The Paper-only 1m client retains immutable
provider-field gzip rows, a manifest/raw hash, exact-overlap fingerprints, and
an atomic per-target `NEXT`/`KEYB` cursor below
`D:\market_data\us_equities\kis_paper_private\intraday`. A failed or empty
attempt writes no data-bearing chunk; it cannot create a fixed
`raw_market_data_retained: false` latch. An exact overlap is deduplicated;
different fields for the same KIS Korea timestamp reject cursor advance.

The offline loader uses KIS's explicit Korea timestamp fields as the canonical
UTC basis and marks a bar incomplete if its end follows the rounded collection
minute. It reuses the existing explicit-session resampler for 5m, 10m, 1h, and
3h output. This is intentionally not a US regular-session or source
open-versus-close claim: holiday, early-close, exchange timestamp, and session
semantics remain `observed_unqualified` until source evidence says otherwise.

The first actual bounded cycle stored 239 deduplicated 1m rows for each target,
with one exact page-boundary overlap per symbol. QQQ covered 20:01-23:59 UTC
and SPY 19:58-23:59 UTC on 2026-07-21, so both are extended-session evidence.
A local-paper multitimeframe smoke consumed QQQ's cache with 1m/5m/10m/1h
cells only; its short history correctly left 3h execution unready. No price,
credential, account, order, or raw response body entered Git, console output,
or generated model artifacts.

Claude's falsification-first verdict was `supported-with-limits`. It would
reverse if a live/order route became reachable from the collector or if KIS
minute fields could not yield an honest UTC conversion. The current allowlist
has no order/live route, and the explicit Korea fields provide the selected
fixed-offset basis. Source session interpretation remains a separate data fact,
not an approval boundary.

Reason: the engine needs reusable KIS-reconstructible input bytes more than
another terminal observation. The narrow cache keeps moving under the operator's
full Paper authority while preserving only the technical checks needed to make
later model and paper evidence reproducible.

## 2026-07-22 - Remove residual KIS Paper permission latches from current paths

Decision: the operator has standing-authorized all private `KIS_PAPER_*` work:
credential use, market/account/order reads, virtual submit/modify/cancel,
reconciliation, routine paper sizing, raw local market-data retention, and
goal-owned schedules. No one-shot, per-call, capital-envelope, trade-count,
profitability, report, or historical-retention marker may pause a fresh
correctly scoped KIS Paper action.

An old `raw_market_data_retained: false` record is now ignored by the active
intraday collector and offline loader before cache validation, deduplication,
cursor handling, or bar consumption when it is a legacy marker without a cache
snapshot. A real deferred snapshot remains historical recovery evidence only.
Malformed retained data and conflicting retained rows remain data-integrity
faults, not permission checks.

The remaining technical invariants are deliberately narrow: virtual-paper host
and route isolation, no secret/raw broker output, persisted idempotent intent
before a Paper side effect, and reconciliation before reusing that exact
ambiguous intent. They never block distinct Paper work. `KIS_LIVE_*`, live
hosts/routes, real-money behavior, paid commitments, unclear rights, and public
exposure remain outside this authority.

Claude's falsification-first verdict was `supported-with-limits`: the current
virtual host pin, allowlists, Paper-only variables, and per-intent recovery
semantics support removing permission latches; those technical invariants need
ongoing tests rather than a new approval workflow.

Reason: historical experiment metadata had an accidental path to look like a
global stop condition. The private Paper system should iterate by default and
record technical evidence without recreating v1-style process controls.

## 2026-07-22 - Separate prospective intraday head cache and first complete-session replay

Decision: retain the cursor-resuming intraday cache for historical continuation,
and add a sibling `intraday-head` cache for fresh KIS source pages. Head mode
does not move the backfill cursor and is invoked by one bounded local data-only
automation. It receives only Paper market-data credentials and exposes no
account, order, or live route.

`us_equity_2026_session` maps the published Nasdaq/NYSE 2026 holiday and early
close calendar into explicit UTC session windows. It is a calendar source, not
a claim about KIS bar timestamp or open/close semantics. A 390-minute QQQ slice
for 2026-07-21 completed the CPU cache-to-local-paper baseline across
1m/5m/10m/1h/3h. Its external sanitized artifact records replayability only;
it is not profitability, model-selection, or GPU-training evidence.

Claude's falsification-first verdict was `supported-with-limits`: separate
roots/cursors, Paper-only routing, and an explicit calendar support the design;
schedule time alone cannot prove source coverage. The implementation preserves
that distinction and retains no raw quotes, credentials, account identifiers,
or broker output in Git.

Reason: prospective KIS-compatible cache accumulation can proceed continuously
without corrupting historical recovery state, while a complete session proves
the local replay interface before multi-session research begins.

## 2026-07-22 - Freeze the first KIS-native chronological intraday CPU baseline

Decision: use the reattested QQQ/NAS cache to freeze the latest 20 complete
regular 2026 sessions, 2026-06-23 through 2026-07-21, as 10 development
sessions, one unused 2026-07-08 purge session, and 9 validation sessions. The
first contract fixes completed 1m decisions at offsets 89 through 387, next-bar
open entry/following-bar-open exit, 1 bp per-side fee, 2 bps per-side slippage,
and `flat`, `always_long`, and `previous_bar_direction` local-paper references.
The external manifest is
`D:\\thericher-v2\\model-artifacts\\kis-intraday-cpu-campaign\\qqq-20260623-20260721-r1\\summary.json`.

All six actual replay cells retained only `source: local_paper` fills and their
JSONL event counts match both the summary and reconstructed SQLite state. Both
non-flat references were negative after the stated costs in development and
validation. This is a descriptive baseline to beat, not a profitability,
promotion, ensemble, or model-selection conclusion.

Claude's falsification-first verdict was `supported-with-limits`: the split,
in-session signal geometry, and target timing avoid the named leakage and
cross-session failures, but nine validation sessions have very low statistical
power. That limit constrains interpretation, not data collection, Paper work,
or independent feature preparation.

Reason: an explicit KIS-only baseline is more useful than extending isolated
single-session smoke work. It gives the next candidate a fixed costed comparator
without importing v1-style report or approval scaffolding.

## 2026-07-22 - Make intraday discontinuities and retries explicit evidence facts

Decision: a multi-session local-paper validation may permit only the exact
close/open boundary between consecutive declared `SessionWindow` values. A bare
timestamp cannot nominate an arbitrary intraday gap, and a target may not cross
that boundary. Completed campaign replay uses a JSONL-authoritative event log
and rebuilds SQLite before evidence is emitted.

An optional safe attempt label propagates from the intraday campaign runner into
each baseline run ID. A restart uses a new label and separate external work and
artifact paths; completed evidence is never overwritten or silently reused.

Reason: the controls preserve input meaning and recoverability after an
interruption. They are data/execution correctness properties, not a new approval
gate, one-shot quota, or scheduler platform.

## 2026-07-22 - Share explicit exchange calendar eligibility with the Paper quote session

Decision: the virtual-paper quote session delegates its pre-credential session
check to `us_equity_2026_session`. It accepts only an explicit published regular
or early-close window, returns `session_unavailable` for holidays and dates
outside the supported 2026 source scope, and performs no environment or KIS
transport access in those cases.

Reason: the same narrow calendar source now governs research session selection
and quote-session timing. This removes a weekday-only mismatch without changing
Paper authority, widening a route, or creating a schedule approval condition.

## 2026-07-22 - Record the first KIS intraday breadth and CUDA pipeline evidence

Decision: retain the frozen QQQ 20-session contract as 10 development sessions,
one unused purge session, 5 descriptive candidate-comparison sessions, and 4
unmaterialized later sessions. The latter split is only a small research
interpretation control after Claude's `supported-with-limits` warning about
choosing from nine PnL observations; it does not gate KIS Paper data, schedules,
account work, orders, or operator action.

The CPU candidate replay wrote external local-paper evidence for `flat`,
`fixed_momentum`, and `regularized_linear`; all were non-positive after costs on
the comparison slice, so no candidate is selected. The fixed development-only
PyTorch GRU smoke then ran in the network-disabled Docker research profile on
the RTX 4090. It uses 2,990 90x3 sequences, writes only a sanitized JSON summary
under `D:\thericher-v2\model-artifacts`, and writes no checkpoint or promoted
model. The cache path check explicitly recognizes `/app/market_data` only as the
named external D: mount when the repository root is `/app`.

The follow-up Claude CLI request for the fixed smoke timed out without a
verdict; it did not determine this decision because the architecture and
no-selection scope were fixed before the CPU result.

Reason: this adds actual KIS-compatible CPU and CUDA research evidence without
reintroducing one-shot latches, artificial Paper approvals, or a GPU-driven
model-promotion claim.

## 2026-07-22 - Precommit the first fixed KIS intraday sequence architecture screen

Decision: run exactly LSTM, causal TCN, and compact attention on the frozen
QQQ 20-session KIS input with fixed seeds, 16 hidden dimensions, 8 epochs, and
a `0.5` decision threshold. Before comparison samples materialize, write a
sanitized immutable external precommit containing all configurations, the
development-only input hash, the fixed five-session replay scope, and the
explicit joint-report/no-winner policy.

The actual network-disabled Docker run used PyTorch CUDA 12.8 on the RTX 4090
and trained each architecture on 2,990 development-only 90x3 sequences. Local
paper replays on the five comparison sessions produced after-cost PnL of LSTM
`-639.3858`, causal TCN `-5.9777`, and compact attention `0.0000`. The external
summary is
`D:\thericher-v2\model-artifacts\kis-intraday-sequence-architecture-screen\qqq-20260623-20260721-sequence-architecture-r1\summary.json`.

Claude's falsification-first verdict was `supported-with-limits`: a fixed joint
screen is acceptable only when settings and replay eligibility are committed
before comparison data is used. The implementation follows that correction.
The outcome has no winner, promotion, ensemble, profitability, or KIS Paper
authority effect; later confirmation sessions remain unmaterialized.

Reason: this broadens architecture evidence without silently selecting from a
small comparison slice or turning research evidence into a Paper-work gate.

## 2026-07-22 - Add a local KIS Paper operations projection and directional controls

Decision: keep the emergency stop/cancel state separate from reversible
`pause_buys` and `pause_sells` state. The local web process may change only that
small local state; it has no KIS credentials, broker client, private intent
state, or `D:` market-data mount. The active buy canary/session checks
`pause_buys` before loading configuration or making a KIS call. `pause_sells` is
persisted now and will be consumed only by a later deterministic sell executor;
it can never block a hard-risk exit.

The same console reads a metadata-only intraday freshness projection. It shows
cache mode, safe stream identity, age, outcome class, and chunk counts, but not
raw rows, values, paths, hashes, manifests, account identifiers, or secrets.
An old `raw_market_data_retained: false` marker remains a factual absence of
bytes for that historical result and is ignored for later collection and for the
freshness count; it is never a Paper or schedule latch.

A due quote-session outcome that ends before a canary intent exists publishes a
fresh sanitized canary runtime with status `unavailable`. This records that the
current session produced no intent without overloading a prior canary result or
exposing the quote/error body; detailed safe reason remains external evidence.

Reason: this gives the operator immediate, local operational control and useful
current data visibility without adding a broker-capable dashboard, a report
chain, a capital gate, or another approval mechanism.

## 2026-07-22 - Reject blank KIS Paper price-detail fields as a canary input

Decision: add one exact, Paper-host-pinned SPY `price-detail` structural probe
using the official route `HHDFS76200200`, `AUTH=""`, `EXCD=NAS`, and `SYMB=SPY`.
It classifies only HTTP status, mapping/result shape, and the validity states of
`last`, decimal scale, and tick fields. It cannot produce a price, create an
intent, submit an order, retain a raw response, or widen the canary route.

The live 2026-07-22 Paper probe received a success-shaped mapping but all three
required fields were blank. Therefore `price-detail` is rejected as the current
explicit-limit conversion candidate. This is an input-evidence conclusion, not
a permission, capital, retention, scheduler, or one-shot condition: another
correctly scoped Paper action or candidate proceeds normally.

Claude's falsification-first verdict was `supported-with-limits`: the route is
acceptable only as the exact tuple above, with category-only output and no path
from its response into an intent or order. The implementation follows those
limits.

Reason: it resolves a concrete KIS compatibility question without inventing a
price or turning a blank provider field into another Paper approval process.

## 2026-07-22 - Establish the AMEX SPY Paper price input and read-only recovery

Decision: retain the earlier `NAS/SPY` blank-field probe as a rejected historical
candidate, then use the checked official KIS sample source revision
`885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc` for the actual mapping: `AMS` on
the SPY asking-price and price-detail endpoints, and `AMEX` on the virtual
order. The in-memory limit adapter accepts a KIS-success asking-price last only
when its Korea timestamp is at most 120 seconds old, its decimal scale matches
price detail, and price detail's positive `e_hogau` tick divides the price. The
limit is rounded to that tick. Quote values and payloads remain transient.

The first independent canary using that contract reached its persisted
`outcome_unknown` / `reconciliation_unresolved` path. A same-run read-only
reconciliation later found only sanitized aggregate account facts and made no
buy or cancel request. Add `reconcile_kis_paper_canary_unknown_run` for this
exact recovery class: it reconstructs all decision fields, including original
timestamps, solely from durable state; accepts only `submission_started`,
`outcome_unknown`, or `cancel_started`; and rejects missing, mismatched,
submitted, terminal, or intent-recorded state before network access. If state
disappears between the initial check and the recovery branch, the branch raises
`recovery_state_missing` rather than creating a fresh intent.

Claude's falsification-first verdict was `supported-with-limits`. Its strongest
kill tests were a reachable buy/cancel route, a recreated intent, identity
change, or private-value output. Focused tests cover all of those library-level
routes, including the deleted-state race; the small CLI delegates only to that
covered helper.

Reason: the engine can now use a truthful, KIS-compatible transient price input
and recover an ambiguous Paper result without turning a historical blank field,
unknown intent, or one-shot marker into an approval hold for later distinct
Paper work.

## 2026-07-23 - Use final-limit tick validity, not raw-last tick validity

Decision: the transient KIS asking-price `last` may have finer precision than
the KIS-reported `e_hogau` increment. Do not reject a fresh otherwise valid
source last merely because it is not itself a multiple of the submit tick.
Require the tick to be positive and representable at the declared decimal scale;
derive the private limit with downward rounding, then require that final limit
to be tick-aligned before it can reach the virtual Paper route.

The 2026-07-22 15:27 ET current-image virtual session then reached the safe
submit category `acknowledged_order_reference`, completed requested cancellation,
and reconciled cleanly. Its new host-only lifecycle projector emits opaque
identity references plus `cancelled`, `clean`, and `not_eligible`; it reads an
existing evidence file only and makes no KIS call or credential read. It does
not claim a fill, realized PnL, model edge, or a reason to throttle later
distinct authorized Paper work.

Claude's falsification-first verdict was `supported-with-limits`: preserving a
tick-aligned final order remains necessary, but treating the raw provider last
as a required tick multiple was an unjustified availability gate. The focused
tests cover a sub-tick source last that yields a valid rounded final limit, the
category-only response parser, and the host-vs-container artifact-root split.

Reason: this removes a false negative observed in an authorized Paper session
while retaining the actual execution invariant. It reinforces that historical
`raw_market_data_retained: false` markers and old one-shot evidence remain
provenance/recovery facts only, never Paper permissions or general work stops.

## 2026-07-22 - Reaffirm default-progress private Paper authority

Decision: treat every private `KIS_PAPER_*` data, account, order,
modify/cancel, reconciliation, sizing, retention, and goal-owned scheduling
action as standing-authorized. Do not create or revive a capital envelope,
profitability threshold, report, trade-count limit, one-shot marker,
raw-retention value, input-quality result, model outcome, or manual Paper
checkpoint that blocks a different correctly scoped action.

`raw_market_data_retained: false` remains an immutable fact that the named
snapshot has no raw bytes to consume. It does not authorize invented data, but
it also cannot reserve, freeze, or disable a later collection, Paper order, or
schedule. Likewise, an unavailable input or blank price contract yields a
scoped no-intent for that exact decision, and an unknown broker outcome delays
only replacement of that exact durable intent until reconciliation. Existing
facts and identity records are preserved rather than deleted or rewritten.

Claude's falsification-first verdict was `supported-with-limits`: retain
Paper-host pinning, secret redaction, durable intent-before-side-effect, and
exact-intent reconciliation. Keep `KIS_LIVE_*`, real-money behavior, paid
commitments, unclear rights, and public exposure outside this standing scope.

Reason: the operator explicitly prefers development and virtual-paper learning
to proceed by default. The remaining technical controls preserve truthful
evidence; they are not approval gates or a source of process scaffolding.

## 2026-07-22 - Bridge immutable research receipts to paper-ready decisions

Decision: introduce a small pure execution bridge with three distinct outcomes:
an eligible receipt can create a deterministic broker-free `local_paper` buy
intent using its full immutable decision identity; the same receipt can prepare
the existing KIS Paper canary decision only when Execution provides matching
symbol/venue/whole-share binding and a fresh final-limit proof; every other
case produces a sanitized no-intent fact. The bridge has no credential,
environment, network, KIS-client, or live-route dependency.

The first external receipt uses the frozen QQQ/NAS 20-session KIS-native input
and the current observed capability contract. It is stored only at
`D:\thericher-v2\model-artifacts\kis-paper-baseline-receipt\qqq-20260623-20260721-receipt-r1\receipt.json`.
The contract is currently unqualified, so that exact receipt is an honest
`abstain` / `input_unavailable` / local no-intent result. It does not freeze
independent collection, scheduled canaries, or another Paper decision.

For future receipt-shaped canaries, sanitized lifecycle evidence includes the
full opaque receipt digest as `attribution_ref`; old canaries remain compatible
without it. This makes model-to-execution joins exact without exposing a symbol,
price, quantity, account value, raw broker payload, or credential.

Claude's prior `supported-with-limits` bridge review applies: treat the full
input digest as authoritative, prove offline isolation in tests, and do not
rehydrate an `abstain`, expired, future, or mismatched receipt into an order.

Reason: this advances the data-to-decision-to-paper attribution loop without
mistaking a current data limitation for a permission gate or fabricating a
model-driven virtual order.

## 2026-07-22 - Remove all non-live Paper permission latches

Decision: reaffirm that every private, non-live Data, Research, and KIS Paper
action is standing-authorized, including virtual account/market reads, paper
submit/modify/cancel, reconciliation, data retention on `D:`, and recurring
goal-owned schedules. Do not create an `awaiting_operator_approval` state,
capital envelope, profitability threshold, trade-count quota, one-shot
reservation, raw-retention switch, report, model-result gate, or
`safe_to_submit` proxy for this work.

`raw_market_data_retained: false` and a completed/failed/blank one-shot result
are immutable facts about their own evidence only. They neither grant nor
withdraw authority for later data collection, virtual Paper orders, or a
schedule. A call may reject only its own technical request when the route is
not pinned to the KIS virtual host, its durable identity conflicts, or its own
previous submission is unknown and must be reconciled. That result never
pauses a distinct intent or another ready lane. `KIS_LIVE_*`, real-money
behavior, and live routes remain prohibited even if no funds are currently
present.

Claude's falsification-first verdict was `supported-with-limits`: retain
call-time virtual-host isolation, secret safety, paper-scoped durable identity,
and exact-intent reconciliation; retain source-rights and disk constraints only
for the affected cache. These are technical truth and containment properties,
not operator approval checkpoints.

Reason: the operator explicitly prioritizes rapid autonomous development and
virtual-paper learning over process scaffolding, while preserving the hard
non-live boundary and truthful recoverable evidence.

## 2026-07-22 - Add a point-in-time daily SPY receipt path

Decision: add a compact forward `SPY/AMS` D1 head cache and connect it to a
transparent two-close daily receipt, local-paper replay, and receipt-aware KIS
Paper canary preparation. The collector retains only prior completed US
exchange sessions and atomically hashes one immutable source. A session runner
selects either that head or the older daily source as a whole, records first
local availability, and requires the resulting receipt to be current for the
next eligible session. It never combines rows across the sources, uses a daily
close as an order price, or accepts the current exchange date as a completed
bar.

Execution binds an eligible receipt only to `SPY` / `AMEX`, one whole share,
and an independently observed fresh `AMS` final-limit proof. Its durable
run/client identity derives from the full receipt digest. A repeat can recover
the exact intent but cannot submit it again with a changed price. The initial
scheduled runner uses the existing cancellation canary, so its output is
execution lifecycle evidence rather than a realized-PnL or model-quality claim.

The first private head snapshot was collected outside Git with 99 prior
completed sessions through 2026-07-21. A manual Docker run after the valid
daily window produced a safe no-intent and made no quote/order call. New
Windows tasks collect the head at 22:15 KST and run the session at 23:50 KST on
Tuesday through Saturday. These are recurring private Paper jobs, not one-shot
approval latches.

Claude's falsification-first verdict was `supported-with-limits`: preserve the
current-session exclusion, whole-source selection, immutable source hashes,
virtual-route isolation, redaction, and exact-intent recovery. The next change
may add an explicit receipt-linked Paper position/exit lifecycle, but must not
create a live route or reinterpret a cancellation as PnL.

## 2026-07-22 - Add receipt-linked KIS Paper SPY position lifecycle

Decision: extend the daily SPY slice from a buy-only cancellation diagnostic to
a receipt-linked one-share target-position loop. A ready `enter` receipt may
produce only `flat -> buy one SPY/AMEX share`; a ready `exit` receipt may
produce only `one SPY/AMEX share -> flat`. Execution gets that state from one
fresh complete KIS Paper account/open-order snapshot, not from a prior intent,
acknowledgement, local cache, or inferred fill. An existing SPY open order,
stale snapshot, unsupported inventory, or target already met yields a scoped
no-intent result for that invocation.

The virtual sell adapter uses the same fixed Paper host and order endpoint as
the buy adapter, with the official KIS Paper sell TR ID `VTTT1001U` and
`SLL_TYPE="00"`; the existing Paper buy route remains `VTTT1002U`. The pure
field mapping is cross-checked against the pinned official KIS sample revision
`885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc`. Durable intent state carries an
explicit sell side while preserving legacy buy fingerprints. The stable
receipt-derived run identity remains shared, so a replay with a changed quote
reuses the first price proof and a replay with an opposite side fails its exact
identity check before a request can be sent.

Sanitized execution evidence may expose categorical `order_side`, lifecycle
state, target-resolution state, and `pnl_status: not_observed`. It must not
claim a fill, cost basis, account value, cash value, or realized PnL until a
later authoritative KIS completion/reconciliation contract exists. The daily
compose service no longer passes `--cancel-after-submit`, allowing a valid
Paper limit order to participate in a position lifecycle; the standalone
canary retains its immediate-cancel diagnostic behavior.

Claude's pre-implementation falsification-first verdict was
`supported-with-limits`. The implemented kill tests cover virtual-only sell
routing, changed-quote idempotency, same-receipt directional exclusion, stale
account facts, open-order conflicts, redaction, and no fabricated PnL. A
credential-free direct Docker exercise of the daily service produced only a
safe stale-receipt no-intent; it sent no account, quote, or order request.

Reason: this creates a truthful first Paper position loop without adding a
live route, a quota, a model-promotion gate, or a report system.

## 2026-07-22 - Add receipt-linked KIS Paper observation without terminal inference

Decision: move the fixed virtual `VTTS3035R` same-day history query into the
structurally read-only KIS client and add a separate receipt observer for one
durable `receipt-<sha256>` SPY/AMEX intent. The observer can acquire only a
Paper token plus fixed read-only `GET` endpoints; its module contains no
submit, modify, cancel, or live-route capability. It reads private state only
to compare a raw KIS order ID in memory, then writes a categorical immutable
artifact outside Git.

An exact current open-order match is sufficient for `open`. The current
`inquire-ccnl` contract is sufficient only for `same_day_id_seen` or absent;
it is not an explicit fill, cancellation, price, quantity, or realized-PnL
fact. The account snapshot is aggregate and cannot assign an inventory change
to this receipt. Accordingly this first observer emits `not_submitted`,
`open`, `outcome_unknown`, or `unavailable` as supported and always emits
`pnl_status: not_observed`; `filled` and `cancelled` remain unavailable until
an official per-order terminal field is independently qualified. A missing,
stale, corrupt, or ambiguous observation affects only that receipt and never
acts as a Paper authorization, quota, schedule, or recovery latch.

Claude's pre-implementation falsification-first verdict was
`supported-with-limits`: read-only isolation must be structural; an ID sighting
is not a fill; aggregate positions are not receipt attribution; unavailable
facts must remain unavailable; and replay/redaction must be tested. The focused
tests cover these kill conditions, including no credential/network path for an
unsubmitted or corrupt state and replay without changing private state.

Reason: this makes the first Paper lifecycle observation usable by future PnL
attribution without turning broker ambiguity into a fabricated strategy result
or adding another operator approval mechanism.

## 2026-07-22 - Link the daily SPY Paper session to its exact observer

Decision: the existing scheduled daily SPY session now invokes the read-only
receipt observer only after its canary returns a run ID that exactly equals
`receipt-<prepared receipt digest>`. The safe daily outcome requires that same
identity again when it embeds the observer fact. It never scans for a latest
run, hands the observer raw market data, price, account, or order values, or
adds another scheduled task.

Observation is post-order evidence, not an order transition. At this narrow
boundary any ordinary observer exception becomes the safe
`observer_unavailable` result while the original canary status, reason, and
durable state remain intact. Process-control exceptions are not swallowed. A
successful observation adds only its existing categorical safe payload; its
current `pnl_status` remains `not_observed`. Missing, stale, ambiguous, or
unavailable evidence is therefore an execution-coverage gap with
`performance_label = None`, not a fill, loss, negative training label, retry,
or Paper authority condition.

Claude's isolated falsification-first verdict was `supported-with-limits`.
Its constraints were structural no-POST/no-live containment despite a
write-capable credential, exact identity pinning, no absence-to-fill inference,
and observer failure/replay isolation. Independent Data review confirmed that
the daily provenance contract needs only opaque receipt/run identity and that
`raw_market_data_retained: false` remains a no-bytes fact rather than a latch.
Independent Research review confirmed the full receipt digest as the only
model-side join key. Independent Validation initially found two P2 gaps;
the final code validates identity before observation and isolates an unexpected
ordinary observer failure. Focused tests cover mismatched receipt/run rejection
before the observer, persisted-state read-only routing, replay, redaction, and
no fabricated PnL.

Reason: this reuses the existing daily Paper schedule to produce timely,
truthful execution evidence without building a scheduler platform, a permission
marker, or a separate report workflow.

## 2026-07-22 - Qualify the KIS Paper terminal-field source without fabricating terminal facts

Decision: add a structurally read-only terminal-field probe for one existing
SPY/AMEX virtual Paper intent. It reads the persisted state from a read-only
volume without creating a lock file, binds the requested run ID to the internal
state, derives the KIS query date only from a durable acknowledged submission
time, completes the fixed `VTTS3035R` history pagination, and compares `odno`
and `orgn_odno` only in memory. Its external evidence keeps only an opaque run
reference, identity-match category, pagination completion, and documented
field-presence categories. It has no submit, modify, cancel, or live route.

KIS's official sample names `ft_ord_qty`, `ft_ccld_qty`, `nccs_qty`, fill
price/amount, `prcs_stat_name`, `rvse_cncl_dvsn`, and `ord_tmd`, but does not
qualify the terminal enum, original-order lineage resolution, row ordering, or
net-PnL/cost basis. An independent validation review found that intent creation
time could cross ET midnight before submission and that a valid state could be
misfiled under another run ID. The final contract therefore writes
`submitted_at` exactly once when a broker order ID is acknowledged, preserves
it through later transitions, and refuses a mismatched or legacy timestamp-free
state before configuration or network access. The existing cancelled canary
predates that field and now truthfully reports `submission_time_missing`.
The outcome remains `terminal_state_support: unqualified`,
`pnl_status: not_observed`, and `performance_label: None`; it is not a
cancellation inference, a negative label, a retry cue, or an
authorization/schedule hold.

Claude's falsification-first verdict was `supported-with-limits`: promotion
would require exact durable identity, fully completed order-date pagination,
official terminal semantics, amendment resolution, quantity consistency, and
official realized-PnL economics. Independent Data review confirmed the source
field/Mock-query constraints. Independent Research review confirmed that an
entry fill is not realized PnL and all incomplete facts retain a null
performance label. The follow-up Claude check was also `supported-with-limits`:
the acknowledged time must be write-once, exact run binding must be enforced,
and legacy state stays scoped unavailable to this probe only. Focused
fake-transport tests cover acknowledgement-time ET-date selection, write-once
preservation, run mismatch, pagination, ambiguity, route isolation, redaction,
external artifacts, and read-only state behavior.

Reason: this advances KIS-native execution evidence while keeping the current
source limitation truthful and without reviving a Paper permission latch.

## 2026-07-23 - Attach terminal-field evidence to the exact daily Paper receipt

Decision: after the daily SPY Paper session verifies that its canary run ID is
the receipt-derived `receipt-<digest>` value and completes the existing receipt
observer, invoke the existing read-only terminal-field probe for that same
durable state. Embed only the probe's categorical safe payload plus a SHA-256
content reference to its external artifact in the daily outcome. The probe's
result is post-order evidence: it cannot change the canary result, create an
order, modify/cancel/retry an order, add a scheduler, scan latest runs, or
affect another distinct Paper session.

The daily outcome validates the probe run hash against its own run ID. A
mismatched result or ordinary probe failure is contained as
`terminal_field_probe_unavailable`; the canary and receipt-observer facts are
preserved. A legacy state with no write-once acknowledged `submitted_at` still
records only `submission_time_missing` before configuration or network access.
The date used for a new query remains the acknowledged timestamp's ET date,
not the intent creation date.

Independent Data review confirmed the bounded `VTTS3035R` direct/lineage,
pagination, and field-presence contract. Independent Validation review drove
tests for receipt/run mismatch, legacy state, ET-midnight selection, replay,
exception isolation, virtual-only GET/token routing, and artifact redaction.
Independent Engine Research review confirmed no consumer path from this payload
to `performance_label`, candidate selection, ensemble inputs, Paper cadence,
or PnL attribution. The high-level Claude drift verdict was
`supported-with-limits`; no field-presence result is promoted beyond the
existing `terminal_state_support: unqualified` and
`pnl_status: not_observed` limits.

Reason: this captures the next useful KIS-native execution fact automatically
without turning source uncertainty, a completed one-shot marker, or a missing
timestamp into a Paper permission or research gate.

## 2026-07-23 - Align prospective intraday-head collection with a complete US session

Decision: move the existing `thericher-kis-paper-intraday-head` task from
02:35 KST to 06:20 KST and increase its unchanged `QQQ/NAS` and `SPY/AMS`
head collection from two to four minute pages per target. The prior run at
02:35 KST observed exactly 240 consecutive KIS minute rows from US 09:36 to
13:35, which cannot contain a complete 390-minute regular session. At 06:20
KST the summer post-close offset is 80 minutes; four 120-row pages cover 480
minutes, enough to span 80 post-close minutes plus the 390-minute session with
a small boundary margin. The run remains a bounded KIS Paper market-data call
only, with at most eight page requests, no new route, symbols, account access,
order operation, or retention location.

The next due run is the falsification check: its metadata-only prospective
inspection must find exactly one complete 390-minute QQQ regular session under
the existing explicit 2026 session calendar. A short, delayed, duplicate, or
otherwise incomplete result remains a source/schedule finding and is not
research evidence or an authority latch. The source loader continues to clip
to the explicit regular-session window; four pages improve coverage but do not
claim that extended-hours rows are strategy inputs.

Claude's focused falsification-first verdict was `supported-with-limits`.
It agreed that four pages are the minimum defensible post-close envelope and
flagged extended-hours clipping and the next exact-390-minute inspection as
the decisive kill test. The change does not add a scheduler or a new approval
process; it corrects the cadence of the already authorized task.

## 2026-07-23 - Treat all private non-live work as default action

Decision: reaffirm the operator's explicit standing authorization for every
private non-live action, including ordinary KIS Paper virtual trades,
modification, cancellation, retention on `D:`, and goal-owned schedules. No
past one-shot record, raw-retention value, account/result shape, report, or
model outcome may become a fixed permission state or a reason to request a
human release.

`raw_market_data_retained: false` remains precise evidence that the named
attempt has no raw bytes available for data consumption. It is not an active
control flag: it neither blocks a fresh collection nor suppresses a distinct
Paper intent, schedule, or ready lane. A request can still truthfully decline
its own execution for virtual-host isolation, secret safety, missing data for
that exact computation, durable-idempotency conflict, or reconciliation of
that exact unknown intent. Those are technical execution facts, not approval
gates, and must not be generalized into same-symbol, same-session, or global
stops. `KIS_LIVE_*`, a live route, real-money behavior, paid commitments,
unclear rights, and public exposure remain outside this authority.

Claude's 2026-07-23 falsification-first drift check was
`supported-with-limits`: a no-bytes fact must not make nonexistent bytes usable
as data, and exact-intent reconciliation must remain limited to retrying that
one unknown intent.

Reason: non-live process latches were consuming development time without
improving the engine loop. The project should execute eligible private work by
default and preserve only facts needed for truthful data handling and
recoverable virtual execution.

## 2026-07-23 - Keep a repeated invalid daily cursor from starving useful data

Decision: when one private daily-cache target records at least two consecutive
`daily_response_invalid` outcomes with zero rows at the exact unchanged cursor,
upgrade only that target to `source_limited` and exclude it from ordinary target
selection. QQQ/SPY or another ready target continues without an operator
decision, Paper-order hold, or global data stop.

The predicate is deliberately exact: it requires the same cursor, zero rows,
the same strict-parser reason, no retained raw bytes, and no cursor progress.
A partial result, changed cursor, different reason, or usable data never
qualifies. A later official endpoint, changed source scope, or separately
evidence-backed parser contract can establish a new target; this status does
not convert missing rows into data or become a permanent product restriction.

Claude's falsification-first verdict was `supported-with-limits`: the
implementation must prove both that the invalid target no longer starves the
worker and that a ready QQQ/SPY target remains collectible.

Reason: the IWM cursor at 2023-10-10 repeated the same zero-row strict-parser
failure four times. Continuing to call it consumed KIS capacity without
improving data coverage, while excluding only that broken source cursor lets
the active engine loop progress.

## 2026-07-23 - Schedule bounded daily historical backfill

Decision: install one `thericher-kis-paper-daily-backfill` Windows task for
Tuesday through Saturday at 07:00 KST. It invokes the new
`kis-paper-daily-backfill` Docker profile, which runs the existing cache worker
with one KIS Paper token and at most two daily pages. It runs after the 06:20
intraday-head task and before the 08:10 local operating review.

The service mounts only `D:\market_data` at `/app/market_data`, receives only
`KIS_PAPER_APP_KEY` and `KIS_PAPER_APP_SECRET`, and uses `THERICHER_MODE=off`.
It has no account, position, order, live, dashboard, or artifact mount. The
existing root lock, source-specific `source_limited` status, and 15% free-space
floor bound its data effect. It is an owned recurring Data job, not a new
approval mechanism or a general scheduler platform.

Claude's focused scheduler drift-check was `supported-with-limits`: retain the
one-token/two-page limit, verify the single data mount is read/write scoped to
that path, and re-review any future account/order route or second token.

Reason: QQQ/SPY daily coverage can now advance automatically without repeated
IWM failures consuming the worker. The schedule improves collection cadence
while remaining independent of Paper orders and model promotion.

## 2026-07-23 - Support injected Paper market-data configuration in Docker

Decision: the shared KIS Paper market-data loader accepts a complete explicit
environment pair of `KIS_PAPER_APP_KEY` and `KIS_PAPER_APP_SECRET` for the
data-only Docker profiles. It reads only those two names plus
`THERICHER_MODE`, rejects a partial pair or a live mode without a dotenv
fallback, and never reads account or `KIS_LIVE_*` names. If neither Paper app
value is injected, the existing strict local `.env` parser remains the host
fallback.

The first end-to-end Docker backfill verified this path by collecting one
199-row `SPY/AMS` daily chunk under `D:\market_data`; it had no account/order
route, live route, or `.env` mount. The worker emitted only a sanitized
manifest identity, row count, target, and status.

Claude's short drift-check was `supported-with-limits`. The implemented limits
are complete-pair-only configuration, no environment/dotenv value mixing, a
live-mode rejection, and tests proving no live credential name is read.

Reason: Docker Compose already injects exactly the two authorized Paper
market-data values while the container image deliberately excludes `.env`.
Using the explicit pair fixes a runtime portability defect without widening
broker authority or changing the Paper-only client route.

## 2026-07-23 - Keep non-live authority free of renamed approval latches

Decision: reaffirm that a status, safety score, report, model metric, recovery
note, historical marker, or unavailable input cannot be repurposed into a
human-release requirement for private non-live work. This includes ordinary
KIS Paper virtual trades, reads, modify/cancel, data retention, research work,
and goal-owned schedules. A factual condition may reject only the computation
whose required bytes are absent or the exact unknown durable intent that must
be reconciled; it cannot suppress a distinct correctly scoped action.

The only authority boundaries remain `KIS_LIVE_*`, live routing or real-money
behavior, paid commitments, unclear rights, and public exposure. Technical
truth remains mandatory: virtual-host pinning, secret redaction, immutable
intent-before-side-effect, and exact-intent reconciliation. These are not
operator approval steps.

Claude's falsification-first verdict was `supported-with-limits`: scope every
historical marker to its named evidence, never treat missing bytes as usable
data, and never bypass reconciliation for the exact unknown intent.

Reason: renaming a historical condition as a status or report would recreate
the same process obstruction the operator has explicitly removed, without
improving data quality, Paper learning, or recovery truth.

## 2026-07-23 - Use the KIS response header for minute pagination

Decision: use the official KIS overseas-minute response header `tr_cont` as
the sole continuation authority. `M` or `F` produces the fixed next request
value `NEXT=1`; every other header state completes the bounded page sequence.
The collector continues to derive `KEYB` from the oldest validated exchange
timestamp. `output1.next` and `more` remain recorded provider metadata and do
not control cursor advancement.

Reason: the prior body-`next == "1"` interpretation turned a terminal
historical page into `minute_cursor_invalid` despite valid rows. Fake transport
tests now prove header/body disagreement, both documented continuation states,
and the unchanged Paper-only request contract. A data-only Docker re-run then
committed 100 QQQ/NAS and 69 SPY/AMS rows under `D:\market_data` and cleared
both historical cursors without an account, order, or live call.

The source reference is the official `koreainvestment/open-trading-api` sample
at revision `885dd4e2f5c37e4f7e23dd63c15555a9967bc7bc`,
`examples_llm/overseas_stock/inquire_time_itemchartprice`. Claude CLI
drift-check requests timed out without a verdict, so this decision relies only
on the official source, isolated fake tests, and the bounded Paper-data result.

## 2026-07-24 - Classify the first post-close intraday-head result as short coverage

Decision: retain the first 06:20 KST post-close head result as a source-coverage
finding, not as an input qualification, Paper permission, or Research result.
The authorized data-only task completed successfully and added one terminal 120-row
minute chunk per QQQ/NAS and SPY/AMS to its independent cache, but the
metadata-only prospective preparer found zero exact 390-minute QQQ regular
sessions. It therefore wrote no research artifact and made no model, GPU,
broker, account, or order call.

Reason: the actual KIS source result falsifies the prior operational assumption
that four configured pages would necessarily yield a full post-close regular
session. The next bounded Data objective is to inspect the official request /
continuation contract and deterministic tests before changing page count,
anchors, or schedule behavior. A short source slice limits only the exact
prospective input claim; it cannot halt another authorized Paper, data, or
research lane.

## 2026-07-24 - Sample prospective head windows during the source session

Decision: retain the existing `thericher-kis-paper-intraday-head` task and
Docker profile, preserve its four-page-per-target cap, and give that one task
three Tuesday-through-Saturday KST triggers: 02:35, 04:35, and 06:20. The task
remains data-only and keeps its independent head cache, exact-overlap handling,
and D: retention contract. It adds no account, order, live, dashboard, or new
task/service route.

Reason: the terminal 06:20 result showed that post-close page count cannot
manufacture server continuation. Safe metadata from the prior 02:35 KST run
shows two full 120-row pages spanning 09:36 through 13:35 with continuation
still available after the second page. Earlier in-session samples can therefore
ask the server for the opening range through its documented continuation path,
while later samples cover the session tail. The Data selector remains the
decisive kill test: only an exact 390-minute declared QQQ session becomes a
future candidate input; any incomplete union stays source evidence.

Claude's focused follow-up verdict was `supported-with-limits`. Its reversal
condition is an incomplete or gapped union being accepted as complete. Existing
metadata-selection tests reject that shape, and the first three-trigger session
will reattest it against the actual source.

## 2026-07-24 - Use finite rate-safe KIS Paper market-data catch-up

Decision: treat the current KIS Paper market-data constraint as a shared
request-rate concern, not an assumed daily quota. All Paper market-data
workers now share an external 1.25-second request-start gate and record a
60-second cooldown after HTTP `429` or KIS `EGW00201`. The 07:00 KST daily
worker uses one Paper client to drain at most 48 ready daily chunks or six
hours, then stops with a categorical result. It retains the existing IWM
source-limit behavior and never reads account, order, or live credentials.

The historical QQQ/SPY minute cursor is hydrated as `source_exhausted` after a
verified terminal page rather than downloading that terminal range repeatedly.
The independent intraday-head cache remains the only scheduled fresh-minute
path.

Reason: official KIS materials establish a per-second request constraint, but
no verified daily total was found. A finite shared gate reaches ready history
quickly without a parallel request flood, duplicate token issuance, or an
unbounded daemon. The gate persists timing facts only under `D:`, never raw
responses, credentials, account facts, or a permission state.

Claude's falsification-first verdict was `supported-with-limits`: do not call
this high-throughput, keep the run finite, prevent a long worker from starving
fresh-head collection, and preserve the source/terms boundary. The daily
worker's hard time/chunk bounds and shared request gate satisfy those limits.

## 2026-07-24 - Keep cross-lane throughput in a Codex-owned stateboard

Decision: add `agents/orchestration.md` as a concise Codex-owned cross-lane
projection. It may hold only resource conflicts, external waits, the current
bottleneck, and one current reversible operating improvement. Data, Engine
Research, and Execution remain the only durable role lanes; this file is not a
Role Agent, second objective, implementation queue, approval mechanism, or
history ledger.

An external quota, retry time, or timer wait belongs to its named worker or
existing scheduler. Codex records the next due fact and advances independent
ready work instead of holding the foreground orchestrator in a long sleep.
This improves data collection and research/execution throughput without
changing broker authority, strategy authority, or live-risk controls.

Claude's falsification-first verdict was `supported-with-limits`: do not copy
lane queues or historical evidence, replace the current bottleneck/improvement
rather than appending a log, and make the no-foreground-wait behavior real in
orchestration rather than treating the file as a report.

Reason: provider quotas and scheduled collection are normal parts of the data
loop, but they must not idle the entire development team when independent Data,
Research, or Execution work is ready.

## 2026-07-24 - Treat immediate KIS Paper token reissue failure as inconclusive

Decision: a data-only `token_issued` result followed immediately by an
`auth_rejected` result from a separate short-lived worker is not evidence that
the Paper App Key/App Secret must be replaced. KIS documents a one-day token
lifetime and at-most-once-per-minute reissuance, while the sanitized category
does not distinguish rate limiting from credential rejection. The Data path
will use one in-memory client per finite run and a shared non-secret
five-minute token-request-start spacing guard; bearer tokens remain memory-only.

Only a spaced single-client issuance failure, or a valid token refused by the
allowlisted market-data endpoint, reopens the local credential/provider
hypothesis. This changes no account, order, live, or capital authority.

Claude's falsification-first verdict was `supported-with-limits`: the separate
process assumption and token-versus-data endpoint must remain visible, the
spacing timestamp must be genuinely shared, and a sanitized failure cannot be
overinterpreted before the kill test.

Reason: the immediate two-process sequence likely collided with KIS token
reissuance handling. Reusing a valid token and spacing restart issuance avoids
unnecessary token calls while preserving secret isolation and fast data pages.

## 2026-07-24 - Calibrate throughput with bounded probes

Decision: for a genuinely unknown private non-live provider, runtime,
data-capability, or throughput behavior, use a finite scoped capability probe
before adding an approval hold or a new durable throttle. A persistent sleep,
rate cap, retry cap, or scheduler throttle must have official-source or
measured evidence and name the fact that will retain, recalibrate, or remove
it. An external wait remains the owning worker's `next_due`; its failure is
scoped evidence and cannot pause another ready lane.

Existing documented or evidence-backed controls remain in force until their
named source or measurement changes. This decision does not permit unbounded
retry, a parallel flood, removal of established recovery controls after one
inconclusive run, a new role/report/gate, or any broker/live authority change.
At each company-goal boundary, Codex identifies the most material cross-lane
bottleneck or idle resource and retains or makes one reversible,
evidence-backed improvement when it advances an engine loop.

Claude's falsification-first verdict was `supported-with-limits`: preserve
official or measured controls such as the current request gate, rate-limit
cooldown, token-start spacing, and scoped source-quality stop until their
specific calibration fact changes. The rule applies only to a genuinely
unknown capability and must not become a brute-force retry justification.

Reason: a scoped probe yields faster, recoverable evidence without inventing a
human approval wait or leaving the foreground orchestrator idle. It improves
data collection and research/execution throughput while keeping rate, data
correctness, recovery, and live-authority boundaries intact.

## 2026-07-25 - Keep unadjusted QQQ/SPY daily history out of return labels pending event qualification

Decision: the completed KIS Paper QQQ/SPY-only D1 cache is valid collection
evidence but is not yet a return-labelled Research input. Its 4,756 common
sessions (2007-08-21 through 2026-07-17) remain explicitly
`MODP=0_unadjusted` with unqualified corporate-action semantics. Do not run a
daily return baseline, model, GPU candidate, ensemble, promotion, or Paper
decision from that source until a separate, source-attested dividend/split event
contract defines comparable feature/target pairs and preserves point-in-time
availability. The existing 694-session three-ETF work remains frozen and is not
retuned.

This is a source-contract limitation, not an operator approval, Paper, data
collection, schedule, or global Research halt. Data may use the already
authorized no-cost Tiingo standard-EOD access to build a bounded external
event-only sidecar and either qualify a masked contract or record an
unqualified result. The operator's existing `TIINGO_API_TOKEN` authorization
for private `QQQ`/`SPY` standard-EOD work applies to that bounded sidecar only;
the token itself remains local and unreported.

Reason: Claude's falsification-first verdict was `unsupported` as framed.
Raw unadjusted close-to-close labels can be mechanically distorted on dividend
or split event dates, and the current KIS cache alone cannot identify those
dates. The verdict's reversal fact is a source-attested event mapping plus
chronological availability/target timing validation; until then, a disclaimer
would not make the labels comparable.

## 2026-07-25 - Qualify only a price-free QQQ/SPY event-sidecar, not a return strategy

Decision: accept the immutable external Tiingo Standard EOD event-only sidecar
for the completed KIS Paper QQQ/SPY daily panel. The sidecar covers the exact
4,756 common KIS sessions from 2007-08-21 through 2026-07-17, records 78 QQQ
and 76 SPY dividend/split events, and binds the source to the KIS panel through
the catalog hash
`sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`.
Its snapshot dataset hash is
`sha256:9a3e3b22c4a6045c4f26e6e77439cb3322cb61f8f6c04b422bb31412631d0de3`,
with manifest hash
`sha256:c6f4b7113507d27577fb7ee66328db53d274e08d2470d3854b6f4e9aa46d171d`.
It retains only normalized event dates/kinds/values plus coverage and response
hash metadata; it retains no Tiingo price rows or raw response bytes.

This qualifies deterministic event-date mapping for retrospective plumbing,
not KIS adjustment semantics, total-return research, point-in-time feature
availability, alpha, model training, GPU work, ensemble selection, or Paper
decisions. The paired Research receipt currently excludes `t -> t+1` when
either endpoint is an event date, but it remains explicitly non-model and
non-Paper eligible.

Claude's follow-up falsification-first verdict was `supported-with-limits` for
a later naive price-return baseline. Before that baseline, freeze or reject a
separate buffered `+-1`-session event-boundary contract, inspect all event
neighborhoods against the retained KIS series using a pre-registered residual
test, and bind every comparator to the same pair set and split boundaries. A
result from that audit remains a scoped data/research fact, never an operator
approval, KIS Paper, scheduling, or global-engine hold.

Reason: exact Tiingo session coverage and event mapping resolve the original
unknown event-date input, but a provider-declared unadjusted KIS mode and a
single source cannot by themselves rule out a date shift, partial adjustment,
or missing/revised event. A conservative local audit is low-cost and supplies
the reversal fact without mixing providers, exposing prices, or delaying
independent Paper work.

## 2026-07-25 - Qualify a buffered QQQ/SPY daily price-return boundary audit

Decision: accept one immutable external, retrospective event-boundary audit for
the exact 4,756-session `QQQ/SPY` KIS D1 panel. Its artifact is
`D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-event-boundary-audit.json`,
with content hash
`sha256:3d97b26b5e8e422cb2b4bcf262fbd1be887e44d7e43afdd9e2b5d689f805a46c`.
It re-attests the KIS catalog hash
`sha256:78b00556ddbc8bcfb0c4d1bb67e004e4a4c4ff035a8c348b2516b842fa397718`
and the qualified Tiingo event-only sidecar hashes. It freezes mask identity
`sha256:921c61b8abf822b0aee71b66b43c37875cb581e95bf7a1563b053880c087d429`
and partition identity
`sha256:b82ed4022237929febde187651cb31e74740b311faa85c850967c617ac8dcfdb`.

The audit excludes every `t -> t+1` pair whose endpoint is an event session or
either adjacent KIS session, and fixes development/purge/validation/embargo/tail
regions at 2,853/1/951/1/950 sessions. It masks 316 QQQ and 307 SPY pairs and
finds zero remaining absolute close-to-close residuals at the fixed 20%
threshold. It retains categorical counts and dates only; no raw price or return
is persisted. This permits exactly one later fixed CPU-only, descriptive naive
price-return comparison that re-attests the full artifact, uses the exact mask
and partitions, and leaves the untouched tail unopened. It does not permit a
model, GPU work, tuning, ensemble, total-return or point-in-time claim, PnL
claim, KIS Paper decision, or live behavior.

Claude's follow-up falsification verdict is `supported-with-limits`: the audit
cannot prove small distributions, special corporate actions, event completeness,
or KIS/Tiingo timestamp equivalence; its whole-panel residual audit is mild
historical snooping; and calendar masking may lift observed average price return.
Those limitations are permanent scope labels for the next baseline, not a new
operator gate or a hold on independent Data, Research, or Paper work.

Reason: the bounded audit supplies a reproducible, conservative price-return
comparison surface without pretending that unadjusted history becomes an
executable, total-return, or point-in-time source. A fixed naive baseline can
now test the plumbing while preserving a genuinely unused tail and avoiding
model-search selection bias.

## 2026-07-25 - Keep the masked QQQ/SPY D1 naive run as local-paper plumbing only

Decision: record the first completed fixed D1 control artifact at
`D:\thericher-v2\model-artifacts\kis-daily-masked-naive-validation\kis-daily-masked-naive-validation-v1.json`,
with content hash
`sha256:e2ad842d852fe647f7de6367955f7a48f27f08508e32816f98f3c473ffcffbf6`.
The run re-attested the immutable full KIS source, audit, event-sidecar lineage,
mask, and partitions before constructing only the 3,806-session prefix through
the embargo. It ran only `flat`, `always_long`, and
`previous_session_direction`, with identical audited eligibility per
symbol/phase. All 21,294 fills were `source: local_paper`, replay-checked, and
deleted with their temporary event logs; the external artifact is aggregate and
contains no raw price, per-bar return, or broker value.

Do not treat any control cell as alpha, profitability, a model hypothesis,
total-return evidence, point-in-time evidence, KIS Paper input, or a reason to
open the untouched tail. Claude independently returned `supported-with-limits`:
the one SPY validation cell where prior direction exceeded always-long reverses
sign in SPY development and is dominated in the other three cells. It is
multiple-comparison noise until independently sourced, adjusted,
point-in-time, multi-period evidence reverses that conclusion.

Reason: the run proves the constrained offline-to-local-paper path and its
recovery/privacy behavior, not a tradable effect. Restricting the conclusion
keeps future engine work focused on new prospective or properly qualified data
instead of turning an unadjusted retrospective control into model search.

## 2026-07-25 - Retain the static Norgate panel as a sanitized development-only receipt

Decision: accept one deterministic external qualification receipt for the
already retained static Norgate trial panel at
`D:\thericher-v2\model-artifacts\norgate-development-qualification\r1-3d0841b90ddfd8d8\qualification.json`,
with content hash
`sha256:1f5ddec5cd1bc94fddbfde9de22e6480480f3daa28e0a03913a0d8d5d299a9d4`.
It re-attests the pinned panel data hash
`sha256:3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`
and manifest hash
`sha256:a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
The receipt stores only source identity hashes, aggregate geometry, scope,
limitations, reversal facts, and one declarative daily interface: 20
close-to-close returns sourced through `t`, a decision at the completed `t`
close, and a next-open/following-open outcome timing. It stores no OHLCV rows,
symbols, dates, feature values, labels, prices, PnL, broker facts, credentials,
or network output.

The source remains static-survivorship/availability selected with unverified
adjustment semantics, a trial retention obligation, and no point-in-time or
publication-time proof. Its receipt is `qualified_for_development_only` and
keeps model, GPU, campaign, ranking, sealed-holdout, Paper, PnL, and live scope
false. An unqualified source receives no usable feature timing contract; a
source hash, scope, future-boundary, raw-field, or receipt-schema change rejects
reuse. Do not use the existing legacy raw-derived Norgate artifact as a bypass.

Claude's falsification-first verdict was `supported-with-limits`: the strongest
kill test is a sanctioned consumer path that lets this source or receipt reach a
prohibited model/GPU/Paper/live/PnL route. The current helper has no such route,
but its static-universe limitation remains permanent and it cannot support a
naive-baseline or profitability claim. A separately eligible prospective KIS
contract, not a widened Norgate interpretation, is the reversal path for future
model work.

Reason: the receipt resolves a concrete cross-lane ambiguity without duplicating
the loader, preserving raw data, creating a model queue, or adding a Paper gate.
It gives development preparation an explicit causal vocabulary while making
misuse mechanically rejectable and keeping the next engine loop focused on
KIS-compatible prospective evidence.

## 2026-07-25 - Retain bounded ambiguity for absent KIS Paper exact intents

Decision: keep the existing daily-session, receipt-observer, and terminal-field
probe behavior rather than adding stale-order automation. A synthetic,
acknowledged durable intent that is absent from both current open orders and the
same-day order-ID lookup produces only `outcome_unknown`, `exact_absent`,
`same_day_id_absent`, `ambiguous`, and `terminal_state_not_supported`, with
`pnl_status: not_observed`. The observer leaves the durable state unchanged and
uses no submit, modify, cancel, or retry route.

Claude's falsification-first verdict was `supported-with-limits`: this result is
safe only as a scoped uncertainty outcome. The current `VTTS3035R` source still
does not qualify terminal enum, amendment ordering, completed-history, or
net-PnL semantics. Revisit automation only if those source semantics become
qualified and an exact-identity fixture demonstrates a concrete missing
invariant.

Reason: a timer or absence-based transition would add machinery without new
truth and could fabricate lifecycle or PnL facts. The existing exact-identity
path advances execution evidence while preserving independent Paper work.

## 2026-07-25 - Couple completed intraday-head collection to one isolated readiness preparation

Decision: reuse the existing `thericher-kis-paper-intraday-head` Windows task
and Docker service for one sequential, metadata-only preparation attempt after
its exact QQQ target result is `collected` or `recovered`. A scoped SPY target
failure still makes the overall collection result `incomplete`, but cannot delay
the QQQ-only preparation input; the preparer validates the complete index shape
before selecting QQQ. Do not add a second Windows task, polling loop, or queue.
The preparer runs with the deterministic `scheduled-head-v1` label, only
`PYTHONPATH` plus necessary process bootstrap variables, and a ten-second
containment timeout. Its categorical `pending`, `prepared`, or scoped
unavailable result is additive output only: it cannot revise a completed
collector result, cache cursor, or freshness projection.

When five complete QQQ regular sessions become available, the existing first-
five contract writes an external precommit/planning-receipt pair once. Replays
validate the pair rather than using current index metadata or preparation time
as identity: the immutable binding is the contract hash, first-five dates, and
the selected rows' fingerprint digest. A malformed, changed, escaped, or
concurrently published pair fails closed or reuses a verified winner without
overwriting evidence. No raw bars, credentials, model checkpoint, GPU work,
order, or PnL result crosses this handoff.

Claude's falsification-first verdict was `supported-with-limits`. The relevant
kill case is a slow, failing, or malformed child after a successful collection;
tests show that the collection remains complete and its freshness output stays
authoritative. The remaining limit is operational: real first-five coverage
still depends on future KIS head sessions, so this decision proves the handoff
and recovery behavior, not source completeness or model readiness.

Reason: this removes a manual research-preparation gap at the exact boundary
where the data is known durable, while preserving the one existing collector,
isolating credentials, and avoiding a new scheduler or approval surface.

## 2026-07-26 - Dispatch a prepared prospective pair through an isolated CPU observer

Decision: retain one `thericher-kis-paper-intraday-head` Windows task and one
`kis-paper-intraday-head` Docker profile, but let that profile contain a
second, sequential service solely for the existing offline observation. The
host dispatcher runs the credential-bearing collector once and then invokes
`kis-paper-intraday-observation` regardless of the collector exit code. The
observer is `network_mode: none`, read-only except for the external artifact
mount, has no KIS environment values or GPU request, and uses the existing
pair-verifying consumer. Before a pair exists it is a no-op pending check;
afterward it is the bounded local-paper observation only.

The dispatcher returns the collector's exit code, not the observer's. A QQQ
pair may therefore reach the observer even when the independent SPY result
makes the Data result incomplete, while observer failure cannot rewrite Data
freshness, cache state, or scheduler recovery. `IgnoreNew` still serializes
the single named task; the consumer's immutable receipt/replay checks remain
the boundary against duplicate or changed evidence.

Claude CLI was asked for the required falsification-first drift check, but its
OAuth session was expired. Data and Engine Research advised against executing
the observer inside the KIS container; Execution identified the isolation,
independent-exit, and cadence invariants implemented here. The next due run is
the operational proof, not a new authority gate.

Reason: this removes the foreground wait between a valid Data pair and its
first repeatable local-paper observation without widening broker authority,
creating a second scheduler, or borrowing the GPU for a CPU-sized check.

## 2026-07-25 - Seal the first pair-bound prospective offline observation

Decision: the first `kis-intraday-prospective-head-observation-r1` consumer is
an offline-only boundary. It accepts only a Data-loader-created input after the
external precommit/planning pair's frozen first-five QQQ dates and selected-row
fingerprint digest match both before and after the separate local cache reads.
The full head-index metadata hash is preparation-time provenance, not a mutable
input lock: append-only coverage or independent SPY metadata updates remain
eligible, while a selected-row change fails closed. The sealed input binds the
selected rows and pair; the frozen model receipt retains that provenance.

The consumer fits the regularized-linear control only on the fixed ten-session
historical prefix, runs `flat`, `always_long`, `previous_bar_direction`, and
that control through the local-paper simulator in memory, and persists only
sanitized decision/fill evidence. Receipts bind the verified input, frozen
model, exact replay plan, and sanitized event-log hashes. They exclude
raw bars, prices, order identifiers, source paths, PnL, selection, promotion,
broker submission, network, credentials, and GPU artifacts. A known-safe
partial candidate artifact may restart; a completed but changed receipt fails
without overwrite or silent replacement.

The host and network-disabled research-container smoke both returned
`preparation_pair_missing`, so no real consumer receipt exists yet. Claude CLI
could not provide a fresh verdict because its local OAuth session had expired.
This is a tooling limitation, not an authority or data gate: retry the required
falsification check before relying on a material result, promotion, holdout, or
execution decision.

Reason: a small sealed handoff makes the first fresh KIS-compatible observation
reproducible without turning raw data, retrospective model outputs, or local
paper mechanics into a broker or model-selection path.

## 2026-07-25 - Add an early prospective-head coverage window

Decision: keep the one existing `thericher-kis-paper-intraday-head` task,
Docker profile, four-page-per-target cap, strict duplicate-conflict rule, and
390-minute selector. Add only its 00:35 KST trigger, alongside 02:35, 04:35,
and 06:20, so the same data-only worker can sample the previously absent early
US-session range. No account, order, live, model, or new scheduler route is
introduced.

A metadata-only index inventory found zero complete QQQ sessions out of five.
The current candidate dates had 240, 39, and 240 of 390 required minutes; no
duplicate retained timestamp, conflicting retained fingerprint, or later
same-fingerprint completion could explain the gap. A later rejected source
attempt recorded `minute_duplicate_conflict`, which remains scoped evidence for
that snapshot rather than a cache or schedule hold.

Reason: source metadata falsifies a selector relaxation or completion-promotion
change as the current recovery. The missing early window is the smallest
reversible coverage change; the next scheduled result, not the new schedule
itself, will determine whether collection coverage improves.

## 2026-07-25 - Fail closed on prospective evidence that cannot be replayed exactly

Decision: a minute duplicate discovered inside one candidate batch rejects the
entire candidate, including any earlier accepted page from that invocation. It
writes no retained snapshot and does not advance the cursor. Explicitly marked
legacy `candidate_batch` conflict chunks remain immutable audit evidence, but
the metadata selectors and offline loader exclude them from session completion
and feature inputs. The outer collector reports `complete` only when it returns
exactly one successful outcome for both expected QQQ and SPY targets; a scoped
QQQ recovery may still drive the existing QQQ-only preparation child while the
outer result remains `incomplete`.

The prospective local-paper receipt recovery now accepts only canonical current
schema event envelopes, contiguous sequence numbers, and the frozen plan's
chronological decision stream. Each buy decision must carry exactly its planned
local-paper buy and sell fills at the planned timestamps, instrument, and one
share quantity; non-buy decisions carry no fill. Extra, malformed, or
unplanned events fail the receipt reconstruction. A missing Paper receipt state
is `unavailable`, not proof of `not_submitted`, and the terminal-field probe
checks run, client-order, and decision identity before any history read.

Reason: these are narrow provenance and recovery properties. They prevent an
invalid cached prefix, malformed replay, or mismatched private state from
becoming a false data, execution, or PnL claim without adding a scheduler,
approval step, broker side effect, or model-selection path.

## 2026-07-25 - Quarantine invalid legacy intraday candidates from active recovery

Decision: an explicitly marked legacy `candidate_batch` conflict is invalid
collection input. Preserve its immutable snapshot artifact, but remove the
chunk from the active intraday index, derive a backfill continuation only from
remaining valid chunks, preserve a head collector's stored cursor, and exclude
it from collision, duplicate, source-exhaustion, snapshot attestation, and
orphan-recovery logic. If orphan reconciliation succeeds for one target, emit
one aggregate recovered result for that target and continue the other target in
the same bounded cycle.

The kill cases are a legacy invalid chunk blocking a new conflicting row, being
mistaken for an already cached exact row, or a QQQ/SPY recovery suppressing the
independent target's collection. Synthetic tests cover all three. Claude CLI
was asked for the required short recovery drift-check but its OAuth session was
expired; this tooling failure does not hold independent private work.

Reason: invalid evidence must never become an operational latch, but deleting
the artifact would erase provenance. This keeps recovery narrow, preserves
evidence, and maintains the one existing scheduler, data boundary, and Paper
authority separation.

## 2026-07-25 - Bound named scheduler recovery without late Paper catch-up

Decision: retain the existing five named Windows tasks, profiles, services,
and triggers, but register explicit task settings. All tasks allow battery
start/continuation, use `IgnoreNew`, and have an execution limit. Data-only
daily-head, intraday-head, and daily-backfill tasks use `StartWhenAvailable`;
the Paper quote and daily-session tasks do not, so a late availability event
cannot create an off-cadence Paper session. The normal head/session limit is
90 minutes, below the intraday head's shortest 105-minute gap. Daily backfill
has 390 minutes around its declared six-hour inner runtime.

The kill cases are a sleep/battery transition silently dropping a prospective
data window, a stalled Docker process suppressing later head triggers, or a
late catch-up creating a Paper execution outside its intended cadence. Static
tests pin every task's recovery and limit assignment; the installed definitions
were re-read after registration. Claude CLI was asked for the short scheduler
drift-check but its OAuth session was expired, which is tooling evidence only.

Reason: this makes data collection recoverable and cadence-bounded without
adding a scheduler, widening a broker route, changing Paper intent semantics,
or creating an operator gate.

## 2026-07-26 - Localize prospective readiness and restore parallel throughput

Decision: a prospective-data requirement now names only the exact
pair-dependent consumer, campaign, or promotion it governs. The existing
first-five QQQ 1m condition remains required for its isolated prospective
observation, but it cannot make historical KIS Research, Data capability
measurement, local simulation, or deterministic Paper preparation
input-pending. Company goals must include all ready, non-conflicting,
role-owned work packages rather than waiting on the next external due time.

The immediate company objective has three parallel packages: a finite KIS
Paper market-data capability probe and adaptive-capture design; a frozen
historical KIS Research campaign with CPU baseline and at most one bounded GPU
replication/comparison; and an Execution contract simplification that preserves
local_paper, kis_paper, and kis_live route isolation. The probe is not an
unbounded request flood, and no package changes live authority, opens a sealed
holdout, selects a model, or creates a Paper order merely to manufacture
activity.

Evidence: the prospective head currently has zero complete QQQ sessions out of
five, while source-separated KIS history already includes a QQQ/SPY daily
common intersection and bounded complete intraday sessions. The former is a
local source limitation, not evidence that every engine loop lacks input.
KIS documents per-second request constraints and the project has an EGW00201
fact, so throughput remains an empirical Data concern rather than a presumed
daily-unlimited permission.

Claude CLI was invoked for the required governance drift-check, but its OAuth
session was expired. No credentials, raw data, or holdout material was sent.
The failure is recorded only as a scoped tool limitation; it does not hold
ready private work. Retry the falsification-first check before relying on a
material scheduler widening, model promotion, ensemble selection, sealed
holdout interpretation, or execution-risk change.

Reason: the prior objective turned one future source condition into a company
bottleneck and caused scheduler/recovery reattestation to displace Data,
Research, and Execution progress. Localizing the condition restores the
approved readiness-driven operating model while retaining source correctness,
rate, recovery, and live-route safeguards.

## 2026-07-26 - Build KIS intraday capture from measured terminal-head behavior

Decision: the next Data objective is one owned, bounded KIS Paper intraday
session-capture worker. It creates one in-memory market-data client/token for
one worker invocation, keeps concurrency at one, preserves the existing shared
request gate and cooldown, and treats `tr_cont` as the sole continuation
authority. A terminal page may contribute only current-head evidence; it may
not synthesize a historical cursor or support a historical-range claim. The
worker must retain provider rows, manifests, provenance, deduplication, and
recovery state only under `D:\market_data`, then report source-safe coverage
facts including the exact 390-minute regular-session contract. It has no
account, position, order, or live route and does not require a new scheduler.

Evidence: the bounded QQQ Paper-minute probe accepted two full terminal-head
pages under the current gate, reused one in-memory Paper token, and observed a
gap within one exchange date. Its source-safe artifact is
`20260726T123512436025Z-f1575006a7319021.json` beneath the external model
artifact root; the probe retained no raw bars. This establishes client-lifetime
token reuse only. It does not establish continuous-session capture, historical
pagination, a provider request ceiling above the current gate, or a reason to
loosen the existing pacing controls.

The frozen QQQ KIS-private-daily CPU baseline and fixed 20-session CUDA
architecture replication are recorded as descriptive local-paper evidence.
They selected no model, ensemble, or Paper action and do not change this Data
decision. A fresh Claude falsification-first capture check was attempted, but
the local CLI OAuth session was expired; no private material was sent. This
tooling limitation does not hold the Data-only worker, but Claude must be
retried before a material scheduler widening, promotion, ensemble selection,
holdout interpretation, or execution-risk change.

Reason: the smallest useful next step is to turn an observed route behavior
into a recoverable source-correct collector. Further blind model sweeps cannot
resolve the missing continuous-session evidence and would not advance a model
promotion claim.

## 2026-07-26 - Scope KIS intraday capture evidence to its own QQQ manifests

Decision: implement `session-capture` as a thin, Data-owned projection over
the existing private intraday collector. One invocation retains the existing
one-client/token, lock, request gate, cooldown, strict conflict handling, and
`tr_cont` behavior; the new projection makes no KIS call. It writes only an
allowlisted receipt under the external head cache and inspects coverage using
only QQQ manifest hashes produced or recovered by that invocation. An empty
manifest scope intentionally selects no legacy rows, so a prior complete chunk
cannot make a fresh partial capture appear complete. QQQ is the capture
target; SPY remains visible companion evidence without changing QQQ's scoped
transport outcome.

The bounded Paper Data-only smoke wrote a source-safe receipt below
`D:\market_data` and found zero of 390 qualified regular-session minutes in its
terminal capture. The source page was extended-session evidence, so it remains
excluded from feature, label, promotion, ensemble, GPU, Paper-order, and PnL
claims. No account, position, order, cancel, modify, live, scheduler, or model
route ran or changed.

Claude's required capture drift-check was retried before this implementation,
but its local OAuth session remained expired; no credentials, account data, raw
provider data, or holdout material was sent. This is a scoped review-tool
limitation, not a hold on the completed private Data work. Retry before the
next material scheduler/profile integration.

Reason: a transport-success label without capture-scoped coverage could let
legacy data or extended-session rows masquerade as a new regular-session
input. This keeps provenance exact while retaining the smallest reusable
collector path.

## 2026-07-26 - Integrate measured capture mode with the existing intraday task

Decision: update only the existing `kis-paper-intraday-head` Docker service to
run `--mode session-capture`. Its named Windows task, four triggers, execution
limit, `IgnoreNew` behavior, page cap, one-client collector, lock, transport
gates, strict conflict rule, and `tr_cont` continuation contract are unchanged.
No task, scheduler, account, position, order, cancel, modify, live, model, or
new observer route is created.

The command now applies the pre-existing QQQ-only metadata preparation handoff
to eligible `head` and `session-capture` results. The capture receipt remains
Data evidence; preparation stays isolated from KIS credentials, and the
network-disabled observer remains a second sequential service. A successful
QQQ result may prepare even if independent SPY collection makes the collector
cycle incomplete, but the collector's full target result remains the sole
process exit and freshness authority. A preparation fault cannot change a
successful collector exit.

Focused tests pin the exact Compose mode, unchanged task surface, one-client
capture semantics, QQQ/SPY partial behavior, fatal-path no-preparation rule,
and observer/route isolation. Claude's required profile drift-check was
attempted, but OAuth was still expired; no private material was sent. This
review-tool fault is scoped evidence only.

Reason: this operationalizes the tested source contract through the one
existing collector rather than creating parallel workers or silently dropping
the immutable Data-to-Research handoff.

## 2026-07-26 - Keep operating-efficiency review invoked and evidence-bound

Decision: add an invoked, bounded Throughput Review to the Codex orchestration
contract rather than create a fourth durable management lane. At company-goal
boundaries, task resumes, and an observed unexplained foreground idle period,
Codex may inspect ready work, active-job ownership, worker `next_due` facts,
resource contention, and test-feedback latency. It records one measured
bottleneck or idle resource and one reversible improvement in the existing
orchestration stateboard.

Every role handoff updates only its current objective, ready/running item, one
evidence pointer, recovery class, and next action. Git and the external
evidence substrate remain the searchable history. Parallel pytest runs are
allowed as isolated feedback, while the repository's required serial
goal-boundary verification remains authoritative.

The local Claude CLI drift-check was attempted before this governance change
but its OAuth session was expired; no private material was sent. The change is
reversible, private, no-cost, and does not alter authority, broker routing,
capital, model promotion, or external side effects.

Reason: long foreground sleeps and unowned wait interpretation waste available
Data, Research, and Execution capacity. A small, concrete review makes that
failure observable without adding a process-only agent, duplicate goal, or
approval checkpoint.

## 2026-07-26 - Freeze the first QQQ/SPY KIS daily sequence breadth screen

Decision: use the existing hash-attested QQQ/SPY KIS Paper private daily common
panel for one development-only sequence breadth screen. The runner requires the
exact pair, no IWM or source mixing, the qualified daily loader, `MODP=0`
unadjusted limitation, and the current unqualified corporate-action semantics.
It freezes a 20 completed-bar QQQ/SPY return window, pooled development-only
standardization, next observed daily-open entry, following observed daily-open
exit, 1 bps fee, 2 bps slippage, 3,783 development sessions, a 22-session
purge, and 951 validation sessions. Every validation feature window starts
inside validation after its own warmup; validation labels are not materialized
for fitting or tuning.

The precommit fixes compact LSTM, causal TCN, and compact attention before any
validation comparison materializes. The CPU wiring smoke uses one epoch; the
Docker CUDA screen uses eight. Both use the existing network-disabled Research
profile and write checkpoints, work state, precommit, summary, and replay
evidence only under `D:\thericher-v2\model-artifacts` or
`/app/model_artifacts`. Each candidate/symbol replay must use `local_paper`.
The screen has no winner, selection, ensemble, model promotion, sealed holdout,
broker route, Paper intent, or profitability claim.

The 2026-07-26 CPU smoke and one RTX 4090 CUDA screen completed with all three
fixed architectures and both symbols. They produced three external checkpoints
and six replay cells per attempt; no raw market data or repository artifact was
written. Their results remain descriptive evidence only. The local Claude CLI
falsification check was attempted before result interpretation but OAuth was
expired; no private material was sent. That tooling fault does not promote or
invalidate the frozen non-promotion result.

Reason: this creates a real KIS-compatible multi-architecture research loop
without mistaking a small historical comparison for a production model or
letting a missing prospective intraday pair idle the GPU.

## 2026-07-26 - Calibrate KIS data-ingress pace instead of inferring a quota

Decision: make the next bounded company objective a Data-owned KIS Paper
market-data pace calibration followed, when a ready cursor exists, by the
existing finite collector. The calibration keeps one client and one collector
per cache, distinguishes token-request starts from page-request starts and
worker scheduling, changes one pacing variable at a time, and records only
source-safe request/page/limit/elapsed facts. It may make an evidence-backed
change to the shared pace only after a test-backed implementation and a
calibration fact identify the setting and its revision condition.

The present 1.25-second request-start gate and 60-second `429`/`EGW00201`
cooldown stay active until such evidence exists. The five-minute token-start
guard spaces only token issuance attempts; it is not a token lifetime, a
five-minute page delay, or a foreground-orchestrator wait. A token or cooldown
deferral yields the owning worker while other ready lanes continue. This does
not authorize a parallel request flood, unbounded retries, a second collector
against the same cache, account/order calls, or any live route.

The required concise Claude governance drift-check was attempted before this
policy clarification, but the local CLI OAuth session was expired. No
credentials, account facts, raw rows, or holdout material were sent. That
scoped tool fault does not hold this private, non-live measurement work.

Reason: the project has an `EGW00201` observation and no verified daily quota.
Treating either a token guard or an arbitrary sleep as a general throughput
ceiling wastes collection time; blindly removing the measured controls risks
repeated rate limiting. A bounded calibration supplies the missing operational
evidence without adding an approval gate or slowing independent lanes.

## 2026-07-26 - Treat the clean one-second KIS result as an end-to-end candidate

Decision: retain the latest QQQ KIS Paper calibration as evidence for a
candidate 1.0-second request-start interval, but do not call it an effective
default until the complete owned path is aligned and tested. Before changing
the installed pace, Data must inventory the shared gate, client, collector, and
scheduler delays. A second delay remains only when it protects a path that
cannot depend on the shared gate, with its owner, reason, and observed effect
recorded. The 60-second `429`/`EGW00201` cooldown and five-minute token-start
guard remain unchanged; neither is a foreground wait or an approval boundary.

The source-safe external artifact
`D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe\20260726T150223752216Z-d52c06ef917b80e5.json`
records one token request, two accepted full terminal-head minute pages, a
1.0-second tested interval, and zero categorical limits or errors. It does not
establish a daily quota, universal route ceiling, historical pagination, or a
complete regular session. No raw bars, credentials, account facts, orders, or
live route were retained or used. The required Claude falsification-first check
was attempted before the pace change work, but local OAuth was expired; no
private material was sent.

Reason: a lower number in one rate-gate constant does not increase collection
throughput if another active layer still sleeps longer. This preserves the
measured speed opportunity while preventing hidden local throttles from being
misread as a provider constraint or an orchestrator idle period.

## 2026-07-26 - Install the measured KIS Paper one-second ingress setting

Decision: install the source-safe 1.0-second KIS Paper request-start setting
through the complete owned ingestion path. The shared market-data gate is now
1.0 seconds, and the daily and intraday collector-local pacing constants alias
that same setting. The 60-second `429`/`EGW00201` cooldown and five-minute
cross-process token-start guard remain unchanged and retain their separate
recovery purposes.

The minute capability probe now bounds a programmatic test interval to the
supported range and records a non-success fact when observed minute-page start
times are faster than the claimed interval. Focused tests pin both the pacing
alignment and that evidence invariant. A finite `session-capture` invocation
then completed through the authorized Paper market-data path; it recovered
existing QQQ/SPY cache state and added no qualified 390-minute regular-session
Research input. No account, position, order, cancel, modify, live route, raw
row output, or secret output was used.

The required concise Claude falsification check was attempted before this
persistent pace change, but the local CLI OAuth session was expired. No private
material was sent. This scoped reviewer-tool fault does not alter the bounded
measurement evidence or block independent work.

Reason: the previous 1.0-second calibration was clean enough for one
end-to-end installation only after the complete owned path was aligned. Sharing
one setting removes an accidental local throughput loss while preserving the
existing measured recovery controls and avoiding a claim of unlimited provider
capacity.

## 2026-07-26 - Bind frozen replay economics and artifact containment

Decision: every immutable local-paper research control must bind its replay
cash and quantity in the precommit before fitting and validation replay. The
L2 logistic control fixes `10000` starting cash and one-share quantity in both
its precommit and source-safe summary; callers cannot override either value.
Its core artifact API now accepts only ASCII-safe labels and resolves the
output beneath its named external artifact root, while rejecting both a
caller-supplied repository root and the actual module repository root.

The completed first artifact remains immutable but is unqualified because its
precommit did not contain the replay sizing. The corrected r2 run used the same
fixed model and data configuration, produced only external artifacts, and was
after-cost negative for both QQQ and SPY. It is descriptive falsification
evidence only: no threshold tuning, model selection, ensemble, promotion,
broker route, or Paper intent follows from either artifact.

Reason: a replay's PnL cannot be reproducible evidence if a caller can alter
its economic envelope after the model precommit. Root containment and negative
completed-bar timing tests keep a bounded research control from writing outside
its evidence boundary or accepting a cross-phase decision window.

## 2026-07-27 - Isolate a six-symbol KIS Paper daily-universe capability fact

Decision: keep the existing QQQ/SPY/IWM daily route unchanged and bind a
separate NAS-only KIS Paper capability probe to one exact official current
listing snapshot. The registry pins the source manifest hash
`sha256:129e6aa02a27e8760139a901f13e2ee4e3fc9b5d4a3e615f9dcd431154aecea4`
and the fixed ordered targets `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and
`NVDA`, all on `NAS`. Its dedicated transport accepts only that registry's
daily endpoint plus the inherited Paper token endpoint; it rejects account,
order, minute, live, and out-of-registry daily requests. The public registry
builder rejects any replacement current-listing snapshot rather than silently
following a newer file.

One finite single-client run made one token request and twelve daily-page
requests, two pages per target. All six targets were accepted with strict
`tr_cont` progress; the source-safe page facts reach from 2026-07-24 to
2025-10-08. Raw daily bytes reside only below
`D:\market_data\us_equities\kis_paper_private\daily-universe-probe\v1`.
The raw-row-free evidence is below
`D:\thericher-v2\model-artifacts\kis-paper-daily-universe-probe-v1`, with
cache manifest hash
`sha256:ffe91642bb024e7a9191c2abb774c97d529ec4b074d719b387da6dc460fd0eac`
and evidence hash
`sha256:02ce0b1004808644b0c69af6a546423508e13609aa658175f8ee09c3293e6bad`.

This proves only a current, fixed six-symbol KIS Paper daily capability. It is
not a historical point-in-time universe, corporate-action qualification,
stock-selection result, training dataset, paper order, account call, or live
route. The local Claude CLI falsification check was attempted before the
architecture change, but OAuth remained expired; no private material was
sent. That reviewer-tool limitation does not change the bounded Data fact.

Reason: a fixed current basket gives the engine an execution-compatible daily
source without pretending it solves survivorship or historical universe
construction. The separate cache and route avoid weakening the established ETF
catalog while preserving a small, replayable foundation for the next panel
contract.

## 2026-07-27 - Freeze the six-symbol KIS Paper daily panel contract

Decision: reattest only the completed NAS-only KIS Paper daily-universe probe
cache and its linked source-safe evidence before exposing a panel. The loader
pins the exact cache manifest
`sha256:ffe91642bb024e7a9191c2abb774c97d529ec4b074d719b387da6dc460fd0eac`,
probe evidence
`sha256:02ce0b1004808644b0c69af6a546423508e13609aa658175f8ee09c3293e6bad`,
registry, official directory hashes, ordered NAS scope, raw-file hashes,
`MODP=0_unadjusted`, chronological rows, and common-session alignment. It
produced six immutable `CatalogedBars` streams with 199 shared sessions from
2025-10-08 through 2026-07-24 and panel dataset hash
`sha256:fdd24d53ee9f7f5fd876f1f51561fc3fe7c8aea6d79d87bce83355dc4c07ed66`.
The separate D: panel manifest hash is
`sha256:99ba614688e199e6c40d9c20d5d22bebbe586e4e479deeee0c40a9a40417e6f4`;
the raw-row-free external panel evidence hash is
`sha256:55bfaaa68d29e8040dc08fa0c5459a7c7123fc242389b4da3f30394ae9250978`.

The completed-bar adapter exposes one homogeneous D1 `CatalogedBars` stream
only to offline/local-paper validation. It does not invoke a model, ranking,
decision, `OrderIntent`, KIS, credential, account, or broker path, and marks
the panel as not paper-trading eligible. The D1 session label means only an
observed completed replay bar; it does not establish a provider close timestamp
or runtime availability claim. The panel remains a current fixed basket, not a
historical PIT universe, corporate-action-qualified dataset, stock-selection
input, ensemble input, or profitability result. Claude's concise
falsification-first check was attempted before this contract change, but local
OAuth remained expired and no private material was sent.

Reason: a fully attested narrow panel makes the next per-symbol local-paper
baseline repeatable without weakening source separation or inventing live-like
availability claims. It creates a real engine input while leaving historical
universe, corporate-action, and execution eligibility work explicitly open.

## 2026-07-27 - Keep research utilization readiness-first

Decision: Engine Research keeps breadth, depth, ensemble, and replication work
in a ready queue. When the single GPU is free, it starts the first frozen,
eligible campaign or records the exact data, contract, or resource fact that
leaves none eligible. It does not create arbitrary training merely to maximize
GPU occupancy. Focused tests may use `pytest -n auto` only when their fixtures,
artifact roots, and external workers are process-isolated; the required
goal-boundary suite remains the serial project command.

Reason: this keeps the expensive shared resource productive without converting
utilization into a model-quality target or weakening campaign contracts,
holdout isolation, source limits, and reproducible test evidence. A concise
Claude drift-check was attempted for this agent-governance change, but the
local CLI OAuth session was expired; no private material was sent and the
scoped reviewer fault does not block this reversible policy clarification.

## 2026-07-27 - Freeze a six-symbol CPU local-paper descriptive control

Decision: evaluate the hash-attested six-symbol current-basket panel only by a
fixed per-symbol D1 CPU local-paper control. The immutable contract pins the
ordered `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA` panel hash, 159
development sessions, one purge session, 39 validation sessions, a three-bar
momentum rule, an `always_long` naive comparator, one-share sizing, five basis
point entry/exit costs, and a stride of two. The public runner always reloads
the canonical panel and rejects caller-supplied panel substitution.

Every replay is broker-free and uses only `source: local_paper`. Its temporary
event history is replayed to a flat final account and then removed; only
source-safe `precommit.json` and `summary.json` stay beneath
`D:\thericher-v2\model-artifacts\kis-paper-daily-universe-cpu-baseline-v1`.
The completed run `cpu-baseline-20260726T183947Z` has four positive and two
negative after-cost momentum-minus-comparator deltas. That observation is a
mandatory falsification prompt, not evidence of a winning stock, profitability,
promotion, ranking, ensemble, GPU campaign, or Paper order. The current panel
remains neither point-in-time nor corporate-action qualified.

Reason: a small transparent control proves the source-to-local-paper validation
loop and makes its limitations concrete without converting a current listing or
short sample into a trading decision. The required concise Claude challenge was
attempted for the unexpectedly positive relative cells, but local OAuth was
expired and no private material was sent; the scoped reviewer-tool failure does
not block independent data collection.

## 2026-07-27 - Freeze the QQQ/SPY joint event-window contract

Decision: bind the exact QQQ/SPY KIS-private daily catalog, price-free
corporate-action sidecar, and existing event-boundary audit provenance into a
schema-v2 external contract. The contract joins qualified QQQ/SPY event dates
and excludes every decision whose actual feature/target dependency intersects
an event across `t-20..t+2`. It freezes three expanding folds rooted at 3,783
development sessions, each with 22 purge and 252 validation sessions, and a
151-session untouched tail. Its active artifact is
`sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814`;
validation eligibility is `146 / 128 / 145` and the effective joint mask is
separate from the legacy `+-1` audit mask.

The artifact preserves only hashes, event date/kind metadata, segment bounds,
and eligibility identities. It is offline, candidate-only, and records
`model_execution_review: review_unavailable` with
`model_execution_eligible: false` after the required concise Claude leakage
challenge could not authenticate. The earlier v1 artifact remains immutable
historical evidence and is not the active contract. A future generic campaign
adapter must consume one fold at a time together with its sparse joint
eligibility; it cannot place all overlapping expanding folds in one
`CampaignContract`.

Reason: the existing event audit was useful provenance but could not protect a
pooled QQQ/SPY sequence's full dependency window. The contract makes that
leakage boundary deterministic without promoting a model, interpreting PnL,
loading a credential, or changing a Paper/live route.

## 2026-07-27 - Reattest one fold-local QQQ/SPY input before data consumption

Decision: require a locally rebuilt schema-v2 parent contract to match the
active immutable artifact before exposing a fold. The first resulting input is
only `expanding-1`, written outside Git with artifact hash
`sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b`
and identity
`sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db`.
It binds parent artifact `sha256:f908...bb814`, contract identity
`sha256:d8c1...7c2a6`, joint-event/audit identities, exact segment bounds, and
the sparse index tuples containing 2,345 development and 146 validation
decisions. It persists no prices, returns, provider payloads, credentials, or
execution data.

The consumer API rejects an artifact object unless that parent-rebuild
comparison has completed. It exposes exactly one named fold and does not import
or construct `CampaignContract`; a future generic campaign, if warranted, must
be independently bound to one fold rather than merge overlapping expanding
folds. The input remains offline, candidate-only, and
`model_execution_eligible: false` under `review_unavailable`.

Reason: the parent artifact intentionally keeps only safe aggregate eligibility
identities, while a downstream materializer needs the exact index tuples.
Reattestation preserves the event mask and temporal boundary without retaining
raw values or making an accidental transition into model execution or Paper
trading.

## 2026-07-27 - Materialize one reattested fold before defining a model target

Decision: bind only the reattested `expanding-1` fold input to the matching
QQQ/SPY D1 catalog through a pure, offline materializer. It preserves the
joint sparse eligibility tuple and produces one in-memory window at a time:
the predecessor at `t-20`, 20 completed-return feature rows `t-19..t`, and
future open references at `t+1/t+2`. The first external validation receipt is
`D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-1-validation-first-v1.json`,
with hash
`sha256:247142b6f84f7e0ce88e538ea6832c083be2d1b29b66b079c99a2ad6d6b2f748`
and materializer identity
`sha256:d8b096b6bb9e38aad7976cebff61ffb628a913da0e05be4a345dec4f8e41d772`.

The receipt stores only identities, scope, counts, timestamps, and index
bounds. It contains no raw bars, prices, returns, labels, predictions,
checkpoints, credentials, accounts, orders, or PnL. The materializer rejects
unreattested, stale, mismatched, or non-sparse input before exposing a window,
does not import Data/Execution on its pure path, and remains
`model_execution_eligible: false` under `review_unavailable`. It is not a
`CampaignContract`, model, replay, decision, ensemble, or Paper input.

Reason: the exact causal window must be demonstrated before a label or model
can be defined. One-window in-memory materialization keeps the event mask and
lineage intact while avoiding raw-value artifact leakage or accidental
promotion. Temporary Validation independently passed the artifact hash,
`t-20..t+2` geometry, sparse-mask, source-safe receipt, and import isolation.
Claude's concise falsification-first materializer check was attempted, but its
OAuth session remained expired and no private content was sent; this is a
scoped reviewer-tool limitation, not a block on the non-executable adapter.

## 2026-07-27 - Freeze deterministic QQQ D1 target/cost semantics before a model screen

Decision: bind one candidate-only QQQ long-versus-flat target to the reattested
`expanding-1` materializer. It uses only QQQ's observed `t+1` entry open and
`t+2` exit open, while SPY remains a completed-feature reference. The fixed
two-fill convention is one basis point fee and two basis points slippage per
fill, with `0.0001` price/fee quantization. A target is `1` only when net exit
credit strictly exceeds entry debit; equality is `0`. This is a deterministic
label convention, not cost calibration, PnL evidence, a model decision, or a
trade instruction.

The active v2 external receipt is
`D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-1-validation-first-v2.json`,
with hash
`sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486`
and target-cost identity
`sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842`.
It records only lineage, fixed formula parameters, index/timestamp geometry,
and non-executable scope. It persists no opens, returns, labels, predictions,
checkpoints, credentials, accounts, orders, or PnL.

Independent Validation found that the first immutable v1 target receipt allowed
ambient Decimal precision to affect intermediate arithmetic. Preserve it as
historical evidence, but do not use it. v2 fixes the complete calculation inside
a local Decimal context with precision 34 and `ROUND_HALF_EVEN`; its independent
reproducer, source-safety, geometry, and pure-import checks passed. The target
adapter reconstructs its own sparse materializer window instead of making a
one-window receipt an approval or input gate.

Reason: the target must be reproducible before model comparison can be trusted.
Freezing the entire Decimal context avoids a hidden host-dependent training
label while retaining the exact local-paper-style two-fill economics. Claude's
concise target-semantics check was attempted but OAuth remained expired; no
private content was sent. That tooling fault prevents no candidate-only screen,
promotion, replay, Paper, or live action.

## 2026-07-27 - Run a first candidate-only D1 classification screen without replay

Decision: run exactly one CPU smoke and one CUDA screen for the reattested
`expanding-1` QQQ/SPY D1 fold. Both use the immutable v2 target/cost semantics,
the exact sparse `2345 / 146` development/validation lists, 20-by-3 completed
return windows, development-only normalization, and two precommitted candidates:
a linear classifier and a compact GRU. The external evidence is under
`D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1`
with source-safe result identities `sha256:81e486...247f5` for CPU and
`sha256:8c4e49...32068` for CUDA.

The screen writes only lineage identities, split counts, normalization identity,
fixed specifications, and aggregate classification metrics. It writes no raw
rows, targets, predictions, model weights, replay, PnL, broker event, account,
order, or Paper decision. It creates no selection, ensemble, promotion, or
profitability claim. The CUDA job ran in Docker's network-disabled research
profile on the available RTX 4090. Temporary Validation independently passed
the frozen split, final 151-session tail exclusion, source-safety, and route
isolation. A script-level injected isolation test denies network/environment
access; the actual D: loader remains static-local and is additionally contained
by Docker network isolation.

Reason: a first fold is sufficient to prove the narrow model-input and CUDA
execution path, but not to choose a model. The parent contract's later folds
and its final tail remain untouched; `expanding-1` ends before `expanding-2`
and `expanding-3`, so exact sparse lists rather than a simple end-of-dataset
calculation define the exclusion boundary. Claude's required concise review was
attempted but OAuth remained expired. That is a promotion/reliance limitation,
not a hold on candidate-only evidence.

## 2026-07-27 - Reattest the independent expanding-2 D1 contract without merging folds

Decision: expose only the separately reattested `expanding-2` input to the
existing pure D1 materializer and deterministic v2 target/cost adapter. Its
external fold artifact is
`sha256:79723a4713b5a4751b6a62ddcd700b67542012bf3ff17a44958b7bd3d67c9305`
with fold identity
`sha256:6507570e49022133ff1055d49d610a6c32e80b92c0f881115f67d9e68e899f4e`.
It pins exactly `2511 / 128` sparse development/validation decisions. The
external source-safe materializer and target/cost receipts are
`sha256:e489f1bfadf0c685acaa0ff030d184fdc94b191aa4684b4cad7db3c69099709f`
and `sha256:4de77ac80db46b1378c5728473e2f31c04b5c5343ffde8ddf507b9afb16941da`.

The adapter accepts only one explicit verified fold at a time and currently
allows the pinned `expanding-1` and `expanding-2` contracts. It does not expose
`expanding-3`, form a multi-fold campaign, change first-fold identities, retain
market values or labels, train, replay, select, ensemble, create a Paper
decision, or call any provider or broker. Its Docker exception recognizes only
the explicit `/app/market_data` and `/app/model_artifacts` bind mounts when the
repository root is `/app`; host artifact roots still must remain outside Git.

Reason: an independently fixed second fold is the next necessary validation
input, while one-fold-at-a-time lineage prevents the overlapping expanding
windows from becoming an accidental pooled selection dataset. Claude's
falsification-first review was attempted and OAuth remained expired; Temporary
Validation independently passed the parent lineage, sparse counts, `t-20..t+2`
geometry, final 151-session-tail exclusion, source-safety, and route isolation.

## 2026-07-27 - Complete the independent expanding-2 candidate-only D1 screen

Decision: run one CPU smoke and one network-disabled Docker CUDA screen for
the already reattested `expanding-2` QQQ/SPY D1 fold. Both retain the existing
linear and compact-GRU specifications, score threshold, development-only
normalization policy, and v2 target/cost semantics. The immutable external
result identities are
`sha256:96a29b18e95e495a8ccfb0146b8654dadde37118ca99c672ef48c55b20a7106e`
for CPU and
`sha256:233629de1a3fc1a4c0a1ab2a1d86f7a0d0c4c387c3a6a26a169442f380b2826e`
for CUDA. They bind only the exact `2511 / 128` sparse split, fixed candidate
specifications, normalizer identity, and aggregate classification metrics.

Neither artifact retains rows, labels, predictions, model weights, replay,
PnL, broker, account, order, or credential data. Neither changes a threshold,
selects a model, forms an ensemble, creates a Paper decision, or supports a
profitability claim. Temporary Validation independently passed lineage, split,
tail, source-safety, and route isolation. Claude's concise E2 pin/screen
challenge again could not authenticate; the fault remains a promotion/reliance
limit, not a block on this candidate-only evidence.

Reason: the second independently fixed fold confirms the narrow CPU/CUDA input
and artifact path without letting the earlier fold steer parameters or choice.
The remaining third expanding fold and final unused tail remain untouched.

## 2026-07-27 - Reattest the final independent expanding-3 D1 input contract

Decision: expose only the separately reattested `expanding-3` input to the
existing pure D1 materializer and deterministic v2 target/cost adapter. Its
external fold artifact is
`sha256:40d6c9920a0edec12249f4b429c503b085b2e908466093496da8e0b6717128fc`
with fold identity
`sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e`.
It pins exactly `2671 / 145` sparse development/validation decisions. The
source-safe validation materializer and target/cost receipts are
`sha256:e0b90a504e10c12460282b71707649f59c49f9b2b4b4c03598d892ceb3c147c8`
and `sha256:4c389d437ed5c6ad35908dd98e1639e8ab17d41db889a7e5d1d6437c78961560`.

The explicit adapter allow-list now includes only `expanding-1`,
`expanding-2`, and `expanding-3`; it does not create a generic multi-fold
campaign. The E3 validation geometry is `t-20..t+2` and remains before the
final 151-session tail. Host and network-disabled Docker reattestation write
only to the external artifact mount and refuse immutable overwrite. No model,
training, CUDA screen, replay, selection, ensemble, PnL, Paper action, or
provider/broker call occurs in this decision.

Reason: the third fixed fold completes the independent input set needed for a
later, separately bounded candidate-only screen without reopening or pooling
earlier screen evidence. Claude's E3 drift-check attempt again failed OAuth;
Temporary Validation passed lineage, counts, tail, source-safety, and route
isolation, so the fault remains a promotion/reliance limitation only.

## 2026-07-27 - Complete the independent expanding-3 candidate-only D1 screen

Decision: run exactly one CPU smoke and one network-disabled Docker CUDA screen
for the already reattested `expanding-3` QQQ/SPY D1 fold. Both retain the
existing linear and compact-GRU specifications, score threshold,
development-only normalization policy, and v2 target/cost semantics. The
immutable external result identities are
`sha256:438b720b0aeb6e95b884d03b9e60add9e10b63030544af94a4451783b7c20e87`
for CPU and
`sha256:f3ad319969ac2b59965e1a545ef52cd17bb7afef9135c45cb4b250402803922a`
for CUDA. They bind only the exact `2671 / 145` sparse split, fixed candidate
specifications, normalizer identity, and aggregate classification metrics.

Neither artifact retains rows, labels, predictions, model weights, replay,
PnL, broker, account, order, or credential data. Neither changes a threshold,
selects a model, forms an ensemble, creates a Paper decision, or supports a
profitability claim. Temporary Validation independently passed lineage, split,
tail, source-safety, write-once artifact behavior, and route isolation. Claude's
concise E3 screen challenge could not authenticate; the fault remains a
promotion/reliance limit, not a block on this candidate-only evidence.

Reason: the third independent screen completes the fixed input/CUDA evidence
without letting earlier folds steer the E3 parameters or choice. The next
research step may inspect source-safe aggregate failures across fixed folds, but
must not pool their overlapping windows or turn that inspection into a ranking,
selection, replay, PnL, Paper, or live decision.

## 2026-07-27 - Falsify the fixed D1 candidate pair without pooling expanding folds

Decision: consume exactly the six immutable E1/E2/E3 CPU/CUDA D1
summary/precommit pairs through one fixed, offline falsification verifier. The
verifier pins canonical bytes, external containment, SHA-256, fold lineage,
source identity, split shape, development-only normalization, candidate
specification, runtime mode, and source-safe scope before it reads aggregate
classification counts. E1's older summary shape is accepted only through its
two exact pins; missing fold data is never inferred from counts or a later
artifact.

The immutable external run is
`D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-crossfold-falsification-v1\crossfold-falsification-20260727-r1`.
Its precommit identity is
`sha256:991a344522cdd9a51af370e8a8ec9e9b1335cf8f301b8bb9af4f490c325b2330`,
and its result identity is
`sha256:1bbbc7ea47ceb6ce4d2b75409d020a1486bb4a6a6ea071ce4246852cca18bc5d`.
Each candidate is compared only with the class-majority count from the same
fold and mode; the three expanding folds are never pooled, averaged, ranked, or
weighted. All twelve fixed candidate/mode/fold observations are `falsified`:
neither the fixed linear classifier nor the fixed compact GRU strictly exceeds
that fold-local majority count.

This rejects the fixed pair under the stated rule only. It does not select a
replacement, make an all-architecture claim, form an ensemble, reopen a
holdout, retune a parameter, replay, create PnL, produce a Paper input, call
KIS/Tiingo, read credentials, or affect a broker route. Temporary Data,
Execution, and Validation checks passed the input lineage, no-pooling,
source-safety, and route-isolation boundaries. Claude's required concise
falsification check could not authenticate because its OAuth session was
expired; no private content was sent, and that reviewer limitation does not
alter this bounded failure result.

Reason: overlapping expanding folds can otherwise turn a useful falsification
check into a disguised candidate-selection campaign. A strict fold-local
comparison preserves the failure signal while keeping the next architecture or
execution decision independent.

## 2026-07-27 - Make KIS collection throughput observable and work-conserving

Decision: preserve the evidence-backed 1.0-second shared KIS Paper market-data
request-start gate, 60-second categorical-limit cooldown, and five-minute
cross-process token-start guard. Do not replace them with an unmeasured
parallel request flood or a foreground sleep. One collector keeps one
in-memory client/token while it remains valid for eligible pages in its own
run; the token-start guard applies only when a new token POST is needed and does not imply
cross-process token sharing.

For every active KIS coverage package, the Data stateboard must project only
source-safe operational facts: named scope, durable cursor, accepted and
categorical-failure page counts, measured pace, remaining-page estimate or
`unknown`, ETA bucket or `unknown`, owned `next_due`, and recovery class. A
bounded reach probe remains the first step for a new endpoint/granularity
scope. After it establishes useful continuation semantics, a durable serial
collector advances whenever the measured gate permits, yields only itself for
a categorical retry, and resumes from its cursor. The estimate informs dispatch
and recovery; it is neither a completion promise nor a dependency or approval
gate for another lane.

Reason: the project needs maximum sustained accepted-page progress and a
truthful recovery handoff, not artificial idle time or an unsupported claim of
unlimited daily capacity. This makes an actual bottleneck visible before a
collector is slowed or expanded. The required concise Claude drift-check was
attempted with no private material but could not authenticate because the local
OAuth session was expired; the reviewer outage does not change the existing
measured controls or stop this reversible operating-policy clarification.

## 2026-07-27 - Preserve the canonical read-only account envelope at `/state`

Decision: have `DashboardSnapshot.to_dict()` replace the generic nested
dataclass representation of `paper_account` with the validated
`PaperAccountSnapshot.to_dict()` envelope. The local dashboard therefore
retains `kind`, `source`, `read_only`, and `submission_capability` alongside
the existing typed local account view. Its fresh factual view remains private
and loopback-only; credentials, account identifiers, and raw broker payloads
never enter the web process, Git, external evidence, logs, Claude, or chat.

Reason: generic dataclass serialization omitted the account projection's
provenance and capability fields, leaving `/state` unable to prove that a
visible Paper account fact was from the virtual read-only path. The correction
is a narrow dashboard serialization fix, does not call KIS, and does not add an
order, account, or public-service route.

## 2026-07-27 - Isolate the resumable fixed-NAS KIS Paper daily-history cache

Decision: create a dedicated `kis-paper-daily-history` Compose profile and
Data-only collector for the fixed current `AAPL`, `AMZN`, `GOOGL`, `META`,
`MSFT`, and `NVDA` NAS registry. It uses one in-memory client/token per bounded
worker, the existing 1.0-second shared request-start gate, a separate D: raw
cache and cursor index, and an external source-safe receipt root. Its credential
execution roots are fixed to the three dedicated Compose mounts and `/app`; the
profile receives only the two KIS Paper app variables, has a read-only root and
`/tmp` tmpfs, and cannot route account, position, quote, order, or live calls.

A valid empty terminal page becomes a `source_limited` state with no raw
snapshot. A non-advancing cursor becomes a scoped source-limited result before
snapshot publication, while an interrupted valid orphan is reverified and
recovered. The first three real cycles accepted 13, 50, and 69 pages at
observed 27.158, 32.664, and 27.962 pages/minute; index generation 67 retained
132 accepted pages and three categorical limits with all six cursors at
`20171120`. Every result is source-scoped only: the registry remains current,
not point-in-time, and cannot become a model, ranking, replay, PnL, or Paper
decision input.

Reason: the original two-page capability probe proved usable continuation but
not durable historical coverage. The isolated collector creates a recoverable
coverage loop without widening the generic ETF route, mutating legacy caches,
or treating a rate response as an authority hold. Claude's required concise
collector/profile challenge was attempted without private material but OAuth was
unavailable; independent Execution and Validation passed route, mount,
redaction, terminal, cursor, orphan, and root-containment checks.

## 2026-07-27 - Bound daily-history token reuse to one owned continuation worker

Decision: the fixed NAS daily-history collector may retain a single in-memory
KIS Paper client/token across its own verified future retry due. The CLI now
has one total runtime and one global chunk budget, writes its normal immutable
per-cycle receipts, and writes one immutable source-safe continuation summary
outside Git. The worker alone may wait for a future owned `next_due`; Codex and
independent lanes do not foreground-sleep for it. An elapsed historical retry
timestamp is normalized away before scheduling, so a non-retryable target
failure cannot make the collector appear to have a pending global retry.

The real bounded runs added 92 accepted pages. At index generation 117,
`AAPL/NAS` and `AMZN/NAS` are complete, `GOOGL/NAS` and `META/NAS` are
target-local source-limited results, and only `MSFT/NAS` and `NVDA/NAS` remain
target-local deferred recovery items. The real source did not produce an
eligible future retry after the continuation change, so the final summary
records `not_observed_no_future_retry_due_observed`; focused tests establish
the same-process reuse path. The frozen probe, panel, and QQQ/SPY/IWM catalog
hashes were rechecked unchanged. No account, position, open-order, quote,
order, live, Tiingo, model, replay, PnL, or Paper decision path was added.

Reason: this removes short-lived-process token loss without claiming an
unmeasured provider quota or allowing a retry wait to stall other ready work.
It keeps the data boundary recoverable and makes the next work item precise:
recover the two deferred targets independently rather than restarting a
completed or source-limited cursor. Claude's concise recovery/architecture
challenge was attempted without private material but could not authenticate;
that reviewer outage limits reliance on a material promotion decision, not this
bounded private Data implementation.

## 2026-07-27 - Close the fixed NAS daily-history recovery without widening scope

Decision: make recovery an explicit fixed contract for only `MSFT/NAS` and
`NVDA/NAS`, with expected prior failure reasons, an orphan-recovery fence, and
one collection chunk per admitted target in one core run. A valid partial
cursor is preserved as `ready` for a later bounded run; a repeated unchanged
cursor `daily_response_invalid` follows the existing target-local
`source_limited` rule. The route class remains KIS Paper token plus fixed NAS
daily price only.

The authorized bounded run accepted seven pages in five chunks and recorded one
categorical result. `MSFT/NAS` reached its target-local source limit at its
observed 2017-Q4 boundary and `NVDA/NAS` completed to 2007-Q3. The resulting
generation-121 cache is terminal for all six fixed current-listing targets:
three complete and three source-limited. It made no account, position,
open-order, quote, order, Tiingo, or live call; raw rows remain in D: only.
The independent validation and focused containment checks passed. Claude OAuth
was unavailable, so no private material was sent; that does not change this
non-promotional Data recovery fact.

Reason: a target-local recovery must resolve only its exact evidence without
turning a resumed cursor into an unbounded continuation, reviving terminal
peers, or creating a cross-lane approval hold. The completed cache remains
prospective current-listing coverage evidence, not a PIT universe, model input,
ranking claim, or Paper-order input.

## 2026-07-27 - Establish the bounded prospective QQQ runtime-to-Paper loop

Decision: use one verified `QQQ/NAS` same-session runtime input of exactly 90
contiguous completed `1m` bars ending on a 10-minute boundary, with a fixed
two-minute freshness budget. Derive 18 `5m` and 9 `10m` bars locally, evaluate
the frozen five-action target-state baseline, bind its provisional capability
authorization to the exact cache/input hashes, and replay the original proposal
through external `local_paper` state. A whole 390-minute session remains a
coverage and first-five-observer rule only; it is not a prerequisite for this
runtime decision.

Split the Docker route into an offline `kis-paper-prospective-loop` and a
separate `kis-paper-prospective-qqq-session`. The former is read-only,
network-disabled, carries no KIS environment values, and writes only
source-safe loop evidence plus private local-paper state outside Git. The latter
recomputes the verified cache input and opens KIS Paper only for a current
receipt with `enter` or `exit`. It resolves the current QQQ/NASD one-share
target from a fresh Paper account snapshot, rejects an out-of-scope inventory
or a conflicting QQQ order, obtains the fixed NAS quote proof, and delegates to
the existing persisted receipt-canary lifecycle. The bounded scheduled canary
uses cancellation after submission; an unknown result remains scoped to that
exact durable intent.

The existing intraday-head task now starts at 00:31, 02:31, 04:31, and 06:20
KST. The first three timings are evidence-backed alignment with the fresh
10-minute runtime boundary; the later capture remains coverage-only. The
dispatcher runs collection, offline loop, QQQ session, and the separate older
observer without foreground sleeps. Current prior-session cache smoke evidence
was correctly `stale` and no-intent: it did not construct the QQQ account,
quote, or order route.

Reason: this creates a small, reproducible decision-to-execution learning loop
from the data KIS can actually supply, without confusing partial-session
coverage with runtime input eligibility or promoting a deterministic baseline.
The required concise Claude falsification-first drift check was attempted before
this route change, but the local OAuth session was expired; no private data was
sent. That reviewer outage limits reliance or promotion claims, not this
authorized, reversible virtual-paper implementation.

## 2026-07-27 - Recompute exact prospective QQQ evidence offline after each session

Decision: append one `kis-paper-prospective-qqq-validation` service to the
existing intraday-head chain after the virtual-only QQQ session. The dispatcher
passes the exact safe session ID; the service has `network_mode: none`, no KIS
environment values, read-only source/cache mounts, and only the external model
artifact mount writable. It reloads the verified QQQ/NAS cache at the recorded
session timestamp, recomputes the 90-minute selector, verifies the
baseline/receipt/local-paper lineage and the virtual-only canary envelope, then
writes an immutable source-safe validation artifact.

The validator accepts a durable target-local no-intent/recovery record when no
loop exists, but it cannot invent a runtime window or action. A ready window
requires matching re-computation and local-paper replay structure. A completed
canary requires its session's existing prepared and position evidence; the
validator neither reads a KIS credential nor reaches a broker, replay store, or
private canary state. The collection exit remains the task's Data recovery
authority; validation output is independent evidence, not a new approval or
retry gate.

The existing stale-session Docker smoke validated the retained cache as the
same stale no-intent fact and wrote only an external artifact with hash
`sha256:0c0836476f49f11a8f34b387f087c8344cc1ac83bd30e29ba45fb60a50dee827`.
Claude's required scheduler/recovery drift-check was attempted before this
change and returned OAuth expiry. That `review_unavailable` outcome does not
block this offline, non-authority-changing improvement.

Reason: automatic independent re-computation closes the evidence gap between a
scheduled session and later operator/Codex reattachment without widening KIS,
Paper, or live behavior.

## 2026-07-27 - Preserve scheduled QQQ downstream recovery evidence

Decision: keep the existing named intraday-head task and its collection-first
order, but append one network-disabled, credential-free terminal receipt writer
after the prospective loop, QQQ session, offline validator, and legacy
observer. The external receipt retains only each stage's exit/status category,
safe session ID, and one target-local recovery class. Collection retains its
own nonzero exit code. After a successful collection, a nonzero or missing safe
payload from the required loop, QQQ session, or validator returns the fixed
task recovery code `20`; a failed terminal writer returns `21`. A validated
`no_intent` is normal task success. The older pair-bound observer remains
recorded but optional for this QQQ runtime cycle.

The kill cases are a downstream Docker or Python failure appearing as a
successful Windows task, a successful-but-malformed payload bypassing exact
validation evidence, a terminal receipt recording raw rows, credentials,
account facts, or broker order data, or an optional legacy observer blocking a
fresh QQQ result. Focused tests cover collection-code precedence, required
stage exit and unavailable-status recovery, session-ID mismatch,
optional-observer behavior, outside-Git storage, scheduler wiring, and the
network-disabled Compose boundary. The required concise Claude recovery
drift-check was attempted, but local OAuth refresh failed; no private data was
sent.

Reason: Task Scheduler is an operational recovery signal only when it cannot
silently hide a required stage failure. This improves reattachment of the
active QQQ execution-learning loop without widening KIS, Paper, live, cadence,
capital, or authorization behavior.

## 2026-07-27 - Resolve material company-goal blocks through alternatives

Decision: when the company objective itself has no ready route because of an
external wait, unmeasured capability, or unresolved technical contradiction,
Codex writes one compact `blocked-goal alternatives` record in the existing
orchestration projection. It contains the exact stopping fact, original plan,
two to four ready role-owned packages, owned resources, strongest kill test,
and recovery action. Codex asks Claude for one concise falsification-first
challenge, records `review_unavailable` when the CLI cannot authenticate, and
dispatches every non-conflicting package inside standing authority.

This mechanism does not apply to a lane-local cooldown, stale input, or
source-limited target when another package is ready. It creates neither a new
report family nor a second goal. A Claude conclusion may support a reversible,
no-cost choice already delegated to Codex, but cannot replace explicit operator
authority for paid commitments, unclear rights, public exposure, major runtime
replacement, `KIS_LIVE_*`, live capital, or material live-risk changes.

Reason: the QQQ prospective scheduler exposed that an external session due time
can look like a company stop even while Data, Research, and Execution have
independent work. The original plan over-weighted the scheduled observation.
The new record makes the alternate route explicit without recreating the
report/gate sprawl that v2 rejects. Claude review was attempted with no private
material during this decision and failed because local OAuth was expired.

## 2026-07-27 - Move KIS intraday coverage to continuous snapshot production

Decision: treat the existing 21 complete QQQ/SPY `1m` sessions as a pipeline
control only. Data first runs one source-safe QQQ/SPY historical
reach-and-continuation probe. If useful serial continuation is established,
Data promotes that exact route into one durable per-account cursor dispatcher
at the documented/measured Paper request pace. Fresh market-session collection
preempts historical backfill; otherwise-unused capacity advances independent
targets from atomic checkpoints. A repeated malformed non-advancing cursor
closes only that exact target as `source_limited`.

Qualified `1m` bytes remain canonical under `D:\market_data`; `5m`, `10m`,
`1h`, and `3h` views are local derivations, while direct daily history remains
a separate source contract. Research consumes immutable snapshots as they
arrive: breadth evaluates distinct fixed candidate families and naive baselines;
only replicated, error-diverse candidates may enter depth or ensemble work.
The existing virtual-only QQQ canary remains the first execution observation;
a low-frequency fixed Paper baseline follows its exact lifecycle and remains
independent of model promotion.

Reason: continuous data production, snapshot-driven research, and bounded Paper
execution can run concurrently. Multiple parallel loops against one Paper
account would not increase the documented per-account REST throughput and would
make cursor/retry recovery less reliable. The required Claude architecture
challenge was attempted without credentials, raw rows, or account data; local
OAuth was expired, so the durable record is `review_unavailable` rather than a
claim of external support.

## 2026-07-28 - Close the exact KIS prior-day minute routes without a false backfill

Decision: keep current-head capture on its existing `PINC=0` request shape and
use `PINC=1` only in the new bounded source-safe historical-reach probe. The
official KIS sample distinguishes that prior-day request scope from the normal
head path. QQQ/NAS and SPY/AMS each accepted two full terminal-head pages with
one client/token, no categorical error, no continuation cursor, and no second
exchange-date category. The external evidence paths are
`20260727T145537118121Z-09f1f5872ad57830.json` and
`20260727T150227658709Z-6d826de2f017e316.json` under
`D:\thericher-v2\model-artifacts\data\kis-paper-minute-capability-probe`.

No serial cursor dispatcher is created for those exact routes. Their
`source_limited` status is a fact about observed continuation semantics, not a
claim that every KIS minute endpoint lacks history, a reason to remove fresh
capture, or a hold on another lane. A future attempt must name an alternative
endpoint, exchange route, or compatible source and run a distinct bounded
probe.

Reason: a worker without a continuation cursor cannot safely claim a durable
history boundary or manufacture progress through repeated terminal requests.
The required concise Claude falsification request was attempted with no secrets
or raw rows, but the local OAuth session remained expired. That
`review_unavailable` fact does not hold the private Data or Research work.

## 2026-07-28 - Falsify the fixed nonlinear daily regime-tree breadth candidate

Decision: add one fixed CPU histogram-gradient tree candidate as an independent
nonlinear breadth test over the existing immutable QQQ/SPY daily input. Its
precommit freezes 20 completed-bar return features, the `3,783 / 22 / 951`
chronological split, after-cost next-open/following-open local-paper target,
three naive comparators, fixed tree parameters, and a two-symbol kill test. The
Docker research profile reads only `/app/market_data`, writes artifacts only to
`/app/model_artifacts`, has no runtime network, and persists no pickle, joblib,
checkpoint, raw row, credential, account, or broker artifact.

The `20260728-cpu-smoke` result was after-cost negative for QQQ (`-45.8296`)
and SPY (`-73.7783`), weaker than their fixed previous-bar-direction comparators
(`-1.7914` and `-44.1851`) and flat. The candidate is therefore falsified. It
is not retuned, selected, ensembled, promoted, GPU-repeated, or connected to a
Paper order.

Reason: a tree supplies a genuinely different nonlinear inductive bias without
relabeling or retuning the failed linear/sequence candidates. A clear two-symbol
failure is useful breadth evidence, and closing it prevents GPU work from being
used as an activity metric rather than an eligible research resource.

## 2026-07-28 - Close the first fresh prospective QQQ Paper cycle as no-intent

Decision: accept the first fresh scheduled QQQ cycle as complete execution
learning evidence. The collection stage exited zero, the offline runtime loop
found a ready same-session 90-minute window and classified an `eligible_exit`,
and the virtual-only session returned `account_unavailable`. It created no
canary, order, modification, cancellation, or reconciliation side effect. The
separate offline validator reattested the same no-intent and the terminal
schedule receipt recorded `complete` with scheduler exit zero.

This closes only the exact fresh receipt. `account_unavailable` is a target-local
account-read availability fact, not a model result, capital gate, KIS-wide
outage claim, reason to retry a broker action, or permission hold on a later
fresh intent. The next bounded Execution package may diagnose that secret-safe
virtual read path, then a later fresh receipt must construct a new exact intent
at its own call site before a canary can exist.

Reason: the scheduled chain now proves its complete fresh runtime/window/loop/
virtual-session/validator/terminal-receipt path while preserving no-side-effect
truth when the account read cannot support the eligible exit. Claude's required
falsification-first interpretation request used only source-safe categories but
could not authenticate because local OAuth was expired. That
`review_unavailable` result limits no private routine work.

## 2026-07-28 - Re-establish current virtual account-read health without replaying QQQ

Decision: run the existing Docker `kis-readonly` bridge once as a separate,
virtual-host-pinned, read-only observation. It completed at
`2026-07-27T15:58:23Z`; its immutable source-safe evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260727T155823938788Z-complete.json`.
The record attests only `paper_only: true`, `submit_capability: false`, USD
currency categories, one position, and zero open orders. It contains no
balance, account identifier, raw broker body, intent, order submission,
modification, cancellation, or reconciliation result.

The successful refresh establishes current account-read health only. It does
not amend the earlier completed QQQ `account_unavailable` receipt, establish
model quality or order readiness, or make a stale account projection an input
to a later canary. A later scheduled QQQ receipt must independently read its
own current account and quote before the existing persisted-intent lifecycle
can act.

Reason: an isolated availability result distinguishes a transient or
route-local account-read fault from an execution or model claim without
creating a broker retry. Claude received a source-safe falsification request
for this interpretation, but local OAuth remained expired; the recorded
outcome is `review_unavailable`, not a hold on the next private Paper cycle.

## 2026-07-28 - Redirect material company blocks into executable alternatives

Decision: a materially blocked company objective writes one compact
`blocked-goal alternatives` record in the orchestration stateboard rather than
creating a separate report family or foreground wait. The record names the
blocking fact, original plan, two to four role-owned packages, each package's
resource, engineering approach, completion evidence, kill test, and recovery.
An apparent operator decision adds concrete options, Codex's recommendation,
and the authority boundary. Codex requests Claude's falsification-first view,
then dispatches every independent package already inside standing authority.

Codex and Claude agreement may resolve only a reversible, no-cost choice that
is already delegated. Paid commitments, unclear rights, public exposure, major
runtime replacement, `KIS_LIVE_*`, live capital, and material live-risk changes
remain operator decisions. A Claude authentication fault is recorded as
`review_unavailable`; it cannot manufacture authority or turn an external timer
into a company-wide stop.

Reason: the prior QQQ objective made a future scheduled receipt its completion
condition even though ready Execution and Research work existed. This change
keeps the operator's genuine decisions visible while making routine blocked-goal
recovery concrete, bounded, and throughput-oriented. Claude's credential-free
challenge request could not authenticate because local OAuth was expired.

## 2026-07-28 - Make prospective QQQ Paper dispatch single-pass and prebuilt

Decision: remove the separate `kis-paper-prospective-loop` scheduled container.
The executed virtual-only QQQ session remains the sole owner of its embedded
local-paper recomputation, followed by the existing offline validator. Terminal
receipt compatibility is preserved, but new receipts record the retained loop
stage as `embedded` rather than pretending a separate preview ran. The legacy
pair-bound observer starts only when both Data-owned evidence files exist.

Scheduled paths no longer use Docker `--build`. Installing or updating local
Paper schedules explicitly prebuilds every named image, then each due task uses
`--pull never`; a missing image is a truthful, recoverable task failure. The
existing Windows tasks were updated after the image build, with no KIS call,
credential output, or scheduled run.

Reason: the prior route recomputed the same decision in two containers and
could spend the current receipt window building images. Focused scheduler,
receipt, Compose, QQQ session, and validator tests passed after the change.
Claude's route/governance challenge was credential-free but unavailable because
local OAuth was expired; the change remains private, reversible, and inside
standing authority.

## 2026-07-28 - Falsify the fixed CACC-D1 closing-auction candidate

Decision: close the fixed QQQ/SPY daily closing-auction co-confirmation rule.
It required both completed bars to be green and to close in their top range,
then replayed a one-share QQQ next-open/following-open local-paper position with
the existing pinned costs. The CPU-only run used the three existing hash-attested
sparse validation folds, persisted only source-safe aggregate evidence at
`D:\thericher-v2\model-artifacts\kis-daily-cacc-d1-v1\cpu-20260728t0208-cacc-d1-r2\summary.json`,
and created no network, KIS, credential, GPU, checkpoint, ensemble, or Paper
route surface.

Every fold triggered the precommitted kill rule: the first was nonpositive after
costs and all three failed to beat the time-matched always-long comparator. Do
not retune the threshold, rerun it on GPU, add it to an ensemble, promote it, or
route it to KIS Paper. No Claude result challenge is needed for this ordinary
negative result.

Independent Validation challenged the handling of adjacent qualified days. The
target contract uses half-open windows, so an exit at one next-open timestamp
precedes an adjacent re-entry at that same timestamp for this stateless,
fixed-one-share control. The active r2 precommit and focused test prove the
exit-first order, a maximum one-share position, and PnL reconciliation. The
earlier immutable r1 artifact remains historical evidence only; r2 is the
active result identity.

Reason: this was a causal rule distinct from the rejected return-window models,
with fixed folds, cost semantics, baselines, and a clear falsification rule.
Closing it preserves breadth evidence without turning GPU occupancy or
parameter-search into progress.

## 2026-07-28 - Complete the fixed ETF D1 trend-regime control without promotion

Decision: complete one fixed source-local QQQ/SPY/IWM D1 trend-regime control
under `D:\thericher-v2\model-artifacts\etf-d1-trend-regime-v1\etf-d1-trend-regime-20260728-0400`.
The rule uses only each completed D1 stream's close, SMA20, and SMA50; it enters
one simulated share at `t+1` open and exits at `t+2` open. Each ETF has a
chronological 70/30 decision-slot split, no tuning, and a matched always-long
local-paper comparator with the existing fixed costs. The source-safe result is
not globally falsified: QQQ and IWM do not beat their validation comparator,
while SPY does. IWM's `source_limited_history_scope` is a fail-closed input
requirement.

No model, winner, rank, ensemble, GPU job, Paper input, order, credential,
network, KIS call, raw price, feature, or replay-event persistence follows from
this control. The result is descriptive evidence only. The required concise
Claude falsification request used no private values but returned
`review_unavailable` because the local OAuth session expired.

Reason: this is a causal, non-fitted, independently source-local timing control
with a transparent comparator. Its one non-falsified slice is insufficient for
selection or promotion; keeping it closed prevents a fixed ETF survivor set or
single comparative outcome from becoming a strategy claim.

## 2026-07-28 - Bind a current-source-scoped universe without a liquidity claim

Decision: materialize one deterministic, external D1-only manifest from the
terminal private QQQ/SPY/IWM daily-catalog index and the frozen six-symbol
current NAS daily panel. The active manifest is
`sha256:068c34ced08eac50de53e9fbc27f3f78b36412b03aef6b602c35b4de5a083f4c`
under `D:\market_data\us_equities\source-scoped-liquid-universe\v1`.
It exposes nine stable instrument references to a pure offline unranked
Research handoff, preserving source IDs instead of treating the ETF history and
current NAS panel as one aligned cross-section.

The manifest and its consumer explicitly set historical-membership, ranking,
Paper, liquidity, and cross-partition-alignment eligibility to false. They
read source-safe manifest/index/evidence metadata only; no raw bar, credential,
provider, KIS, broker, model, replay, or order path exists in this change.

Reason: the existing data can support a reproducible opportunity-selection
foundation, but neither a current listing nor retained D1 coverage establishes
survivorship-free membership, comparable liquidity, or a tradable rank. The
compact contract makes the usable boundary explicit without creating a new
data collection or approval workflow. Claude's source-safe falsification
request could not authenticate because local OAuth was expired, so the review
status is `review_unavailable` rather than external support or a work hold.

## 2026-07-27 - Add source-partitioned D1 research eligibility

Decision: create one immutable, externally stored D1 eligibility receipt from
the reattested QQQ/SPY/IWM private daily index and frozen six-symbol current NAS
panel. Each instrument independently requires at least 60 completed D1 bars,
20 recent completed bars with positive volume, and a recent 20-bar median
dollar-turnover proxy at or above USD 10,000,000. The active receipt is
`sha256:7232c9c21c08b9564b526a34f02c109f499594a5b2a06af889b242edf2be09de`
under `D:\thericher-v2\model-artifacts\data\d1-liquidity-eligibility\v1`.

The receipt and its pure Research handoff preserve the ETF and NAS source
partitions, source hashes, categorical eligibility, reason codes, and inherited
limitations only. They persist no raw row, observed price, volume, observed
turnover, credential, account, order, model, replay, or GPU data. All nine
current references meet this narrow data proxy, while IWM retains its
source-limited history limitation. Historical membership, ranking, model
selection, Paper, executable liquidity, and cross-partition alignment remain
false.

Reason: the retained local data can now support one source-local causal control
without pretending that current listing coverage or daily turnover establishes a
cross-sectional universe, actual liquidity, or broker readiness. Claude's
credential-free interpretation request again could not authenticate because the
local OAuth session was expired; that `review_unavailable` result does not hold
the completed private offline work.

## 2026-07-28 - Quarantine conflicting fresh-head cache entries before retry

Decision: when a complete candidate page from the isolated KIS Paper
`intraday-head` cache disagrees with an active retained head snapshot, the
installed `head` and `session-capture` paths write an index-only quarantine
marker for the exact old `chunk_key`, manifest hash, and raw hash. The old
manifest and raw bytes remain immutable under `D:\market_data`; the marker
excludes only that entry from active cache/coverage consumption and prevents
only that exact orphan snapshot from being reactivated. The current conflicting
candidate remains rejected. A later independently fetched page must be clean
before it becomes an active cache snapshot.

Cursor-backed historical collection keeps the strict conflict rejection and
cannot use this behavior. The change is confined to explicit fresh-head mode,
does not alter a broker, credential, account, Paper order, model, or research
input, and cannot establish a general latest-wins provider-revision rule.

Implementation is fail closed: the shared index validator requires the exact
quarantined chunk, manifest, and raw identities before it excludes an orphan
from recovery. New retained snapshots persist `collection_scope` as `head` or
`historical`; only an explicit persisted `head` snapshot can be quarantined.
Legacy snapshots without this scope and all historical terminal snapshots keep
strict rejection, even if a future caller passes a head option.

The first later fresh capture completed with one clean 120-row page each for
QQQ/NAS and SPY/AMS. Its chained QQQ route truthfully returned
`no_intent/runtime_window_stale`: the latest completed bar ended at 19:20Z and
the route observed it at 19:22:46Z, beyond the fixed two-minute budget. A later
19:31Z scheduled run, started before the rebuilt scoped image was available,
again encountered a retained-cache conflict and left the current head cache in
`reconcile`. The immutable earlier terminal receipt remains valid only for its
exact route; a later clean page must restore current cache input. This exposes
a bounded freshness-calibration question and does not justify forcing a Paper
intent or changing a model conclusion.

Reason: the latest QQQ/SPY head capture reported
`minute_duplicate_conflict/retained_cache`. No provider revision ID or finality
evidence proves that a newer observation corrects a completed bar, so same-run
adoption would silently change prospective Paper input. A temporary independent
review challenged that risk; its focused tests passed. Claude's source-safe
recovery challenge could not authenticate because the local OAuth session is
expired, so its verdict is `review_unavailable`, not a stop on this reversible
private recovery.

## 2026-07-27 - Make blocked-goal recovery a falsifiable dispatch decision

Decision: before declaring a company objective materially blocked, Codex runs
the bounded Throughput Review to verify that no ready, non-conflicting package
was simply left undispatched. The resulting compact `blocked-goal alternatives`
record in `agents/orchestration.md` keeps the exact blocking fact and original
plan, then names two to four concrete role-owned alternatives with resource,
engineering approach, completion evidence, strongest kill test, and recovery
action. Claude's falsification-first review tests the classification of the
block, whether each alternative advances the named company outcome, and whether
the proposed recovery crosses a reserved authority boundary.

For an already-delegated reversible, no-cost choice, Codex may act only when
its conclusion and Claude's successful `supported-with-limits` conclusion
agree. For a true operator-authority decision, the same analysis produces one
recommended direction and a list of independently safe preparation work; it
does not self-authorize paid commitments, unclear rights, public exposure,
major runtime replacement, `KIS_LIVE_*`, live capital, or material live-risk
changes. `review_unavailable` records a Claude tooling fault only and never
turns an external wait into a company-wide hold.

Reason: autonomous long-running work needs a concrete recovery path when a
goal's original route fails, while the operator must retain the few decisions
that genuinely change business, external, or live-risk authority. This keeps
alternative work product-oriented rather than growing a separate report or
approval system. Claude received the source-safe challenge for this refinement,
but the local CLI OAuth session was expired, so no verdict was available.

## 2026-07-28 - Bind QQQ Paper execution to a source-safe runtime deadline

Decision: make the existing two-minute QQQ completed-bar freshness budget a
Data-owned runtime/Paper contract, with an inclusive exact-boundary rule. The
runtime-window projection now records only completed-window end, route
observation time, lag category, and selected budget. A stale projection must
contain an over-budget candidate; a ready projection must be within or exactly
at the budget. This policy governs only the current QQQ runtime/Paper path;
offline Research continues to own any explicitly supplied campaign age.

The prospective QQQ session rechecks that contract before it constructs the
Paper account client. It rechecks again after quote preparation, and the same
freshness predicate is evaluated inside the existing canary lock immediately
before a broker submission. The route therefore emits a source-safe no-intent
when it expires before account access or during preparation, and stale data
cannot pass the final submission predicate. No limit was widened, no model was
selected, and no live route was added.

The offline QQQ validator accepts a legacy session that lacks the new field,
then writes a separate immutable `runtime-freshness-v2` result rather than
overwriting a prior validation artifact. It validates every recorded freshness
fact against the verified cache and its session reason. The 19:48Z QQQ stale
session reattached under this contract with no network, credential, account,
order, or replay mutation.

Reason: one checked freshness timestamp was insufficient to prove that a
current input stayed current across an account/quote/canary lifecycle. The
contract makes the exact data deadline explicit while preserving local replay,
Paper-only routing, legacy evidence, and the external artifact immutability
model. A source-safe falsification-first Claude request was attempted before
reliance on this execution-risk change, but the local OAuth session remained
expired; its status is `review_unavailable`, not a private-work hold.

## 2026-07-28 - Close the phase-local QQQ/SPY relative-regime control

Decision: complete one fixed CPU-only QQQ/SPY D1 relative-regime falsification
control against the existing hash-attested 4,756-session private catalog. Keep
the existing `3,783 / 22 / 951` chronological geometry, but form each
63-session causal comparison entirely inside its phase so no development or
purge bar enters a validation feature. Use two-session non-overlapping slots,
one-share fixed local-paper economics, and only time-matched `always_long` and
`flat` comparators. Persist source-safe, content-addressed external receipts
only; no bars, derived values, per-decision values, event logs, weights, or
checkpoints are retained.

The CPU smoke and full 443-slot validation completed. The candidate made 312
local-paper trades but did not strictly exceed the after-cost always-long
baseline, so the fixed strict kill rule classifies it `falsified`. It cannot be
retuned, selected, ensembled, promoted, sent to GPU depth work, or routed to
KIS Paper.

Reason: phase-local warmup preserves the existing source contract without
allowing a longer lookback to leak across its fixed phase boundary. The result
is ordinary candidate-only falsification evidence, not a promotion or
authority change, so no Claude result challenge was required. The separate
source-safe governance challenge was reattempted on 2026-07-28 and the local
Claude CLI OAuth session remained expired; that tooling fact did not hold this
private offline control.

## 2026-07-28 - Close the QQQ/SPY relative-allocation control

Decision: complete one separate CPU-only QQQ/SPY D1 opportunity-selection
control against the same hash-attested 4,756-session private catalog. The
fixed rule compares phase-local 63-session QQQ and SPY close changes at `t`,
selects one QQQ share only on a strict QQQ win (otherwise one SPY share), enters
at `t+1` open, and flattens at `t+2` open. The fixed `3,783 / 22 / 951`
geometry, two-session cadence, one-share costs, and time-matched
`always_qqq`, `always_spy`, and `flat` comparators were precommitted. Every
role used one sequential in-memory `local_paper` account and retained only
aggregate source-safe receipts beneath
`D:\thericher-v2\model-artifacts\kis-daily-relative-allocation-control-v1`.

The CPU smoke completed, then the full 443-slot validation selected QQQ 312
times and SPY 131 times. Its candidate after-cost PnL was `172.3873`, below
the matched always-QQQ `210.2283` baseline (though above always-SPY and flat),
so the strict three-comparator rule classifies it `falsified`. All candidate
and comparator fills remained replayable `local_paper` fills and every account
was flat between slots.

No parameter change, model selection, ensemble, GPU job, KIS call, Paper
order, or live route follows. This is an ordinary negative control result, so
it does not require a Claude promotion or holdout challenge.

Reason: opportunity selection needs a distinct, time-matched allocation target
rather than another label for the closed QQQ-versus-flat rule. Closing the
candidate at its fixed comparator boundary preserves useful attribution without
letting a partial relative win become a strategy claim.

## 2026-07-28 - Materialize the terminal NAS daily-history cache as a source-local panel

Decision: materialize the already terminal private KIS Paper NAS daily-history
cache into the hash-attested
`kis.paper.private.daily.nas.history.panel-v1` input. The loader reattests every
index, snapshot-manifest, compressed raw-file, row-fingerprint, cursor-chain,
and duplicate identity before exposing immutable completed D1 `CatalogedBars`.
It accepts only the fixed current NAS registry and preserves unadjusted and
corporate-action limitations rather than repairing or blending them.

The D:-resident manifest is
`D:\market_data\us_equities\kis_paper_private\daily-nas-history-panel\v1\panel=7e8d6fe54dd5252fc4b9\manifest.json`
with dataset hash
`sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`.
Its separate external receipt is under
`D:\thericher-v2\model-artifacts\data\kis-paper-daily-nas-history-panel-v1`.
The verified common intersection has 2,179 sessions from `2017-Q4` through
`2026-Q3`. AAPL, AMZN, and NVDA are complete; GOOGL, META, and MSFT remain
source-limited with their factual terminal reasons intact.

The panel is eligible only as a source-local offline Research input. It makes
no point-in-time membership, liquidity, ranking, strategy, model, Paper,
profitability, or live claim. It made no network/KIS/credential/account/order
call and persisted no raw row or value outside the existing source cache.

Reason: the terminal cache was useful but not yet a reproducible long-history
input. This narrow reattestation boundary unlocks an honest chronological
campaign contract without treating a current listing as a historical universe
or forcing a GPU job from unqualified bytes.

## 2026-07-28 - Freeze a phase-local per-symbol NAS D1 sequence campaign before training

Decision: bind the materialized six-symbol NAS panel to one exact offline
campaign contract before CPU or GPU model work. The Data adapter reattests the
panel/cache and slices the verified common intersection into exactly `1,510 /
22 / 647` development, purge, and validation sessions. It preserves each
terminal source status and rejects index/hash/source-path drift, incomplete bars,
misalignment, or phase crossing.

Each per-symbol sample contains twenty completed daily close-return observations
at `t-19..t`; its prior `t-20` close anchor is also required to be inside the
same phase. Development labels are strict positive one-share after-cost outcomes
from `t+1` open to `t+2` open with 1 bps fee and 2 bps slippage per fill.
Validation uses a separate target-free sample type, so it cannot carry a label.
Development examples have stride one; the later fixed comparators `flat`,
`always_long`, and `previous_bar_direction` use two-session slots, with a
previous-direction tie resolving to flat.

The contract hash also binds the exact phase boundary dates and the cost-label
calculation mode: a `0.0001` price quantum, 28 significant Decimal digits, and
`ROUND_HALF_EVEN`. This prevents an ambient Decimal context or same-count split
shift from silently changing a target before model work starts.

The external immutable precommit is under
`D:\thericher-v2\model-artifacts\research\kis-nas-d1-sequence-campaign-v1`
with contract hash
`sha256:5a9ceb6df7b6c1909ef452b8851fbd7bd23ec03660e9fc75bb278377079aaea5`
and receipt hash
`sha256:c54e795b3fb2caa76c9367a72aadc1c0ac685241bd5c59e2e12bdb0af603d37e`.
It records only hashes, scopes, counts, costs, comparators, source limitations,
and the next eligible packages: six independent per-symbol L2-logistic CPU
smokes and target-free CUDA breadth across LSTM, causal TCN, and compact
attention.

No model fit, checkpoint, prediction, validation-label reveal, replay, PnL,
selection, ensemble, KIS call, Paper action, or live route occurred. The current
listing remains non-PIT and the unadjusted/corporate-action limitations remain
unchanged.

Reason: this fixes the causal and economic meaning before allocating the idle
GPU, while retaining enough development coverage for a bounded breadth package
and keeping the later validation/evaluation authority independent.

## 2026-07-28 - Correct the NAS shared-worktree integration hold

Decision: retire the earlier NAS integration hold. The phase-local adapter was
already in the shared worktree, so its unknown authorship was not evidence of a
technical contradiction. Codex inspected the diff and provenance, completed
focused reattestation/isolation tests, and materialized the immutable campaign
receipt. A shared-worktree file now receives that bounded treatment or a scoped
replacement; it cannot itself defer unrelated work.

The canonical blocked-goal, Claude-review, dispatch, and operator-authority
rules remain in `AGENTS.md`; this decision adds no second workflow or authority
rule. Claude's source-safe challenge was attempted on 2026-07-28 but its local
OAuth session had expired, so the review status is `review_unavailable`.

Reason: the old hold delayed a ready Research contract without producing a new
data, model, validation, or execution fact. The correction makes the concrete
implementation and its tests, rather than unverifiable authorship, the recovery
boundary.

## 2026-07-28 - Complete NAS D1 breadth without opening validation targets

Decision: complete the frozen NAS D1 model-plumbing package exactly as
precommitted: six independent per-symbol deterministic CPU L2-logistic smokes,
then 18 network-disabled Docker CUDA candidates across LSTM, causal TCN, and
compact attention. Every fit uses only its symbol's development samples and
standardizer; every validation forward consumes a separate target-free type.
The CPU summary is `sha256:4bfb8448a61cd741e63b12ab71fb58511be3700c936450286b2257b619067196`.
The CUDA summary is `sha256:43a4f91c96cf2a081e7c53fc2ab7fa93c03bf7d7beee0f8b2524f9aa37492ed7`.
All 18 checkpoints are external `state_dict` files that passed
`weights_only=True` reload and strict state compatibility checks.

This is not an evaluation, profitability, selection, ensemble, replay, PnL, or
Paper result. Validation labels, predictions, and per-decision values remain
unmaterialized. The current-listing, unadjusted, and corporate-action
limitations remain unchanged. A later evaluator must precommit its target,
threshold, local-paper attribution, comparators, and stop rule before reading
any validation target.

Reason: bounded breadth verifies that the source-local campaign can reach
real CPU and CUDA model artifacts safely, while preserving an independent
validation boundary rather than converting training loss into a trading claim.

## 2026-07-28 - Treat exact Docker external mounts as external storage

Decision: when a repository-rooted process runs in Docker, permit a path under
`<repo>/market_data` or `<repo>/model_artifacts` only when that exact root is a
real non-symlink mount and the requested path stays beneath it. All other Git
children remain invalid. The NAS panel reader and campaign precommit writer now
use this narrow rule; the breadth artifact runner applies the same check to its
Docker artifact exception.

Reason: the first two CUDA attempts correctly stopped before model execution
because generic Git-root protection mistook the documented bind mounts for
repository storage. The scoped mount check preserves the Git-artifact rule while
making the offline Docker research runtime usable. Claude's concise
falsification-first drift-check attempt was `review_unavailable` due expired
local OAuth; no credential, network, KIS, broker, or live path was used.

## 2026-07-28 - Require a complete frozen CPU receipt before NAS CUDA breadth

Decision: harden the NAS D1 breadth entrypoint after independent review. The
production runner must calculate and match the one frozen campaign contract and
campaign-precommit identity before writing any breadth artifact. A CUDA run must
also receive an immutable sibling CPU precommit and a complete source-safe CPU
summary that exactly names the six fixed L2 specifications, per-symbol
standardizers, development counts, target-free validation shapes, and
non-selection policy. Both CPU input paths must remain outside the Git
workspace. A minimal, mismatched, or Git-resident JSON summary is rejected
before a CUDA output directory exists. The Docker research service keeps repository
`data` and `reports` bind mounts read-only; only the documented external market
data and artifact mounts can be used for mutable research bytes.

The focused host reattestation `cpu-smoke-20260728-r2` reproduced existing CPU
summary `sha256:4bfb8448a61cd741e63b12ab71fb58511be3700c936450286b2257b619067196`.
The network-disabled Docker mount check confirmed `/app/market_data` and
`/app/model_artifacts` are mounts while `/app/data` and `/app/reports` are not
writable. No validation target, replay, PnL, selection, KIS request, or broker
route was opened.

Reason: breadth artifacts become a trustworthy fixed input to the later sealed
evaluator only when their model lineage and write boundary are explicit. This
does not convert the CPU or CUDA result into profitability evidence or a model
selection rule.

## 2026-07-28 - Complete sealed NAS attribution in one Docker runtime

Decision: preserve the immutable r1 cross-runtime failure rather than relaxing
its exact CPU parameter hashes or bridging host predictions into Docker. Rebuild
the unchanged frozen six-CPU/18-CUDA breadth package inside the network-disabled
Docker research runtime, then bind the sealed evaluator only to those r2
receipts. The dataset, six symbols, phase split, feature definition, costs,
candidate architectures, seeds, threshold, comparators, and non-promotion policy
remain unchanged.

Docker r2 completed with CPU and CUDA summaries
`sha256:e60cf92d82b5b6dadb361213e2425845cab4d2f7f64c34a08799b7fd73ffc4fa`
and
`sha256:2c213d0a6aefa63c89aeddf551021d2e92370b59258cde672200301c84253a3f`.
The later Docker r4 sealed evaluator completed the 24 fixed candidate and 18
fixed comparator runs. Its immutable source-safe precommit and summary hashes
are `sha256:99975045bdecd27a578d158c1b4e0ecb9eea3894983cffad5483175a03f71746`
and `sha256:0323424fd24283edd09b517332b454d00bd13a72e698f6a9ce2d92d6b435fedf`.
Every fill was in-memory `local_paper`, every replay reconstructed to a
terminal-flat account, and no raw source row, target, prediction, event row,
checkpoint copy, broker request, KIS call, selection, ensemble, promotion, or
Paper order was produced.

Independent review found that r2 receipts did not independently identify their
runtime class. Add only the source-safe marker observation
`execution_environment.kind` plus its detection field to sealed precommit,
completion, and failure receipts; it is marker-bound to `docker` or `host` and
excludes paths, hardware, network identifiers, values, and secrets. It does not
attest Compose network or mount policy; versioned Compose configuration and its
focused tests establish that contract. Docker r4 records `docker` with an
explicit marker-detection field. The focused
test proves marker behavior while the actual Docker run proves strict checkpoint
reload, inference, local-paper replay, and receipt generation together.

The external output writer now rejects every symlink or Windows junction
component before it creates the fixed run directory, rechecks the created path,
and rechecks receipt parents immediately before each write. This prevents an
external artifact tree from redirecting sealed receipts into Git. Focused tests
cover a linked output parent, a junction marker, and a forced post-precommit
failure receipt. Claude's concise follow-up drift check for this output-boundary
hardening was attempted but OAuth remained expired; it stays
`review_unavailable` and does not change the candidate-only scope.

Reason: runtime coherence preserves exact candidate lineage at the sealed
boundary, and the minimal environment field makes the offline Docker evidence
auditable without creating a reporting framework or exposing protected data.

## 2026-07-28 - Freeze a distinct NAS volatility-conditioned trend breadth package

Decision: add one new, causal NAS D1 hypothesis without consulting the sealed
r4 aggregate result: per-symbol completed-bar `20 x 5` windows of log return,
10-bar trend, realized volatility, normalized true range, and range-conditioned
trend. Freeze the existing source-local six-symbol panel, chronological phase
geometry, development-only target construction, fixed costs, fixed comparator
set, and the later paired local-paper kill rule before fitting. The candidate
package is six deterministic CPU L2-logistic smokes followed by 18
network-disabled Docker CUDA LSTM, causal-TCN, and compact-attention candidates.

The immutable campaign precommit is
`sha256:9f71107718c3235c1a52a092f3362b114e16f33387d7afaafc4b9d390e57deb9`.
CPU r2 and CUDA r2 summaries are
`sha256:65ba9f682bb6477bd7fdfa5d61761fb7ab67f3db23601187a92f88415bad69a8`
and `sha256:3158ac0e69c002394d97dc5f52946d70637e082f292a7c549498f4c045e5bc2c`.
The CUDA output contains 18 external `state_dict` checkpoints that passed
safe `weights_only=True` reload. No validation target, prediction, PnL,
ranking, selection, ensemble, promotion, KIS request, or Paper action was
opened or retained.

Full campaign attestation remains mandatory at construction and immutable-write
boundaries. Repeated in-memory CPU/GPU consumers use a compact identity derived
from the fully attested campaign and frozen standardizer hashes, avoiding
repeated whole-panel rehashing without changing the durable evidence boundary.
The Claude drift-check attempt was `review_unavailable` because OAuth could not
refresh; the package stays candidate-only and non-promoting.

Reason: this gives the engine a genuinely different causal representation and
multiple architecture families while retaining a later sealed falsification
boundary instead of converting training diagnostics into a trading conclusion.

## 2026-07-28 - Preserve the sealed NAS volatility trend result as mixed evidence

Decision: complete one immutable Docker r5 sealed local-paper evaluation of the
frozen NAS volatility-conditioned candidate package, then preserve it as mixed
candidate-only evidence. The r5 precommit and source-safe summary are
`sha256:e7bd2cd8b17959a9b6df5c49c8bfa5a22ae875d9b2a53311890d55e51d7b4618`
and `sha256:803ead4440415dd2818c2bc81a5579f5ae01354a43955ad97e5a526a8634d010`.
It classified all 24 frozen candidates and 36 fixed comparator cells; six
paired cells met the precommitted kill rule. No candidate is selected, ranked,
ensembled, promoted, or routed to KIS Paper from that result.

The evaluator verifies CPU refit lineage against the frozen receipt, loads CUDA
state with `weights_only=True`, writes a source-safe candidate-evidence failure
receipt before a target can open, and calculates drawdown from entry, intrabar
low, and exit equity marks. Every actual fill remained in-memory
`source: local_paper` and replayed to a terminal-flat account. Raw bars,
targets, predictions, event rows, checkpoint copies, KIS calls, broker effects,
and live behavior remain absent. Claude's post-evaluation falsification check
was attempted and returned `review_unavailable` because local OAuth is expired.

Reason: a subset of pair-level passes is insufficient to create a trading
decision, while an immutable, replayable receipt is useful input to a later
independent prospective observation contract. The next package observes newly
arriving local-cache data without reusing r5 to select a candidate.

## 2026-07-28 - Add a bounded NAS D1 prospective shadow-observation contract

Decision: add one offline prospective observer for the frozen six-symbol NAS
volatility-conditioned package. It reattests exact r2 CPU/CUDA and r5 receipt
hashes, derives the boundary from the reattested frozen validation session
rather than file time, and accepts only a complete all-six-symbol D1 window:
one post-boundary decision followed by complete `t+1` and `t+2` bars. It uses
30 completed bars for causal features and non-overlapping three-session slots.
If no such window exists it writes an immutable external `input_unavailable`
receipt, which is a completed scoped state rather than a scheduler or trading
gate.

The observer's Docker smoke is network-disabled and wrote precommit
`sha256:628663053db396626e009ec154ce17b7849fb5f2614384f74a5818f6e46f24da`
and `input_unavailable` receipt
`sha256:56e0f503b7248e10e8461a1752c3baf7df5f1a70e89d0a63909f08cfde78616a`.
The local cache has zero common sessions after 2026-07-24. No r5 outcome,
candidate selection, tuning, ranking, ensemble, KIS call, account route, or
Paper order is consumed or created. When eligible data later exists, all 24
frozen candidates must replay independently through in-memory `local_paper`
and reconstruct terminal-flat accounts before aggregate-only evidence can be
written. The target runtime remains the network-disabled Docker environment;
the host runtime does not silently substitute a different frozen precommit.

Reason: a prospective observation needs a hard temporal boundary and exact
artifact lineage, but missing forward data must not stall independent Data work
or fabricate a model result.

## 2026-07-28 - Separate NAS D1 forward cache from frozen history

Decision: retain a distinct six-symbol, current-D1 KIS Paper forward cache under
`D:\market_data\us_equities\kis_paper_private\daily-nas-forward\v1` and join
it with the frozen NAS D1 panel only through a read-only in-memory projection.
The first bounded single-client run accepted one daily page for each fixed NAS
symbol and retained one common session. The frozen panel reattested unchanged at
`sha256:7e8d6fe54dd5252fc4b9548b70e3bb31aefcd282922a50c1ca7c58a94d57dc8e`;
the source-safe forward cache and index identities are
`sha256:700f0f435ba6f09fc93fbd295d215d6da03245d2930a9cc8708d6cbf95aa3aa9`
and `sha256:8e5a6a96c8da6c3a2924f35816770da0e7319381e57c5d29ecb9b703fe49ee18`.

The cache keeps source-safe per-target accepted-page and categorical-failure
counts. A valid exact retry increments only the accepted-page evidence and does
not replace immutable raw snapshots. Transport, auth, rate, and other
recoverable failures are `deferred`, never a speculative `source_limited`
claim. A target-local cache conflict remains a reconcile event and the runner
writes an immutable source-safe recovery receipt even when cache commit fails.
The collection health and prospective consumer readiness are distinct: an
incomplete all-six basket is `partial`, and the read-only consumer is
`input_unavailable` until three common later sessions exist. No model,
selection, ensemble, KIS Paper order, account route, or live behavior follows.

The required concise Claude forward-cache drift-check was requested with no
private material, but its local OAuth session was expired; record
`review_unavailable`. The independent review identified the transient-failure,
consumer-readiness, accepted-page, and failed-receipt risks above, and focused
regression tests cover their fixes.

Reason: forward observations must accumulate without rewriting the historical
research input, while operational evidence must remain truthful enough to resume
collection and avoid mistaking an external delay for a data boundary or model
signal.

## 2026-07-28 - Automate the NAS D1 forward observation chain

Decision: install one KST 06:40 Tuesday-through-Saturday Windows task for the
fixed NAS D1 forward cache. The task runs a credential-free preflight first. A
verified current cache goes directly to the network-disabled observer; only
preflight exit `10` invokes the credentialed six-symbol collector. A collector
result of `partial` or `deferred`, and an invalid observer cache, returns
recovery exit `20` and prevents observation. This preserves one bounded
collector per cache while preventing stale or incomplete input from looking
like a new prospective result.

The observer container has no KIS credentials, has network disabled, reads D:
market data read-only, and may use CUDA only for an eligible frozen consumer.
The actual one-session smoke returned scoped `input_unavailable`; a CUDA probe
confirmed one PyTorch-visible device but created no model artifact or training
run. The task was installed only after its exact preflight, collector, and
observer images were verified. The installer may reattest already-built images
with `-SkipImageBuild` during bounded installer recovery; normal installation
still builds them first.

Claude's required scheduler/recovery challenge was attempted without private
material and returned `review_unavailable` because local OAuth could not
refresh. Independent review identified and the implementation fixed the
partial-collection and observer-recovery false-success paths.

Reason: current D1 data should advance automatically without turning calendar
waiting into an orchestrator hold, and a prospective observation must be
truthful about its source completeness before it can inform any later research.

## 2026-07-28 - Harden the private Paper account console boundary

Decision: make the existing `kis-readonly` Compose service root filesystem
read-only and provide only `/tmp` tmpfs, while preserving its existing writable
runtime and external artifact mounts. Add one dashboard HTTP integration test
that injects a malformed account projection and proves the rendered state is
fact-free `unavailable`, with the malformed raw marker absent.

The post-hardening virtual-only bridge completed and wrote source-safe external
evidence `execution/kis-paper-console-bridge/20260728T115736150112Z-complete.json`.
The loopback dashboard consumed the fresh complete projection with read-only and
no-submission provenance. No intent, submit, modify, cancel, reconciliation,
live credential, or public endpoint was introduced. The source-safe Claude
governance challenge for the surrounding blocked-goal/authority policy was
attempted again and returned `review_unavailable` because local OAuth could not
refresh; this small runtime hardening does not rely on a reviewer verdict or
change an authority boundary.

Reason: the local console needs a current virtual account view, but accidental
container-local persistence of a broker response is unnecessary risk. The
existing volume contract is sufficient for the sanitized runtime projection and
fact-minimized external evidence without widening KIS behavior.

## 2026-07-28 - Make NAS D1 candle-state contracts host/Docker portable

Decision: preserve the failed candle-state r1 precommit and r2 independent
review findings as immutable scoped recovery evidence, then start a separate
r3/v3 contract/artifact family. The r3 feature definition runs every Decimal
division and logarithm inside one fixed local context, and its normalizer uses
ordered `fsum` reduction with fixed-precision canonicalization before identity
hashing. CPU writes an immutable source-safe summary-attestation sidecar before
CUDA may consume its summary. This makes the frozen six-symbol source contract
reproducible on the Windows host and network-disabled Linux CUDA container
without weakening the immutable precommit rule.

The new r3 package completed six CPU smoke candidates and 18 CUDA LSTM,
causal-TCN, and compact-attention candidates with target-free validation
forwards. Artifacts, including safe-weight checkpoints, remain only under
`D:\thericher-v2\model-artifacts`. The requested Claude drift check was
attempted without private material but the local OAuth session was expired, so
the record is `review_unavailable`. No selection, ensemble, PnL claim, KIS
call, Paper order, or live behavior follows.

Reason: an immutable research contract must reject genuine drift while treating
runtime-specific last-bit math differences and receipt-integrity gaps as
versioned feature-semantic changes, not as reasons to relax reproducibility
checks.

## 2026-07-28 - Separate static D1 opportunity plumbing from KIS runtime evidence

Decision: complete one development-only Norgate D1 opportunity campaign from
the existing frozen 523-symbol panel, but keep it strictly separate from KIS
runtime evidence. The contract uses a 22-date purge between development and
validation so the feature/label dependency window cannot overlap. Its immutable
external contract, CPU baseline, and single Docker PyTorch CUDA causal-TCN job
are `sha256:27e0...d8d348`, `sha256:913e...3dbf42f5`, and
`sha256:f091...541fa13`. The run has no model selection, ranking, ensemble,
Pnl, broker, KIS, or Paper consequence.

Claude's source-safe falsification review returned `supported-with-limits`: a
static survivor panel remains unsuitable as a KIS collection registry, and D1
field shape does not establish adjustment or corporate-action equivalence. The
next coverage package therefore creates a separate cache from the already
hash-attested KIS current-directory source, carries typed non-PIT/non-ranking
scope, and never joins Norgate rows or target selection to KIS data.

Reason: the campaign validates causal research plumbing and CUDA lineage without
mistaking static trial data for executable runtime coverage, while preserving a
direct path to a broad KIS-native D1 input.

## 2026-07-29 - Run broad KIS D1 collection as a source-separated, breadth-first cache

Decision: use the hash-attested 2026-07-18 KIS current NASDAQ directory only to
build a dedicated `daily-nas-broad/v1` current-listing registry. The registry
has 2,119 current common-stock targets and carries explicit
`current_listing_only`, `non_pit`, `non_ranking`, and no-provider-price scope.
It is never a historical membership, survivorship repair, research ranking, or
Paper-trading input.

The new cache does not alter the terminal ETF or fixed NAS contracts. It
reattests its registry before client construction, injects the exact daily
symbol/exchange allowlist, keeps raw snapshots/index data on D:, and keeps
source-safe receipts under the external artifact root. The initial deterministic
bootstrap accepted 16 pages across eight chunks with zero categorical failures;
the first continuation accepted 64 pages across 32 chunks with zero categorical
failures. Their receipt hashes are
`sha256:f57a6aa036670c4a6282251ce45e8ab04765cbe4c86414fbb4b89f43c472b182`
and
`sha256:e8f98a779e49c1df0ed46bba812c113853db507c1f0f51aab8ed56b45eecc914`.

The selector prioritizes lower accepted-page counts before stable registry
position so early work broadens coverage. Target-local repeated source failures
persist a consecutive reason/count and become `source_limited` only after two
same-source failures; auth/rate/token problems remain deferred. Known rate or
token retry times yield before client construction, preserving the retry as
owned scheduler state rather than foreground sleep. Legacy index records gain
these retry fields only while the cache worker holds its lock.

Install the continuation task with KST Tuesday-through-Saturday triggers every
30 minutes from 07:15 through 20:45. One active worker is bounded at 24,000
chunks or 840 minutes; task `IgnoreNew` avoids duplicate collectors, later
triggers recover a failed worker, and the 870-minute Windows limit leaves time
for Docker startup and final source-safe receipt writing. Fresh-head collection
shares the measured one-second gate and remains independent.

Claude's first source-safe review was `uncertain` and found repeat-failure
starvation plus a potential long rate-limit sleep. Both were fixed with focused
tests and a second manual continuation; the follow-up verdict was
`supported-with-limits`, with the task-timeout adjustment adopted. No account,
quote, order, live, model, ranking, PnL, or provider-join route is introduced.

Reason: broad KIS-native daily coverage should progress continuously without
reusing a survivor panel or letting one broken target, a cooldown, or a process
timeout stall the whole engine loop.

## 2026-07-29 - Materialize broad KIS D1 only from a byte-stable source snapshot

Decision: the active `daily-nas-broad/v1` cache now has a separate read-only
panel materializer. It reads an index twice and accepts it only when the exact
bytes match before and after registry/index/chunk/raw reattestation. It never
opens the collector lock, calls KIS, reads credentials, or writes the cache.
Its immutable D:-resident manifest carries source hashes, all target coverage
and zero-coverage facts, source chunk references/hashes, and explicit
current-listing/non-PIT/non-ranking, unadjusted, corporate-action, and
session-finality limitations; it carries no raw rows, prices, volumes, account,
or broker facts.

The first stable panel is dataset
`sha256:09de29cfd619b331853dd2e9063315b84e2fb9397e49b238cc565bdf8ec964b7`
from index generation 187. It has 2,119 registry targets, 187 covered targets,
1,932 zero-covered targets, and zero quarantined conflict targets. It is a
development-coverage record only, not a PIT universe, adjustment qualification,
research split, target, ranking, training, model, Paper, or live input.

Claude's falsification-first review returned `supported-with-limits`. It
required index-byte rather than generation-only stability, no collector-lock
interference, target-wide quarantine for any conflict chunk, visible zero-
coverage facts, and a later date-based split plus independently qualified
target/cost contract. The strongest later kill test is past immutability across
panel generations: shared `(target, session)` fingerprints must stay identical
as collection advances.

Reason: a current mutable collector can safely supply a frozen local consumer
only when its source identity and limitations remain explicit, retryable, and
independent from collection progress.

## 2026-07-29 - Bound broad KIS D1 rate-limit recovery to one same client

Decision: after the broad KIS Paper `dailyprice` worker receives a
`rate_limited` result, it retains the one in-memory client/token and waits only
until the existing shared request gate is due once, inside the worker's existing
runtime. It then resumes normal breadth-first target selection. A second rate
limit, another shared stop, expired runtime, invalid cache, or storage floor
yields to the existing owner scheduler. The source-safe receipt carries only
the recovery attempt count, categorical outcome, and aggregate pages accepted
after recovery. The request-start pace, token-start guard, source scope,
trigger window, and duplicate-worker policy do not change.

Focused deterministic tests prove single-client reuse, one bounded worker wait,
second-rate yield, source-safe receipt contents, and the absence of account,
order, or live routes. A rebuilt-image 900-second real continuation accepted
818 pages over 417 chunks with zero new categorical failures; it did not
encounter a rate limit, so its recovery count was zero. That is sustained
progress evidence only, not a claim that KIS rate recovery has been proven or a
reason to widen the scheduler.

A later scheduler-owned run provided the bounded real recovery evidence: it
accepted 486 pages over 251 chunks, encountered two rate limits, retained the
same client for exactly one recovery, and accepted 50 pages after that recovery
before the second limit yielded. This supports the per-worker recovery behavior
only; it does not identify a universal KIS quota or justify a trigger-density
change.

Reason: the prior off-window rate-limit result left a real restart gap. A single
measured recovery removes that avoidable gap without creating a request flood,
unbounded retry loop, new broker surface, or scheduler platform.

## 2026-07-29 - Compare broad D1 panels by frozen shared-row fingerprints

Decision: add an offline comparison of two materialized broad KIS D1 panel
manifests. It reattests both frozen source snapshots, computes canonical hashes
only in memory for each shared target/session bar, and writes an immutable
external receipt containing dataset hashes and aggregate shared/mismatched
counts. Any shared-row mismatch makes the result `mismatch` and returns a
nonzero script status; it does not alter the cache, collector lock, or an
existing panel.

The first comparison reattested the generation-187 and generation-604 panels:
187 shared targets and 35,975 shared rows had zero mismatches. Tests cover equal
overlap, one altered shared bar, external-only output, retained worker-lock
bytes, and no network/credential/broker route. Claude CLI attempts returned no
review body before their turn limits, so this decision records
`review_unavailable`, not Claude endorsement.

Reason: expanding a mutable current-listing cache is useful only if a frozen
consumer can detect changed retained values. The comparison adds that narrow
lineage check without claiming provider correctness, PIT membership, corporate-
action semantics, session finality, or research readiness.

## 2026-07-29 - Postprocess broad D1 panels only after their collector exits

Decision: keep the materializer's existing two-index byte-stability contract
and attach one offline materialize-and-compare postprocess to the successful
exit path of the existing broad collector task. It does not add a second task
or collector, and it runs only after the Docker collector process has returned
zero. The postprocess writes a deterministic external source-safe receipt and
returns recovery exit `20` for index drift, incomplete full breadth, candidate
quarantine, coverage regression, unavailable continuity, or a shared-row
mismatch. It returns zero only when all current registry targets are covered,
the candidate is non-quarantined, generation-604 coverage is not reduced, and
every retained baseline row is part of a zero-mismatch overlap.

The host command is `uv run --offline`; it reads no `.env` or credentials and
calls no KIS, account, broker, order, or live route. It writes neither raw rows
nor prices, volumes, account facts, or model output. Its result is only a
frozen source-local coverage/lineage fact, not research promotion or a
collection-completion assertion.

Claude's falsification-first verdict was `supported-with-limits`. Its material
caveat was that a zero-mismatch intersection can hide missing coverage; the
full-breadth and baseline-coverage checks above make that caveat an executable
condition for this exact consumer without blocking the collector or another
lane.

Reason: a separate clock-based post-run task could race a long broad worker.
Sequencing the same offline consumer after the owner exits preserves the
existing cache writer boundary while producing a stable, recoverable snapshot
as soon as one is available.

## 2026-07-29 - Observe broad D1 chronology by target distribution, not one common-span gate

Decision: after a complete broad D1 postrun, retain at most one external,
candidate-generation-bound chronology observation with aggregate per-target
bar-count and calendar-span buckets plus source-state counts. It must reattach
the existing postrun, candidate panel, and generation-604 comparison before
writing. It records `recorded`, not `feasible`, and never computes a global
common-history threshold.

The current NAS registry is a current-listing, non-PIT survivor set and its
source-limited targets can remain structurally shallow. Intersecting every
target's history would let the shallowest such member define a misleading
research gate. The observation therefore stays a perishable source fact, not a
split, target, campaign, model, GPU, ensemble, ranking, PnL, Paper, or live
input. It is offline, aggregate-only, external to Git, and has no credential,
KIS, account, broker, order, or network route.

Claude's falsification-first verdict was `supported-with-limits`. Its caveat
was adopted directly: overlap equality already attests retained rows, and a
new chronology result should add only span distribution rather than an
eligibility-like boolean.

Reason: later research needs visibility into broad-cache depth without turning
current-listing coverage or source limitations into an accidental model
qualification rule.

## 2026-07-29 - Chain broad D1 chronology observation to a complete postrun

Decision: extend the existing broad-task exit chain by invoking the already
offline chronology observer only after a zero-exit `complete` postprocess. The
runner resolves the postrun receipt from the postprocess's one JSON result and
its SHA-256-derived immutable filename; it never discovers a mutable "latest"
artifact. The observer derives both panel paths from the receipt's verified
dataset hashes and reattests them before writing its aggregate-only external
observation.

If the observer returns its scoped recovery exit, the runner records a warning
but returns the successful postprocess result. This preserves the factual task
outcome while leaving only the observation eligible for recovery. The chain
adds no trigger, collector, cache mutation, KIS request, credential read,
network/broker route, model input, or research promotion.

Claude's falsification-first verdict was `supported-with-limits`. Its adopted
conditions are deterministic receipt derivation, no mutable-artifact lookup,
and a failure boundary that cannot mislabel a completed collection/postprocess
as a task failure.

Reason: an automatic, receipt-bound observer removes foreground polling and
keeps the next source-safe consumer attached to the stable cache-owner
boundary without converting an observation into a new collection gate.

## 2026-07-29 - Keep broad D1 collection eligible across the KST overnight gap

Decision: extend only the existing
`thericher-kis-paper-daily-broad-backfill` Task Scheduler definition to its
same 30-minute Tuesday-Saturday cadence across 00:15-23:45 KST. It remains one
named task with `IgnoreNew`, the existing 870-minute Windows limit, one cache
lock, one shared external request-control root, and the same postprocess only
after a successful collector exit. The installer registers or updates the task
definition but contains no task-start path. It creates no new task, route,
credential surface, account/order capability, or live behavior.

The first extended overnight window is an observational run. Its source-safe
facts are accepted-page progress, categorical-result count, lock outcome, and
whether a terminal collector exit reaches the existing postprocess boundary.
The pre-observation baseline at 2026-07-29 11:24 KST is mutable index
generation 4,946, 9,618 accepted pages, 110 cumulative target-local
categorical results, and one active owner. Restore the former daytime-only
trigger set immediately if there is evidence of more than one active owner.
Restore it after two consecutive added-slot collector runs each make zero
accepted-page progress because of the same shared rate/maintenance class.
Do not count a target-local `source_limited` result or one scoped retry as
that failure condition.

Claude's falsification-first verdict was `supported-with-limits`. Its required
same-task/`IgnoreNew` and postprocess-boundary conditions are preserved. Its
claim that the request gate would be per-process does not apply to the current
implementation: `KisPaperMarketDataRateGate` persists timing state in the
shared external control root. The ongoing one-second gate and 60-second
categorical backoff remain unchanged until a separate measured capability probe
justifies a recalibration.

Reason: the previous 07:15-20:45 KST trigger coverage left a measured restart
gap after a bounded worker exited. Extending the same task's eligible start
times improves sustained historical backfill without creating parallel KIS
traffic or weakening recovery semantics.

## 2026-07-29 - Bound fresh broad D1 workers to an eight-hour postrun cadence

Decision: change only the host broad-task runner's default inner collector bound
from 50,400 seconds to 28,800 seconds. The currently running 09:45 KST worker
is not stopped or modified. The existing task, 30-minute triggers, `IgnoreNew`,
cache lock, shared request gate, one-client-per-worker rule, 24,000-chunk cap,
and 870-minute Windows envelope remain unchanged. A fresh worker still reaches
postprocess only after its Docker collector exits zero.

Measured context: the one active owner accepted 21,543 pages over roughly
12 hours 35 minutes by 22:20 KST. The original bound would defer the next fresh
postrun until roughly 14:15 KST; the eight-hour bound allows its first
postprocess boundary around 08:15 KST without a parallel collector. This is a
data-collection/validation feedback calibration, not a provider-rate claim.

Claude's falsification-first verdict was `supported-with-limits`. Its adopted
kill test measures accepted pages per rolling 24-hour wall-clock, not active
minutes, because restart/token/index-reverification overhead is real. Revert to
50,400 seconds if the first calibrated cycle has zero accepted progress, a
shared auth/rate failure, no terminal postprocess boundary, a
`rate_limit_recovery_outcome` of `runtime_exhausted` caused by the shorter
bound, or materially lower rolling-24-hour page yield. The first postrun and
subsequent source-safe worker receipt decide retention; neither condition blocks
another correctly scoped Data or Paper action.

Reason: a long uninterrupted collector maximizes one-run duty cycle but delays
the stable snapshot needed by the active validation loop. An eight-hour bound is
a reversible compromise that keeps serial collection while making frozen
lineage evidence available materially earlier.

## 2026-07-29 - Trial strategy discovery before creating a durable research lane

Decision: begin Strategy Discovery as an invoked, bounded public-source
assignment rather than create `agents/strategy-research.md` immediately.
Existing Engine Research retains hypotheses, campaign contracts, CPU/GPU work,
backtests, validation, and model-side attribution. Strategy Discovery may hand
off only retrievable source identifiers, retrieval times, verbatim license text,
source-derived mechanism proposals, and the source's stated discovery/
evaluation or pretraining-corpus period and instrument scope. Engine Research
independently re-retrieves a proposal before it can become a hypothesis or
campaign; unknown or overlapping public-model provenance cannot support a
comparative or promoted result.

Claude's falsification-first verdict was `uncertain`. The policy's durable-role
precondition is not yet evidenced, and a separate role owning hypotheses or
kill tests would duplicate Engine Research. The adopted safeguards forbid it
from owning a queue, gate, model, data, benchmark, campaign, or broker route.
Its external source-safe receipt is evidence only. A failed source re-retrieval
or unconsumed handoff retires the trial; two consecutive goal boundaries with
independently re-retrieved handoffs consumed by Engine Research, including one
recorded source-hygiene rejection, are required before promotion to a durable
stateboard.

Reason: the project needs a repeatable way to discover genuinely new causal
mechanisms after several fixed D1 candidates were falsified, but a permanent
agent without demonstrated independent work would add process structure rather
than advance the feature/model research loop.

## 2026-07-29 - Named research tracks and temporary cross-track synthesis

Decision: keep Data, Engine Research, Execution, and Codex orchestration as the
only durable team lanes. Within Engine Research, dispatch rule/chart structure,
momentum-regime/cross-sectional, classical statistical/ML, and sequence/DL or
public-model benchmark work as separately bounded tracks under the same
campaign and trial-custody contract. Do not create one stateboard per method.

When two independently frozen candidates have aligned out-of-fold evidence and
comparable cost/availability assumptions, invoke Cross-Track Synthesis through
temporary Validation. It measures incremental net value, error dependence,
turnover, drawdown, and missing/stale behavior; it may return only
`no_combination` or one new ensemble-campaign proposal. It cannot tune members,
select weights, promote a model, or create a Paper route.

Claude's falsification-first verdict was `supported-with-limits`. It identified
the material missing boundary as evidence custody rather than more idea roles:
repeated trials on the same panel, split/holdout access, and cost-realism parity
need a shared append-only external registry. The adopted next improvement is a
source-safe campaign record keyed by contract hash, not a new manager or
Markdown ledger. Until it is implemented, historical research remains
non-promoting and may not claim quantified multiple-trial control.

For a post-cost comparative, ensemble, or paper-candidate claim, Execution
must independently reattest the same cost, latency, fill, and availability
assumptions. That parity evidence is not a manual approval or a blockage on a
separately scoped exploratory/paper action; it closes self-certification only
when a Research result is being interpreted as execution-feasible.

Reason: distinct mechanisms deserve parallel exploration, but treating each
model family as an independent permanent agent would duplicate contracts and
make ensemble selection less independent. The temporary synthesis boundary
preserves diversity testing without turning integration into another source of
in-sample tuning.

## 2026-07-29 - Repair target-free representation before CUDA dispatch

Decision: do not dispatch the first Norgate target-free CUDA batch under its
initial r4 contract. Claude's falsification-first verdict was `uncertain`:
the original 22-index gap allowed 40-return diagnostic windows to overlap the
development input, a causal terminal mask could become a next-step predictor,
and numeric per-architecture losses would leave a de facto selection
leaderboard. The static 523-symbol panel also remains full-span survivorship
conditioned and adjustment-unverified, so its scope stays explicitly
non-promoting.

The repaired r5 contract uses a 40-index non-overlap gap, masks only interior
positions with both observed left and right context, uses bidirectional
GRU/LSTM, symmetric temporal convolution, and noncausal compact attention, and
records only finite-loss facts. CUDA enables deterministic algorithms, disables
TF32 and cuDNN benchmarking, and records the configuration. Direct source rows
and value arrays remain unretained, but learned external weights are now
truthfully treated as restricted derived artifacts that may encode source
information.

Reason: this preserves a useful GPU representation plumbing exercise without
relabeling it as a forecast, hiding temporal overlap, or making architecture
selection available by artifact inspection. The r4 CPU smoke and its incomplete
preflight contracts remain scoped non-promoting evidence; only a repaired
contract may reach the named CUDA decision boundary.

## 2026-07-29 - Batch target-free diagnostic forwards after the r5 CUDA fault

Decision: treat r5 as an incomplete CUDA preflight, not a completed four-model
batch. Its CPU GRU smoke completed, but the compact-attention diagnostic forward
attempted all 75,835 rows at once and CUDA returned an invalid kernel
configuration error. The run wrote no aggregate batch summary, registry outcome,
ranking, selection, Paper action, or PnL result.

The r6 recovery keeps the same fixed objective and architecture specifications,
but evaluates diagnostics in deterministic 4,096-row chunks and aggregates only
an in-memory finite check. A focused test fixes the 19 resulting bounded ranges.
The r5 partial per-architecture artifacts remain external non-promoting failure
evidence; they are not reused as a winner or a batch completion shortcut.

Reason: bounded diagnostic inference is a runtime feasibility repair, not a
parameter change or post-hoc model tuning. It prevents one architecture from
receiving a different diagnostic geometry while preserving the source and
selection boundaries established for r5.

## 2026-07-30 - Complete target-free representation plumbing and require source conformance

Decision: accept r6 as completed non-promoting representation plumbing. Its
external contract `sha256:ef3745da...a4aacc2` completed a CPU GRU smoke and the
fixed CUDA GRU/LSTM/temporal-convolution/compact-attention batch, with aggregate
summary `sha256:1f91c4d3...2a4481` and registry outcome
`sha256:e011f1d6...0b65bd`. Safe numeric weights stay outside Git. r5 remains
immutable incomplete preflight evidence; r6 neither reuses it as a winner nor
persists a numeric comparison surface.

The first Strategy Discovery handoff pins official Chronos, TimesFM, and
Uni2TS/Moirai code sources under the external artifact root. It records their
repository license text but does not infer checkpoint rights, financial-domain
pretraining provenance, causal availability, or KIS/Paper eligibility.

Claude's falsification-first verdict was `supported-with-limits`: a static,
adjustment-unqualified Norgate panel alone cannot prove that an input/output
contract reconstructs from KIS, and full-panel target-free weights cannot enter
a later held-out label experiment. Before any causal Norgate breadth campaign,
build an offline source-parameterized Norgate/KIS D1 metadata-conformance
contract. It must compare only source semantics and field availability, keep
survivorship as a declared limitation, and create no labels, costs, rankings,
models, PnL, Paper input, or cross-source row pool.

Reason: this attacks the actual transfer risk before spending a new training
budget. A conformance mismatch is useful scoped evidence, not a global hold or
an excuse to manufacture GPU work.

## 2026-07-29 - Contain the challenged QQQ/SPY overnight/intraday state as CPU plumbing

Decision: retain exactly one Docker CPU smoke for a newly proposed QQQ/SPY D1
directional-count state rule, but prohibit a full validation, GPU run, model
selection, ensemble, KIS Paper use, and order consequence. The rule consumes
only 21 phase-local completed KIS D1 bars: it compares the count of positive
intraday moves with the count of positive prior-close-to-open moves across 20
observations, decides after completed session `t`, enters at `t+1` open, exits
at `t+2` open, and uses a two-session stride. Its fixed comparators are flat,
always-long, and previous-bar-direction. There is no fit, normalizer, threshold
sweep, or training.

The first proposed cumulative-growth version was discarded after Claude showed
that it collapsed to a momentum expression. Claude's second falsification-first
review of the non-telescoping count version was `unsupported`: the mechanism
does not match its open-to-open payoff, unadjusted daily OHLC can contaminate
gap counts, and the existing holdout has already been used by prior research.
The CPU smoke therefore proves only source reattachment, causal action timing,
local-paper replay, external artifact isolation, and independent validation.
It has source-safe precommit
`sha256:dc37edf85605ba78171b006f0c35dd27fcb4355442c9d50d5a3d154a462dd5a1`
and independently reattested summary
`sha256:3fde8e7efd4bbbf78dbe8603d5635036db01b16a5691599994e46b01e030a8ca`.

Reason: a weak hypothesis may verify one bounded research path, but it must not
consume GPU or acquire a false performance meaning merely because its mechanics
run. The next D1 research opportunity should prefer a fresh forward stream and
a new independently challenged causal contract over another variation on the
already-used QQQ/SPY validation slice.

## 2026-07-29 - Separate QQQ/SPY D1 forward validation data from prior history

Decision: create a dedicated KIS Paper daily forward cache for exactly
`QQQ/NAS` and `SPY/AMS`, retaining only completed rows strictly after the
2026-07-24 frozen boundary. It has its own D: cache, index, immutable external
receipts, target-local recovery, and 06:55 KST Tuesday-Saturday schedule. It
does not merge into the fixed QQQ/SPY catalog, NAS forward cache, Norgate,
Tiingo, or broad current-listing cache.

The cache's preflight is network-disabled, read-only, and credential-free. It
returned `collection_required` with source-safe receipt
`sha256:c35d30de11d2d12dddf60ccf43d0738c1474ad88ba2e6c4b8ef8395c5e14ade4`.
When the broad Data worker was running, the first guarded invocation wrote only
`unavailable/shared_dispatcher_busy`, with source-safe receipt
`sha256:227a65afdf8e10f335fa7925ea94d7fe6d1707da927d50899f50e15ef78f86db`.
That is a pair-cache `resume` fact, not an authority hold or an assertion about
provider limits. No credentialed collection was started while the shared
dispatcher was occupied.

The credentialed route is allowlisted to the KIS virtual-paper daily endpoint
and those two symbol/exchange pairs. It injects only KIS Paper market-data
credentials with `THERICHER_MODE=off`; it has no account, position, quote,
order, model, GPU, or live route. Focused tests cover source separation,
completed-session filtering, duplicate preservation, target-local recovery,
external artifact placement, and preflight/schedule isolation. The Claude
falsification-first drift-check request timed out without a body, so this
records `review_unavailable`, not reviewer endorsement.

Reason: untouched out-of-time data must keep a distinct source identity from
the already-consumed historical pair, while a busy broad collector should yield
only this new cache's work instead of delaying independent collection or
creating an unmeasured parallel request path.

## 2026-07-30 - Audit KIS D1 adjustment semantics before extending a sidecar

Decision: accept the completed offline Norgate/KIS D1 metadata conformance
receipt `sha256:f57ff545...10d7f60` as a scoped mismatch, not as source
transfer evidence. Both panels expose completed D1 OHLCV metadata, but their
adjustment and symbol-identity declarations conflict; corporate-action,
timezone, and gap semantics remain unknown. The interface is therefore
source-parameterized only and remains ineligible for model, ranking, PnL, or
Paper use.

Claude's falsification-first verdict on a proposed six-symbol Tiingo
corporate-action sidecar was `unsupported`. Its key findings were that the
documented standing Tiingo scope does not include the six-symbol NAS panel, a
KIS-only sidecar would add rather than resolve the existing dual-source
conflict, and a cheaper offline test can falsify the central `MODP=0`
assumption first. The next bounded package therefore checks fixed split-event
pairs in the existing KIS cache entirely in memory. It persists only
per-symbol categorical signature results and aggregate status, never dates,
prices, returns, rows, credentials, requests, or cache changes.

Reason: evidence about the provider's actual cached adjustment behavior is more
valuable than widening an external-data dependency before knowing whether a
retrospective event mask has a valid premise. A positive split signature only
supports the narrow declaration; it cannot qualify Norgate, resolve
survivorship, make sources interchangeable, or authorize training or Paper
behavior.

## 2026-07-30 - Preserve narrow KIS split evidence and census its complement

Decision: accept the completed offline KIS D1 split-signature receipt
`sha256:3930a95a...05176e` as narrow support for the cached `MODP=0`
declaration. Its five fixed AAPL/AMZN/GOOGL/NVDA pairs all have a categorical
large split signature; the artifact retains only source/contract hashes,
per-symbol counts/statuses, and non-eligibility policy. It contains no rows,
values, returns, dates, labels, credentials, network, KIS, broker, or live
activity.

Claude's result review was `supported-with-limits` for the narrow observation
and `unsupported` for a retrospective-label exclusion adapter. The audit cannot
detect dividend adjustment, uniform restatement, unknown corporate actions, or
identity issues, and the adapter would not change the panel's otherwise
unqualified status. Claude recommended a same-threshold complement census over
every retained adjacent D1 pair and all six symbols. Adopt that next objective,
with unexplained large moves treated only as categorical observations.

Do not adopt Claude's proposed aggregate-order change: the fixed audit contract
deliberately makes an unavailable or invalid required pair aggregate
`inconclusive`, never a partial falsification. That fail-closed rule is an
explicit objective boundary, not an accidental preference for success.

Reason: the complement census creates an actual falsifier for a cheap source
semantics check without inventing label plumbing, adding a provider, or
mistaking a five-event spot check for full historical qualification.

## 2026-07-30 - Close D1 census and prioritize the existing Paper lifecycle

Decision: accept the symbol-aware v2 discontinuity census receipt
`sha256:0f92a377...b93edb` as scoped source-semantics evidence only. It records
one aggregate AAPL large discontinuity outside the five predeclared pairs and
zero for the other five streams. No event location, value, return, date, raw
row, network request, credential, broker body, label, model, PnL, or Paper
action is retained. The category neither proves an adjustment defect nor
qualifies the historical panel.

Claude's verdict was `uncertain`: the static split list may be incomplete,
array adjacency is not calendar continuity, and the previous exclusion
implementation incorrectly discarded symbol identity. Fix the code by matching
`(symbol, before_session, after_session)` and version the census contract to
v2; do not infer a cause or add another label/corporate-action adapter. The
current result remains an AAPL-only aggregate after the fix.

Claude correctly noted that the historical D1 panel has no eligible consumer
while the existing KIS Paper virtual canary has never completed a submit/cancel/
reconciliation lifecycle. Adopt that independent next objective under standing
Paper authority. It must rely only on the existing current QQQ freshness gate,
persist intent before side effects, never retry an ambiguous exact intent before
read-only reconciliation, and retain only source-safe lifecycle categories. It
does not change strategy, sizing, historical data, model eligibility, Paper
authority, or any live route.

Reason: this advances the actual private Paper execution loop without making
historical data qualification a false precondition. It also breaks the emerging
pattern of adding audit artifacts that nothing downstream can safely consume.

## 2026-07-30 - Make exact Paper unknown recovery submit-proof and immutable

Decision: retain the dedicated exact unknown-run reconciliation entrypoint, but
give it an explicit read-only recovery branch that cannot fall through to the
generic submit/cancel path even if its second state read is no longer an
ambiguity phase. Reconciliation writes a new immutable external receipt that
links to the primary evidence hash and preserves the prior safe phase/reason;
it never overwrites the original failure evidence.

Claude's falsification-first review was `supported-with-limits`. It identified
the generic runner's second state read and fixed evidence path as the real
load-bearing risks, not the initial phase check alone. Focused tests now prove
that a substituted `intent_recorded` state raises before any transport request,
and that recovery issues no non-token POST, no buy/sell/cancel route, and leaves
the original evidence bytes unchanged.

The exact private Paper run `canary-20260729T143501313369Z` then completed this
read-only recovery. Original evidence remains
`sha256:2e612d02224e768c1f16aeff6a9874bc06cbf549048964795bac8370fae1858c`;
the new receipt is
`sha256:c3ec1489d61e23ee82b2986355fafa17298be53c7fb58fe130c6a02103f83b90`.
It remained `outcome_unknown/reconciliation_unresolved`, made no submit,
cancel, modify, replacement, or live call, and does not count as the pending
fresh QQQ scheduler lifecycle.

Reason: exact unknown outcomes need recoverable evidence without mutating their
causal record or allowing a recovery tool to become an accidental order retry.

## 2026-07-31 - Research method tracks remain one lane with disposable synthesis

Decision: retain one durable Engine Research lane. Technical/chart,
momentum/regime/cross-section, classical ML, and sequence/DL/public-model work
remain bounded track packages inside that lane rather than separate agents,
stateboards, goals, or promotion authorities. Each assignment expires with its
bounded result or at the next company-goal boundary; continuation requires a
fresh Engine Research package and evidence reference.

Cross-Track Synthesis remains a temporary Validation assignment. It may run only
when at least two independently frozen candidates predeclare identical
out-of-fold row keys, completed-bar/source-adjustment semantics,
decision-to-execution availability/latency, cost/fill model, and temporal split.
Any mismatch returns `no_combination`; the assignment cannot repair alignment,
retune members, select a winner, create a Paper action, or persist a queue.

Claude's falsification-first verdict was `supported-with-limits`. It identified
undefined expiry and alignment as the main ways a useful track portfolio could
quietly become permanent parallel teams and a post-hoc ensemble-selection path.
The explicit expiry and exact compatibility tuple above resolve that limitation.

Reason: breadth is useful only when every method can be independently falsified
and later compared on the same causal contract. This preserves parallel research
without turning organization itself into a strategy or an authority path.

## 2026-07-31 - Research steward and track topology

Decision: retain Data, Engine Research, Research Steward, and Execution as the
durable lanes. Keep technical/chart, momentum/regime, classical ML,
sequence/DL/public-model, and portfolio/allocation work as parallel tracks
inside Engine Research, not separate stateboards. Research Steward owns only
the cross-track GPU appointment and sealed-evaluation family/allocation record.
Strategy Discovery, Validation, Cross-Track Synthesis, Infra, and Throughput
Review remain invoked roles.

Reason: model-method stateboards would duplicate queues while competing for one
GPU and the same finite evaluation evidence. The shared scarce-resource record
needs durable ownership across objectives, but it must not become a manual
approval, model-selection, or Paper-trading gate. Claude's 2026-07-31
falsification-first review was `supported-with-limits`: it required explicit
GPU arbitration, holdout-spend lineage for synthesis proposals, and a clear
portfolio-to-Execution contract seam.

## 2026-07-31 - Require clean cancellation evidence for QQQ lifecycle completion

Decision: retain the installed QQQ session and scheduler unchanged, but make
the independent offline validator fail closed when interpreting its
`canary_completed` record. Completion now requires an explicitly Paper-only
canary payload, terminal `cancelled` phase, and `clean` reconciliation. It
rejects submitted, ambiguous, unresolved, unknown future, absent-route, and
non-Paper variants. Rejection preserves scoped recovery evidence; it neither
submits nor replaces an intent.

Claude's falsification-first verdict was `supported-with-limits`. The adopted
limit is explicit: this validation proves only that the persisted source-safe
record is self-consistent, not that a venue independently confirms the
cancellation. A filled or rejected outcome remains non-completion for this
cancel-after-submit canary, and any exact ambiguous intent keeps its existing
reconcile-first recovery path. Focused validator and full QQQ-path tests cover
the terminal allowlist and explicit Paper-route boundary without a KIS call,
credential read, scheduler mutation, or Paper intent.

Reason: a session status label alone is insufficient completion evidence. The
strict conjunction prevents a false lifecycle claim while preserving the
existing no-duplicate, reconcile-first recovery contract.

## 2026-07-31 - Make clean parallel tests the routine goal-boundary authority

Decision: replace the routine full serial `pytest -q` goal-boundary hold with
changed-path serial tests plus the existing clean-root,
file-distributed `run_parallel_tests.ps1 -RequireCleanTempRoot` full-suite
command. The authority also includes Ruff and both Compose configurations. A
nonzero result, retained current-run temp root, unexpected test/skip cardinality,
or worker-count divergence is verification failure. This changes no KIS, data,
model, Paper-order, or live path.

The completed serial baseline is `1769 passed, 14 skipped` in 806.07 seconds.
The same suite then matched with repeated four-worker and one eight-worker
isolated runs. The runner has a unique short temp root, file-level distribution,
explicit clean-root mode that prunes only verified helper roots older than 24
hours, and a test-backed direct propagation of pytest's exit status. Full serial
`pytest -q` remains a weekly and material live-route or
execution-recovery compatibility diagnostic; it does not hold an otherwise
verified private Paper objective or another lane.

Claude's falsification-first verdict was `supported-with-limits`. Its adopted
conditions are the completed serial anchor, clean-root assertion, exit-code
contract, cardinality comparison, worker-count rotation, and conservative
changed-path serial selection. Cross-file serial-order bugs remain possible,
which is why the periodic diagnostic remains explicit rather than being
silently retired.

Reason: a repeatedly timing-out validation command should not masquerade as
authoritative proof or slow every bounded objective when the same suite has
measured isolated parallel evidence. The retained serial diagnostic preserves a
separate compatibility signal without foreground-blocking routine progress.

## 2026-08-01 - Make timeframe and observation window a frozen research axis

Decision: add timeframe and observation window to every Engine Research
campaign contract. A campaign either declares one fixed horizon or freezes a
finite matrix before outcomes are read. The initial intraday seed menu is 1m
`15/30/60/90/120/180` bars, 5m `3/6/12/18/36` bars, and 10m `3/6/12/18` bars;
1h and 3h belong only as explicit cells under the same contract or as a new
campaign. This is a breadth mechanism, not automatic permission to run every
combination or tune the best observed window.

Each matrix shares one family-level compute/selection budget, records its cell
count, uses a predeclared minimum complete-causal-observation and block-aware
effective-sample rule, and reports a fixed `1.0x/1.5x/2.0x` cost-sensitivity
band. Development or out-of-fold evidence can screen cells, but any survivor
must receive a new lineage and a later or disjoint replication/depth contract
before sealed evaluation, ensemble use, or Paper consideration. Data-scarce or
target-free window studies remain ledgered as non-promoting.

The prior data-backed intraday architecture screen used only one 90-minute
window, so it was not a window comparison. Its LSTM, causal-TCN, and compact
attention replay outcomes did not create a selected candidate; no claim of a
profitable intraday engine follows from it.

Claude's falsification-first review was `supported-with-limits`. It required a
shared budget rather than per-cell budget multiplication, effective-sample
accounting for overlapping windows, a cost band, and one-shot sealed-set family
custody. These limits are now part of the Engine Research and Research Steward
contracts.

Reason: window length materially changes signal horizon, sample dependence,
turnover, and cost exposure. Treating it as an invisible constant left the
research too narrow; treating it as an unbounded grid would overfit the short
intraday history. The frozen, budgeted matrix makes the comparison useful while
preserving a later independent falsification path.

## 2026-08-01 - Run the intraday window probe independently of the QQQ canary

Decision: the scheduler-owned QQQ Paper lifecycle is an Execution observation,
not a dependency for separately frozen offline Research. Start a bounded,
non-promoting QQQ 1m window-sensitivity preflight now, using the retained
20-session KIS private catalog and frozen `30/60/90/120/180` completed-bar
cells. The QQQ scheduler, decision table, sizing, freshness budget, and Paper
route remain unchanged.

The preflight uses the existing chronological `10/1/9` session geometry,
session-local histories and targets, development-only normalization, and
session-block effective-sample accounting. It must run a deterministic
session-block label-permuted null before interpreting the real matrix. Model
capacity is normalized by fixed optimizer-step count per cell; short windows
cannot receive more updates merely because they yield more overlapping rows.
The result exposes only aggregate metric distributions and its
`structure_present` or `no_structure` gate, never a ranked window or model.

CUDA is conditionally eligible only when the real predeclared structure
statistic exceeds the block-permuted null threshold. A null result terminates
the family without manufactured GPU work. A positive gate still creates only a
descriptive external LSTM/causal-TCN/compact-attention screen; it cannot select
a winner, form an ensemble, open sealed evaluation, make a profitability claim,
or change Paper behavior. Any future candidate needs later or disjoint
replication custody.

Claude's falsification-first verdict was `supported-with-limits`. It required
per-cell training-capacity normalization, a CPU structure gate before CUDA,
strict session reset and development-only normalization, one-shot comparison
data custody, aggregate-only reporting, and the label-permuted block null as
the strongest kill test. The contract adopts all six limits.

Reason: serializing Research behind a scheduler-owned Paper observation leaves
the engine idle for no causal reason. The bounded null-first experiment advances
the specific fixed-90-bar uncertainty without pretending that 21 sessions can
select or promote a profitable engine.

## 2026-08-01 - Close the QQQ 1m window family on its predeclared null

Decision: accept the completed external
`kis-intraday-window-matrix-v1/qqq-20260623-20260721-window-null-r1` result as
the terminal outcome of the frozen `30/60/90/120/180`-bar family. Its real
aggregate Brier spread was `0.000233701152146`, below the deterministic
session-block-permuted null P95 of `0.000627602629947`; the result is therefore
`no_structure`. No window, model, ensemble, profitability claim, Paper input,
or CUDA appointment is selected.

The result retains no raw data or checkpoint and writes only source-safe
precommit/summary evidence under `D:\\thericher-v2\\model-artifacts`. Its
comparison sessions are spent for this family: they cannot be reused to retune
a lookback or reopen a GPU screen. A later intraday candidate must have a
separate hypothesis and later or otherwise disjoint evaluation contract.

Reason: the predeclared null test failed to distinguish window-length variation
from session-level noise. Closing it avoids using the idle GPU to amplify an
unsupported choice while leaving independent Engine Research, Data, and KIS
Paper work active.

## 2026-08-01 - Establish the pure target-position policy foundation

Decision: implement one pure product-graph segment that receives only an
already-computed opportunity eligibility fact, caller-frozen configuration,
explicit `1m/5m/10m/1h/3h` `ModelPrediction` evidence, and current exposure.
It produces a model-side `TargetExposureProposal` with a categorical reason.
It has no default alpha, feature/data source, weight, network, credential,
KIS, account, broker, order, or model-selection behavior. Incomplete, stale,
duplicate, misaligned, future, ineligible, and conflicting inputs become
categorical abstentions rather than a hidden fallback decision.

The existing receipt and `local_paper` preparation bridge remain the only
tested downstream connection. Execution continues to own risk, quantities,
cash, durable intent, and broker behavior. This establishes product plumbing,
not a strategy, profitable model, ensemble, Paper action, or CUDA campaign.

The required Claude drift invocation exceeded its bounded timeout and returned
no verdict. It is recorded as `review_unavailable`, not as agreement or a
reason to defer this reversible no-I/O foundation.

Reason: the QQQ scheduler wait should not leave the core target-position engine
unimplemented. A caller-configured, fail-closed proposal boundary lets later
simple and learned experts share one execution-safe shape without prematurely
choosing an alpha model or widening broker behavior.

## 2026-08-01 - Build causal multi-timeframe momentum evidence before replay

Decision: add one no-I/O adapter from a caller-owned, completed KIS-private 1m
session to explicit `1m/5m/10m/1h/3h` `MomentumModel` predictions. Every expert
has a caller-frozen lookback and threshold; the adapter filters bars at its
declared `as_of`, anchors resampling to the explicit session, requires the last
expected completed bucket, and returns a categorical input condition instead of
using an older incomplete bucket. It feeds the existing pure target-position
policy only; it does not select a model, read credentials, call KIS/network,
write raw data/checkpoints, create an order, or use GPU.

The first real local-cache smoke on QQQ 2026-07-21 built all five predictions
and observed `sell/sell/buy/sell/sell`, so the policy correctly emitted
`expert_conflict` / `abstain`. This is structural evidence, not a trading or
profitability result.

Next, run one exact 20-session local-paper consensus replay with the frozen
expert specs, policy configuration, 19:30Z decision time, next-minute entry,
30-minute forced exit, one-share sizing, and flat/time-matched always-long
comparators. Do not tune any dimension after its results are seen.

Reason: before a multi-timeframe policy can be evaluated, every model input must
be built causally from the same KIS-shaped bar stream. The smoke proves the
product path can abstain on genuine disagreement rather than manufacturing a
trade while the independent QQQ scheduler waits.

## 2026-08-01 - Keep the first QQQ consensus replay descriptive

Decision: accept the fixed 20-session QQQ consensus replay as completed
product-path evidence only. Its external precommit and aggregate summary are
under `D:\thericher-v2\model-artifacts\research\kis-intraday-multitimeframe-consensus-replay-v1\qqq-20260623-20260721-consensus-r1`.
The run used causal completed-bar evidence, the existing receipt-to-
`local_paper` preparation path, one-share local-paper next-bar fills, and
in-memory terminal replay. It retained neither raw bars nor fill events and
did not read credentials, call KIS/network, submit a broker order, write a
checkpoint, alter the QQQ scheduler, or touch live behavior.

The frozen policy entered only two of the twenty sessions. Its aggregate
after-cost result and the all-session always-long total are not evidence that
the gate selected profitable sessions: the two consensus trades share the
same entry, exit, quantity, and local-paper cost mechanics as the matching
always-long trades, while the named comparator spans all twenty sessions.
Do not tune any replay parameter or promote a model from that contrast.

The required Claude command exceeded its bounded time limit, so this decision
records it as `review_unavailable` and does not rely on a Claude verdict. The
next independent, no-GPU package must write a fresh immutable precommit for an
equal-count session-subset null diagnostic. It may explain the current
selection effect but cannot establish a candidate; a later or disjoint
replication is still required before any comparative or Paper-input claim.

Reason: the replay successfully proves the causal product path and local-paper
replay invariants, but a two-trade selected subset versus an all-session total
cannot distinguish skill from a small sample of favorable sessions.

## 2026-08-01 - Close the QQQ consensus selection family without promotion

Decision: accept the immutable external
`kis-intraday-consensus-selection-null-v1/qqq-20260623-20260721-null-r1`
diagnostic as the completion of the first QQQ consensus interpretation family.
It reattached the exact baseline summary and precommit, reproduced its complete
in-memory local-paper replay digest, and enumerated all `190` equal-count
two-session subsets. The observed one-sided subset-null value was about
`0.1684`; the fixed policy generated only two round trips against the
predeclared minimum of `30` for any follow-up. Its categorical result is
`selection_unqualified`.

The diagnostic retained no raw prices, fill events, decision mask, or
per-session PnL. It read no credential, called no KIS/network/broker path,
used no GPU, altered no scheduler, and creates no winner, tuning pass,
ensemble, sealed evaluation, profitability claim, or Paper input. The baseline
and null artifacts are immutable; later or disjoint sessions require a fresh
candidate/replication contract rather than reusing this family.

Reason: equal-count comparison distinguishes the selected two-session subset
from its all-session total, but the observed sample is too small to support a
model claim. Closing the interpretation avoids false optimism while allowing
the independent target-exposure sizing foundation to proceed.

## 2026-08-01 - Separate pure allocation from model selection and execution

Decision: add `target-exposure-allocation-v1` as the small model-side stage
after an existing `TargetExposureProposal`. It is long-only and receives only
caller-owned current symbol/portfolio exposure, available capacity, portfolio
and per-symbol caps, bounded confidence/risk multipliers, input status, and an
injected decision timestamp. It first applies the two multipliers to the
already-proposed entry target, then caps only the resulting increase by the
declared headroom. It has no default target, data read, network, credential,
KIS, broker, order, artifact, or GPU behavior.

Unqualified, stale, future, or internally inconsistent allocation facts yield
an abstaining no-increase proposal. Exhausted capacity or a scaled target below
the current symbol exposure yields a hold, never an accidental reduction. A
fresh upstream `reduce` or `exit` passes through allocation-capacity faults;
an expired source proposal still abstains. The allocator is a snapshot
calculation rather than a portfolio reservation: a caller serializes multiple
allocations and refreshes exposure, while Execution independently checks its
own capacity, risk, and order quantization.

Claude's falsification-first review was `supported-with-limits`. The implemented
contract adopts its injected-clock, fixed scale-then-cap, long-only,
exit-preservation, and caller-serialization caveats. The new direct local-paper
composition test also revealed and corrected an eager `research`/`execution`
import cycle by deferring KIS-only research decision imports until their KIS
preparation function is called. No broker semantics changed.

Reason: separating target selection from capacity sizing matches the product
graph, makes later learned allocation testable against a deterministic baseline,
and avoids letting a research-side convenience layer masquerade as execution
authority.

## 2026-08-01 - Qualify the local Norgate trial only for offline source research

Decision: accept the host-only three-case Norgate daily capability receipt at
`D:\market_data\us_equities\norgate_trial\daily_capability_probe\probe=20260801T152000Z-norgate-trial-daily-capability-r1`
as `qualified_for_offline_research`. Its frozen current/member-change/former
cases confirmed date-indexed membership, major-exchange-listing, unadjusted D1
OHLCV field presence, and capital-event marker field availability through
Norgate package `1.0.77`; the aggregate receipt is
`sha256:8a6433a5aa410d3dc6c72077e05f346776348aed76e3b34a42fb55b7ae1d908d`.

The receipt is deliberately narrower than a PIT or model qualification. Vendor
membership availability time, price-adjustment semantics, and corporate-action
marker completeness remain unknown. It retains no raw source row, price, model,
GPU artifact, credential, KIS request, broker behavior, ranking, or Paper input.
The source namespace is structurally `offline_research_only`; every model, GPU,
ranking, PnL, Paper, and live eligibility flag remains false.

Claude's falsification-first direction check was `supported-with-limits`: bind
the local database build, recheck the frozen former-member case at runtime, and
do not infer point-in-time availability from date-indexed field values. The
implemented precommit/receipt and pure future-consumer outline adopt those
limits. A later date-indexed D1 pilot must have its own frozen source scope and
must not turn this capability receipt into a promotion shortcut.

Reason: this establishes the smallest reproducible local source boundary needed
to replace a static-survivorship assumption with an explicit date-indexed
experiment, while keeping the active KIS Paper graph and all live authority
unchanged.

## 2026-08-01 - Materialize only the three-case date-indexed Norgate D1 pilot

Decision: accept the fresh precommitted pilot at
`D:\market_data\us_equities\norgate_trial\daily_pilot\pilot=20260801T161934Z-norgate-trial-daily-pilot-r2`
as `qualified_for_offline_research`, linked to capability receipt
`sha256:8a6433a5aa410d3dc6c72077e05f346776348aed76e3b34a42fb55b7ae1d908d`.
The pilot manifest is
`sha256:7c81f09ad34151acb3896ef7f4cf22cadceedfb2992ac9241578a64db54fd264`.
It retained separate external D1, membership, and listing files for AAPL (10
aligned rows), PLTR (8 aligned rows and one membership transition), and AAL
(10 aligned rows), all bound to Norgate package `1.0.77` and the same local
database metadata fingerprint as the capability receipt.

The pure loader exposes completed `Bar`s and state only at an exact declared
source date. It rejects missing or cross-file date mismatch and does not accept
a static-current membership/listing substitute. Raw rows stay solely under
`D:\market_data`; Git and the manifest retain hashes, aggregate coverage, and
limitations only. It has no KIS, credential, network-provider, Docker-provider,
model, GPU, ranking, PnL, broker, or Paper behavior.

Claude's `supported-with-limits` review is incorporated as a source limitation,
not a new hold: this proves date-indexed field alignment in the current local
database build, but not point-in-time availability. The simplified r2 contract
keys rows only by provider ticker strings rather than overstating a current
`assetid` roundtrip as historical identity. Adjustment and corporate-action
semantics remain unknown. On any unqualified source-contract response its
manifest now retains the failing case, aggregate counts, and first divergent
date without retaining raw rows. The pilot is never a model or Paper promotion
path; the next recovery fact is to freeze a separate campaign only after those
assumptions are independently qualified.

Reason: the bounded pilot replaces an implicit static-list assumption with a
tested, source-date-aligned loader while preserving the distinction between
useful data plumbing and causal research evidence.

## 2026-08-01 - Add a pure causal multi-timeframe sequence-window contract

Decision: add `causal-multitimeframe-sequence-window-v1` as one reusable,
in-memory Engine input for caller-supplied `1m/5m/10m/1h/3h` completed `Bar`
sequences. Every caller declares its own positive lookback per timeframe and
one UTC cutoff. The contract sorts deterministically, preserves the selected
tail and each completed-bar end, requires a single cross-timeframe
symbol/market identity, and rejects incomplete, future, duplicate,
non-contiguous, insufficient, or mismatched inputs. Each timeframe's latest
bar may end before the cutoff only when it remains within that timeframe's own
duration; this allows ordinary decision times without pretending all timeframes
close together.

The function is intentionally only structural and has no provider, calendar,
KIS, credential, network, model, target, artifact, PnL, local-paper, or broker
behavior. Its metadata contains counts and timestamps only. It neither makes a
window a model campaign nor makes the current Norgate pilot a training input.
Session segmentation, resampling, source finality, and data-vintage/PIT truth
remain Data-owned upstream responsibilities.

The first Claude CLI response was discarded as context-invalid because it
referred to an unrelated path. The self-contained rerun was
`supported-with-limits`: it required the explicit cross-timeframe identity
check, cutoff-lag semantics rather than a global equality rule, and a stated
continuous-segment/data-vintage limitation. These changes are applied. The next
recovery fact is that a real multi-session consumer must add a calendar-aware
segmenter rather than fill gaps or relax structural validation.

Reason: model families need one causal, testable way to receive varied lookback
windows before a later frozen campaign can compare rule, classical, sequence,
or attention hypotheses without hidden timestamp semantics.

## 2026-08-01 - Keep the Tiingo three-ETF D1 control source-local and descriptive

Decision: accept the immutable Tiingo raw-D1 snapshot
`us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1` and
its `tiingo-etf-d1-cpu-baseline-v1` external precommit/summary as one bounded
offline control. The source covers SPY, QQQ, and IWM independently, uses raw
OHLCV plus event markers only, and keeps all provider rows on D:. The collector
and receipt expose only hashes, aggregate coverage, and categorical source
facts; they never expose the token, request URL, raw rows, KIS, Norgate, broker,
or live behavior.

The frozen control uses trailing raw-close `5/20/60` features available through
completed day `t`, a 70/30 chronological split with a 61-session purge,
next-session open-to-close direction, a fixed `5/10/20`-bp round-trip cost band,
always-flat and simple momentum baselines, and a feature-side-only discontinuity
kill test. Known event windows are excluded retrospectively. The completed result
leaves all evaluated validation momentum cells below flat across the band; SPY and QQQ
60-session validation cells are `input_unavailable` because the event mask
leaves fewer than fifty observations.

Claude's self-contained falsification-first review was `supported-with-limits`.
It required the target-day discontinuity check to stay out of feature filtering,
the trailing-return dependency to use `L+1` price sessions, the event scope to
remain explicitly retrospective/descriptive, and each validation cell to meet
the predeclared sample floor. The implementation and receipt reflect those
limits; cross-ETF agreement is not treated as independent replication.

No model is selected, no GPU appointment is made, and no Paper/runtime feature
or profitability claim follows. A new daily campaign must freeze a distinct
hypothesis and source interpretation; it cannot retune the observed matrix,
weaken the event mask, or blend Tiingo with KIS/Norgate rows.

Reason: the control proves a reproducible source-separated daily research loop
and rejects a simple after-cost baseline without letting an offline source or a
negative result turn into a general data or execution gate.

## 2026-08-02 - Keep Tiingo D1 sequence breadth descriptive and source-local

Decision: accept exactly one Tiingo SPY/QQQ/IWM D1 sequence breadth family under
`D:\thericher-v2\model-artifacts\research\tiingo-d1-sequence-breadth-v1`.
It reattests immutable source snapshot
`us_equities.tiingo_etf_daily.snapshot=20260801T173121Z-tiingo-etf-d1-r1` and
freezes completed raw-OHLCV `5/20` sequences, development-only normalization,
next-session open-to-close direction with non-up labeled zero, a 70/30
chronological split, 22-session dependency purge, feature-side discontinuity
screen, descriptive known event window through `t+1`, and fixed `5/10/20`-bp
round-trip costs. The CPU comparator and Docker PyTorch CUDA breadth are bound
to source-contract input
`sha256:340a6acede3e8d9d8058a766c9a7b1bfc6fb98a0bab68656d2bad3ed928d7849`.

The host CPU control and the network-disabled CUDA appointment used only the
three-ETF external snapshot. CUDA 12.8 ran fixed GRU, causal TCN, and compact
attention models for both windows, with four epochs and a 90-second/model stop.
No raw rows, labels, predictions, checkpoint, model weight, credential, KIS,
broker, Paper, or live side effect was written. Every six architecture-window
aggregate is negative at the fixed 10-bp cost view, so no winner, ensemble,
depth run, replay, PnL claim, or Paper input follows.

Claude's falsification-first verdict was `supported-with-limits`. It required
the 22-session purge with direct dependency separation, target-side events to
remain a known calendar/descriptive mask rather than a target-price filter, and
zero next-day return to be predeclared as non-up. The implementation also keeps
the input identity as source snapshot, frozen contract, and sample structure;
runtime numerical normalizer hashes remain diagnostics, avoiding a false
Windows-versus-Docker mismatch without weakening source or path reattestation.
Only the named Docker `/app/market_data` and `/app/model_artifacts` mounts are
recognized as external storage under `/app`; all other repository paths remain
rejected.

Reason: this proves the first small, reproducible CUDA breadth loop without
mistaking correlated ETFs, a single historical tail, or GPU activity for a
tradable model claim.

## 2026-08-02 - Kill short Norgate broad-holdout tail before rebuilding the panel

Decision: close the updated-local-Norgate tail readiness target as
`input_unavailable` before rebuilding the 523-symbol static panel. The official
host-only Norgate Python interface (package 1.0.77) reported the active US
Equities update at `2026-08-01T18:59:55Z`; only
`D:\market_data\us_equities\norgate_us_platinum_trial` matched that update
through its core metadata. Its build fingerprint is
`sha256:6cc5daacd420bf8531e25afb68d1875ee5017b0ea94fd91c8868ce5ad3563a1b`.

The source-safe external receipt is
`D:\thericher-v2\model-artifacts\data\norgate-trial-tail-readiness-v1\tail-norgate-tail-20260802-r1`
with hash `sha256:457b27d392c812782b56da2962bccbc2e8bcd8e00d593ead15f09cc960a13952`.
SPY, QQQ, and IWM each have 28 completed D1 sessions strictly after the frozen
2026-06-22 panel end. The full calendar interval through 2026-08-02 has only
41 days, so it cannot possibly satisfy the predeclared 126-session independent
holdout allocation. No raw rows were retained in the receipt and no full
panel rebuild, membership scan, model, GPU job, KIS call, broker action, or
credential path followed.

Claude's falsification-first verdict was `supported-with-limits`: preserve the
126 threshold rather than lowering it after seeing the tail, and when the tail
eventually passes report former-member count/share and per-symbol availability
beside any common intersection. A hash match would attest source bytes only,
not adjustment semantics or point-in-time availability.

Reason: measuring the calendar maximum first prevents a long source-local
rebuild from disguising a known insufficient independent validation window. It
limits only this prospective Norgate family and cannot make the company wait for
the next Norgate update.

## 2026-08-02 - Keep current-source compatibility monotone and causal

Decision: insert a pure current-source opportunity projection between the
caller-supplied opportunity fact and the existing local KIS intraday target
policy. It binds a source contract hash, symbol/market, completedness, and
validity window, but may only preserve or downgrade the upstream candidate. It
does not rank/select symbols, infer liquidity, create a candidate, read a
provider or credential, or reach an order path.

The existing v1 external replay evidence remains immutable. The corrected
interface is a distinct v2 replay because its caller-owned candidate and
per-decision causal source-prefix contract correctly change decision identity.
Its synthetic twenty-session replay is pinned by digest
`sha256:8855ec22147b9218fc83ac60eaf3cb17dd2a70b38bc46b7568aec5033ad383d1`:
matching v2 facts reproduce decisions and `source: local_paper` terminal-flat
fills exactly. An ineligible upstream candidate, stale source, source gap, or
source duplicate yields an abstention with no local-paper intent. Source
contracts hash only bars completed through the decision cutoff, so a future-bar
change cannot alter the decision, receipt, or bridge. The integration is graph
plumbing rather than a strategy, model, profitability, ensemble, GPU, or
Paper-promotion result.

Claude's requested falsification-first drift check timed out. Record this as
`review_unavailable`, not agreement or a new approval hold. The next valid
research action is source qualification for the independently discovered MIM-30
SPY one-minute hypothesis before any training allocation.

## 2026-08-02 - Close MIM-30 history qualification without inventing a collector

Decision: close `mim30-spy-long-only-derivative-v1` as `input_unavailable` for
its frozen historical evaluation contract. The local cache has 20 eligible
SPY/AMS 1m sessions against the predeclared 252. The bounded exact KIS minute
probe accepted two full pages without a categorical error but established only a
head-only terminal continuation shape with no initial historical-date field.
Do not reinterpret response `KEYB/NEXT` as an undocumented date selector, and
do not infer a provider-wide historical-data limit from this endpoint fact.

The source-safe MIM receipt is
`sha256:4d91b03e4a1f688d31a7a67e0595a2493650a2d7abfefb5372774a8c2e186d91`;
the exact route receipt is
`sha256:b061b611439008a30dbcba230d950faeecbfb5074dd08bb5edffa580eff20a18`.
Claude's falsification-first result is `unsupported` for evaluating this
historical source from the available input. In addition, current local-paper
semantics are a next-completed-bar-open/terminal-15:59-open proxy, not the
source's 15:30-to-16:00 close/auction window, so the contract must keep
`source_window_compatible: false` until a separately attested implementation
exists.

Reason: preserve a useful source and execution fact without producing an
unsupported MIM backtest, GPU run, or Paper claim. This ends only this campaign;
it does not stop a distinct prospective intraday engine baseline, Data work, or
authorized KIS Paper lifecycle.

## 2026-08-02 - Keep the prospective SPY baseline import-pure and tamper-safe

Decision: keep the prospective SPY regular-session baseline as a pure
research-only contract. Extract shared resampling primitives to
`thericher_v2.market`, retain `data.resample` as compatibility exports, and
keep the baseline leaf outside eager Data and Research package initialization.
Revalidate its frozen selected 1m/5m/10m/1h/3h tails when a prospective session
record is constructed, rather than trusting a structurally supplied window.

The fixed 15:30 ET baseline uses only a complete 09:30-16:00
America/New_York session and lookbacks 30/6/3/2/2. It is not a model-training,
GPU, profitability, ensemble, or Paper-promotion decision. It has no provider,
network, credential, broker, order, raw-data, or artifact behavior. The change
fixes two validation findings: tampered duplicate or missing selected bars are
rejected, and importing the baseline leaf no longer eagerly loads KIS, provider,
or execution modules.

Claude's static drift review is `supported-with-limits` for the pure
extraction/import-isolation claim. Its conditions are the running runtime suite
and subprocess verification plus the tightened tamper test; it is not a
profitability, promotion, or Paper verdict. No prospective session, KIS call,
Paper order, raw data, artifact, or GPU use occurred in this objective.

Reason: preserve causal input and import isolation so the next source-safe
prospective observation receipt can become usable research evidence without
turning market-session timing into an orchestrator wait or widening execution
authority.

## 2026-08-02 - Use a dedicated content-bound prospective observation receipt

Decision: use `prospective-spy-observation-receipt-v1` rather than a generic
proposal receipt for the fixed SPY 15:30 ET baseline. A generic structural
record or caller-supplied proposal reference would not reliably distinguish
changed OHLCV content with identical timestamps and counts, and would widen the
receipt around mutable identity. The dedicated receipt evaluates the frozen
baseline once per immutable record and derives its deterministic identity from
only source/record hashes, structural/session timestamps, baseline/feature
identities, ready status, categorical decision/reason, and a SHA-256 commitment
over the selected causal bars. It serializes none of those bars' OHLCV values,
prices, account/order/fill facts, paths, credentials, or mutable IDs.

Claude's `supported-with-limits` result applied only to the proposed pure
generic-receipt extraction as an architectural concern, subject to runtime,
subprocess, and stronger tamper verification. Data review found that generic
semantics did not satisfy the necessary source-safe content binding, so Codex
selected the dedicated receipt instead. Claude's scoped review did not approve
the final dedicated receipt design, a profitability claim, model promotion, GPU
work, or a Paper order.

Reason: make replay evidence deterministic and input-content-bound without
retaining market data or widening provider, credential, account, broker, or
live authority. The next fresh-session capture remains a Data-owned
market-data-only runner and cannot turn market time into foreground idle.

## 2026-08-02 - Scope fresh-session identity to selected source content

Decision: the prospective SPY capture runner uses a hash of every selected
09:30-15:30 ET `SPY/AMS/1m` source bar in its source contract, rather than the
whole verified cache hash. The complete selected source identity is therefore
stable when the collector appends a later minute or an unrelated cache chunk,
while any changed decision-session source value still produces a distinct
receipt and conflicts with an already materialized session artifact.

The runner is cache-only and same-Eastern-date: it accepts a regular 2026
session only after 15:30 ET, then writes a single canonical receipt outside
Git. `not_yet_observed` is an invocation-local source condition, never a
scheduler hold. Existing head collection retains cache and schedule ownership;
the runner adds no KIS client, credential, account, order, broker, or live
surface. The Claude drift check expired before a verdict, recorded as
`review_unavailable` rather than approval.

## 2026-08-02 - Narrow Tiingo mean-reversion to honest repeat-source falsification

Decision: the next Tiingo D1 portfolio-rotation rule remains CPU-only, but it
does not call a previously traversed three-ETF snapshot a sealed or independent
holdout. Its chronological validation is an explicitly non-promoting
falsification surface. The campaign records the two prior Tiingo family uses,
requires at least 100 active validation decisions before opening target-day
returns, and otherwise closes as `input_unavailable` rather than manufacturing
a weak kill result.

Claude's `uncertain` drift check identified two material design corrections:
the event/discontinuity mask now stops at decision time rather than reading a
target-day event marker, and active comparators run on exactly the candidate's
active dates to separate signal quality from passive exposure. Costs are fixed
as all-in round-trip `5/10/20` bp. The result cannot select, promote, ensemble,
allocate GPU, form a KIS input, or claim profitability; a later data tail needs
its own genuinely fresh, single-use evaluation contract.

## 2026-08-02 - Freeze a source-local SPY regime and micro-consensus falsification

Decision: use the existing verified `SPY/AMS` 1m KIS-private cache only through
its offline loader for one CPU-only, non-promoting deterministic intraday
falsification. The fixed 21 complete sessions split into `10 / 1 / 10`
development/purge/validation sessions. Before opening any target return, the
source-safe preflight tested feature availability only: a 12:30-15:30 ET,
ten-minute, non-overlapping regime/micro-consensus schedule has 32 active
validation decisions against a frozen 30-decision minimum.

The regime gate uses completed 3h and 1h bars; the micro consensus uses
completed 10m, 5m, and 30-minute 1m states. An eligible decision has a fixed
next-ten-minute open-to-open target and `5/10/20` bp all-in costs. Its main
selection comparator is macro-regime-only net bps per active decision; a
schedule-wide always-long view is descriptive. This avoids the invalid
candidate-active always-long comparison, which would duplicate the exact same
long-only entries. This is a small source-local falsification, not a PIT
result, model choice, PnL claim, Paper signal, or GPU request. Two concise
Claude calls yielded no substantive verdict
(`review_unavailable`); that fact narrows no standing authority and does not
hold this reversible offline work.

## 2026-08-02 - Reject the fixed SPY regime and micro-consensus hypothesis

Decision: retain the frozen source-local result as a rejection of this exact
long-only macro/micro consensus family. The 21-session `SPY/AMS` 1m cache met
the target-free 32-decision validation preflight, then the aggregate evaluation
failed its precommitted 20-bp net-total kill test. The rejection is not a claim
about live performance, a source-wide PnL result, or a reason to change the
fixed split, schedule, costs, or candidate after observing validation outcomes.

The source-safe external receipt records aggregate evidence only and the run
had no KIS, credential, account, order, broker, Paper, GPU, or live surface.
Do not derive a parameter search, ensemble member, model selection, or Paper
input from this failed family. A future Engine package must declare a distinct
hypothesis and fresh frozen contract before target evaluation.

## 2026-08-02 - Freeze a small source-local first-30m/final-30m falsification

Decision: test a distinct direction-signed SPY intraday-momentum premise from
Gao et al. (2018), whose official publication record states a 1993-2013
high-frequency SPY sample. The existing source-local cache can provide ten
chronological validation decisions after the frozen `10 / 1 / 10` split. This
is deliberately a small non-promoting replication, not a claim that its scope
matches the source paper.

At the completed 10:00 ET boundary, use only prior completed regular-session
close and the current first half-hour to freeze sign. Evaluate one signed
15:30-to-16:00 decision per eligible session against `5/10/20` bp all-in
costs. A non-positive signed validation total at 20 bp rejects the exact
family; no outcome may tune inputs, select a model, request GPU, form an
ensemble, or become Paper input. Direction inversion at the same timestamps is
comparative evidence, not a winner-selection mechanism. A concise Claude
check failed to return a verdict (`review_unavailable`), which does not block
this reversible private CPU work.

## 2026-08-02 - Reject the fixed first-30m/final-30m momentum hypothesis

Decision: retain the fixed source-local result as a rejection of the exact
Gao-derived first-30m/final-30m direction-signed family. Its 10 validation
decisions met the precommitted eight-decision preflight, then failed the fixed
20-bp all-in net-total kill test. The small current cache means this is neither
a source-paper replication claim nor a live-performance conclusion.

Do not tune the sign, timing, cost, filters, or direction-inverted reference
after outcomes were read. The external receipt holds aggregates only. No
selection, ensemble, GPU, Paper input, order, account, broker, credential, or
live behavior follows from the result.

## 2026-08-02 - Freeze a small causal MTF logistic baseline

Decision: use the existing pinned `scikit-learn` dependency for one
development-only standardized L2 logistic baseline over causal completed
`1m/5m/10m/1h/3h` SPY features. The 21-session cache supplies 190 scheduled
rows in each development and validation phase, but the ten validation sessions
remain the effective independent units. The package is a CPU breadth baseline,
not a reason to occupy GPU or claim a deployable model.

The fixed `C=0.1`, no-class-weight fit and `0.55` long-only threshold cannot
change after target access. At 20 bp it must be strictly positive in aggregate
and exceed an always-long reference by net mean per executed event; comparing
different trade counts by total would be invalid. This remains source-local,
aggregate-only, non-promoting, and outside Paper, broker, account, credential,
and live surfaces.

## 2026-08-02 - Close the fixed MTF logistic baseline before target evaluation

Decision: retain `spy-intraday-mtf-logistic-10m-v1` as `input_unavailable`.
The 21-session cache met its structural causal-row preflight with 190 rows in
each phase, but the fixed development-only model and `0.55` policy left fewer
than 30 target-free validation long decisions. Validation targets, returns,
cost totals, and kill logic consequently remained unopened.

Do not retroactively lower the threshold, relax the long-decision floor, or
reuse the result as a model, ensemble, GPU, Paper, PnL, or profitability claim.
The aggregate-only receipt stays external and records only contract, source,
structural counts, model identity, and categorical outcome. A follow-up is a
new frozen hypothesis, not a parameter repair of this one.

## 2026-08-02 - Isolate the Norgate client and qualify a fixed ETF D1 source

Decision: `norgatedata==1.0.77` is a dedicated Windows host-only
`norgate-host` optional dependency, not part of the base or Docker-installed
`research` extra. The installed local trial is accessed only through its lazy
provider path; missing client, unavailable local updater, and malformed D1
responses have separate categorical outcomes. No `.env`, KIS, account, order,
broker, local-paper, GPU, or live path belongs to this source foundation.

The fixed three-ETF D1 materialization is hash-attested and idempotent: an
identical rerun verifies the retained D: snapshot before any provider call, and
an incompatible requested window fails closed. Its 511 common-session source
is `qualified_for_offline_research` only. Local availability timing, point-in-
time membership, adjustment semantics, and corporate-action completeness remain
unverified, so it cannot rank, promote, create a Paper input, or support a
profitability claim. A later Engine package needs a new explicit source-local
campaign contract; this raw-source qualification is not that contract.

## 2026-08-02 - Use the fixed Norgate D1 panel only for one falsification diagnostic

Decision: the current fixed `SPY/QQQ/IWM` panel may support one predeclared,
CPU-only, source-local rule diagnostic. It remains a falsification instrument,
not a trained model or source promotion: it cannot select a candidate, consume
GPU, create a PnL/profitability claim, or reach Paper. Its results stay
aggregate-only outside Git, and a non-rejection is still only an inconclusive
source-local observation.

Claude's concise challenge was `supported-with-limits`: use a chronological
split, completed-bar decision timing, a frozen naive comparator and kill test,
and no reuse of this diagnostic to tune the same rule. Codex retains the
source's unverified adjustment, corporate-action, PIT, and availability
semantics rather than treating the requested `NONE` adjustment setting as a
proof of historical tradeability. This is a narrow research-scope decision,
not an approval gate on KIS, independent data work, or another research lane.

## 2026-08-02 - Close the fixed Norgate D1 momentum diagnostic without promotion

Decision: `norgate-d1-trio-momentum-falsification-v1` is closed as
`inconclusive_non_promoting`. Its fixed rule had 59 validation long decisions
with an aggregate positive-sign rate of `0.559322...`, while the frozen
always-long comparator had `0.536231...` across 138 structural slots. This is
one source-local directional observation only, not evidence that the rule is
profitable, robust, tradable, or eligible for a model, GPU, Paper, ensemble,
ranking, or source upgrade.

The same panel/rule/validation slice may not be retuned, threshold-swept, or
reused as a selection pass. The next package must state a distinct hypothesis
or independently test source stability. This preserves useful negative or
inconclusive evidence without turning it into a new approval process or
blocking independent KIS, Data, Engine, or Execution work.

## 2026-08-02 - Close direct Norgate/KIS D1 bar conformance without source promotion

Decision: retain `norgate-kis-d1-bar-conformance-v1` as
`input_unavailable`. The pinned offline sources have 501 common D1 sessions
per required symbol. All quiet-stratum price-relationship and volume-ratio
checks passed their frozen 5-bp/5-percent tolerances and beat both equal-count
one-session shift controls, but neither source produced a 20-percent raw
discontinuity. The required event-adjacent falsifier therefore had zero
samples and cannot support a conformance pass.

The result is limited to present-vintage quiet-bar relationship agreement. It
does not repair the existing adjustment, corporate-action, PIT, availability,
or source-identity limits; it cannot qualify a model, GPU campaign, ensemble,
Paper input, or live route. Review hardened common-predecessor construction,
equal-anchor shifts, noncommon-event projection, nested-path containment, and
exclusive immutable receipt creation before the real run. These are correctness
repairs, not a new framework or approval boundary.

## 2026-08-02 - Keep KIS D1 causal representation strictly non-promoting

Decision: the single `kis-d1-causal-representation-feasibility-v1` causal-TCN
campaign may use only the attested 1,510-session KIS D1 development phase,
with a fixed 32-row window, four terminal masked rows, three left-causal TCN
blocks, four CPU smoke steps, and one 192-step CUDA appointment. It completed
both runtime phases with finite categorical losses. The CUDA terminal mini-batch
did not decrease relative to its first mini-batch, so no learning-quality or
model-selection inference is available or needed for this feasibility result.

The campaign has no return label, validation-phase access, forecast,
profitability/PnL calculation, ranking, ensemble, Paper, broker, account,
credential, network, or live effect. Weights use external non-pickle `.npz`
storage only. Review required summary-to-contract binding, idempotent custody
closure, container-aware artifact defaults, and fail-closed orphaned-weight
handling; reattachment after those repairs confirmed the stored CPU and CUDA
receipts bind to the same frozen contract. A cooperative per-step timer remains
supplemented by the Docker `timeout` wrapper for any future bounded CUDA call.

Reason: use an actually KIS-shaped model input and the available GPU without
pretending a target-free reconstruction study is a trading signal. Claude's
subsequent falsification challenge rejects dispatch of the proposed Norgate SPY
pullback rule, not because of overlap but because its expected six-to-nine
active rows cannot distinguish a 5/10/20-bp cost effect from noise. Preserve a
30-active-row floor and treat more Norgate D1 coverage as an input requirement;
do not consume the current small segment as a pretend alpha test.

## 2026-08-02 - Require a passed source-local noise floor before encoder comparison

Decision: do not dispatch an LSTM, TCN, or Transformer architecture comparison
against the current six-symbol KIS D1 development source after the fixed
`kis-d1-candle-noise-floor-v1` baseline closed `noise_not_separable`. The
campaign used adjustment-robust same-candle ratios rather than cross-session
returns, a chronological 1,000 / 33 / remaining split, five fixed logistic
seeds, and 64 within-symbol contiguous-block nulls. Its actual-label result
did not clear the frozen null-margin plus seed-spread falsifier.

Reason: Claude's `uncertain` challenge correctly identified current-listing
survivorship, unqualified corporate-action semantics, and low effective
cross-sectional breadth. A more expressive encoder would consume scarce GPU
time while the simpler target association remains indistinguishable from its
own noise control. This is a scoped research conclusion, not a model failure,
data prohibition, GPU-idle rule, Paper gate, or operator-approval boundary.
Independent eligible Engine, Data, and KIS Paper work continues.

## 2026-08-02 - Recover a successful ID-less KIS virtual canary conservatively

Decision: a normal virtual-Paper canary recovery may bind a missing private
broker order reference only for a persisted `outcome_unknown` intent whose
submit response was categorically successful but omitted that reference. The
current virtual open-order snapshot must yield exactly one match on the
persisted symbol, exchange, side, remaining quantity, and limit price. The
private reference is persisted before the existing cancellation route is
eligible, then the same intent is reconciled again. The explicit unknown-run
reconciler stays read-only.

Zero, multiple, contradictory, or pre-submit-conflict matches remain scoped
unknown; they cannot create a replacement order, cancel a lookalike, become a
future-session permission state, or affect live routing. Raw references remain
inside the process and are excluded from safe projections and evidence.

Reason: this repairs the only deterministic recovery path available after a
successful response lost its order reference while preserving virtual-host
pinning and intent identity. A later unrelated exact lookalike remains a known
identity limitation pending a separate documented broker-correlation probe.
Claude's falsification review was `supported-with-limits`; tests prove
persist-before-cancel, no resubmit, and read-only isolation.

## 2026-08-02 - Treat active Norgate matching as a narrow source-local input fact

Decision: the fixed `SPY/QQQ/IWM` raw-D1 materialization matched two sequential
active Windows-host reads per symbol with 1,533 matching bars and zero
divergences. A distinct, explicitly frozen, CPU-only source-local baseline may
now use that materialization. It must predeclare causal timestamps, temporal
split, cost assumptions, naive comparators, and a kill test; the result remains
non-promoting and cannot create a ranking, ensemble, Paper input, or GPU
appointment by implication.

The source-safe probe receipt is
`sha256:aa3989e4246a21db6d45f5e85605f896ac0550ee5f6e8f535ee47b328a510bc7`.
It is an active-response comparison, not evidence of point-in-time
availability, historical revision policy, corporate actions, adjustment
semantics, entity identity, or tradeability. Do not turn a matching present
build into a source-quality promotion or a reason to retune the closed trio
momentum diagnostic.

The related trio receipt boundary now canonicalizes and revalidates the exact
base result before writing. This removes a narrow typed-subclass or frozen
object-mutation path without changing the target-free diagnostic strategy.

## 2026-08-02 - Close the fixed trio GBT discrimination preflight without promotion

Decision: close `norgate-d1-trio-intraday-structure-gbt-preflight-v1` as
`noise_not_separable`. Its one frozen HistGradientBoosting CPU configuration
used only multiplier-invariant same-session candle ratios at completed `t` and
the next session's within-session direction label. Across 139 validation date
groups it cleared neither its 0.08 advantage floor nor the 95th percentile of
64 nonzero circular date-block label shifts. The one-session shifted-label
control was not anomalously strong.

Do not change its windows, features, label, split, classifier, seed, null
shifts, effect floor, or thresholds after seeing this outcome. It creates no
model promotion, ranking, ensemble, GPU appointment, Paper input, PnL claim,
or execution consequence. A later candidate must use independently reattested
breadth or a distinct causal hypothesis and must freeze a fresh contract before
target evaluation.

## 2026-08-02 - Separate broad active-build value revisions from availability changes

Decision: the frozen Norgate broad D1 panel is currently reproducible from the
active local build: 523 rank-ordered symbols, 483 common sessions, and 252,609
bars had two repeatable reads and zero taxonomy differences. The external
receipt is `sha256:235af9ebdef1f61081314edc71f1bc0d2de9f266e1ed2e7d265294a1e853cf7a`.

For this exact conformance contract, a shared-session OHLCV mismatch is the
only `revision_detected` condition. Absent symbols, missing/surplus sessions,
malformed responses, and nonrepeatability remain `input_unavailable`; they are
not retrospectively relabeled as price revisions. This taxonomy preserves a
useful current-build reproducibility fact without conflating database membership
or adjustment behavior with values. It does not change static-panel PIT,
adjustment, corporate-action, availability, campaign, model, GPU, ranking,
Paper, PnL, or live eligibility.
Any later provider-free consumer must pin this receipt hash; a valid JSON
receipt without the consumer's expected hash is only self-consistent evidence.

## 2026-08-02 - Close the injected multi-timeframe model-to-local-paper seam

Decision: add one caller-injected, deterministic replay helper that reuses the
existing causal `1m/5m/10m/1h/3h` window contract, `MomentumModel`, target
position policy, research decision receipt, local-paper intent bridge,
local-paper fill/replay, and next-bar timing harness. It writes no artifact and
has no provider, cache, credential, network, KIS, account, or live route. Its
temporary local-paper state exists only inside tests.

Reason: Data schedulers must not create foreground engine idle time, but the
individual components already existed. Claude's `supported-with-limits`
falsification review found that a new score/decision/intent framework would be
duplicate drift. The retained seam instead has a sentinel kill test that proves
each existing path is traversed and two independent fixture runs yield the same
safe projection, including receipt-to-intent identity, next-bar timing, and a
replayable `source: local_paper` fill. Independent review additionally exposed
two local side-effect hazards: a too-short next-bar harness was checked after a
fill, and a same-store retry could record a duplicate rejection. The seam now
validates contiguous backtest timing before the first local event and first
tries the existing recorded-fill recovery path on a retry.

This is neither a predictive result nor an execution authorization: no market
dataset, PnL, training, model comparison, GPU, model artifact, ranking,
ensemble, KIS Paper decision, or broker order follows. The next model work must
freeze its own source-qualified causal campaign; the candidate KIS NAS D1
volume-exhaustion reversal remains only a proposed distinct CPU falsification
until that contract and its Claude challenge exist.

## 2026-08-02 - Keep direct Research leaves execution-free without breaking public imports

Decision: move the existing eager `thericher_v2.research` public API imports
behind a lazy compatibility module. Direct `thericher_v2.research.<leaf>`
imports now load only the requested leaf and its declared dependencies; legacy
`from thericher_v2.research import ExistingPublicName` imports the preserved
public surface on demand. The shared campaign registry now uses an
execution-free artifact-path helper with checked intermediate directories.

Reason: independent review found that the new offline volume falsification leaf
transitively loaded `research.validation` and therefore Execution merely by
being imported. That violated the leaf's fixed no-broker/Paper import boundary.
The lazy boundary preserves existing public API behavior while making direct
offline leaves honest and reducing unrelated startup work. The Claude
falsification request for this narrow architecture correction timed out as
`review_unavailable`; focused subprocess tests prove the leaf imports without
Execution and that the legacy public API remains available.

## 2026-08-02 - Close the KIS NAS D1 volume-exhaustion reversal as falsified

Decision: close `kis-nas-d1-volume-exhaustion-reversal-v1` using only the
attested 1,510-session six-symbol development phase. The corrected immutable
`cpu-falsification-r4` contract is
`sha256:ffe46f6a81e0e44e736db69fefcc7809a33b1e8eef9d1cc66aacb1a05d5f2e9d`;
the source-safe summary is
`sha256:0fd63b26eaf6680825c13a02bb5fae4b642af0ef121a156e815d0e92e5f87eb4`.

The contract left the consumed 647-session validation partition untouched,
ran a target-free structural census before target access, applied a 22-session
purge, and evaluated exactly the precommitted 10/15/20bp, candle-only, and
64 within-symbol full-10-session-block-null kill tests. Its candidate failed
the fixed 20bp flat relation, candle-only relation, and null P95 relation, so
the family is `falsified`. The final seven-session partial null block per
symbol stayed fixed.

The original r1-r3 attempts remain immutable but are superseded and not relied
on: review found a transitive Execution import, leaf-only code-revision custody,
incorrect nonpositive-volume abstention, unsafe child-path handling, Git-root
creation before rejection, and an artifact-root symlink route. The r4 contract
hashes every direct campaign dependency and rejects Git-resident or
symlink-traversing artifact roots before creation, while treating nonpositive
trailing volume as a full abstention. This creates no model selection, GPU
appointment, ensemble, PnL/profitability, Paper input, KIS call, broker action,
or live authority. A future candidate needs a fresh causal contract and
independent data; threshold retuning for this closed family is forbidden.

## 2026-08-02 - Keep direct Data leaves execution-free without breaking public imports

Decision: move the eager `thericher_v2.data` public API imports behind
`data/_public_api.py` and expose them through the same lazy compatibility
pattern used by Research. A direct `thericher_v2.data.tiingo_etf_daily` import
now loads only its own source leaf, while legacy `from thericher_v2.data import
ExistingPublicName` imports remain available on demand.

Reason: the offline Tiingo campaign otherwise transitively loaded unrelated
KIS/Execution modules through Data's eager package initializer. The change
preserves the public surface while making direct source-local research imports
truthful and faster. Claude's bounded architecture request timed out as
`review_unavailable`; subprocess and legacy-import tests are the supporting
evidence.

## 2026-08-02 - Close Tiingo D1 compression-continuation as falsified

Decision: close
`tiingo-d1-trio-intraday-compression-continuation-falsification-v1` with its
final `cpu-falsification-r2` contract
`sha256:2b7be8338f99399d7c1af6c9710d9634fb6e2dc74eb428ccdefea9c649743c7b`
and source-safe summary
`sha256:d1964e6b40cff6691eafd6c8300f140d8727c300bd8d2d6a535f44595ed3a39d`.

The repeat-source Tiingo snapshot supplied only a fixed 70 percent target-free
development census, 61-session purge, and one remaining validation segment.
The compression/close-location rule, equal-exposure comparator, 10/15/20bp
cost band, and 64 joint return-block null were fixed before target access. Its
candidate failed each predeclared 20bp/equal-exposure/null relation, so the
family is `falsified` and cannot be retuned or promoted.

The r1 receipt remains immutable recovery evidence only. Review required the
final r2 to reattach a canonical exact-allowlisted summary before a second run
could inspect a target, classify a target-free unavailable preflight with
`holdout_access=none`, and include the executing Data initializer in the code
revision hash. This decision creates no model selection, GPU appointment,
ensemble, PnL/profitability, Paper input, KIS call, broker action, or live
authority.

## 2026-08-01 - Require a terminal fact from the QQQ/SPY data-only observer

Decision: reuse the existing intraday-head task for one credential-bearing
Data collection followed by a credential-free QQQ/SPY pair observer and a
source-safe schedule receipt. During this bounded objective, the legacy QQQ
Paper and local-paper stages are explicitly `not_applicable`, not silently
skipped. A sealed `not_observed` attempt is a normal zero/one-leg result, while
an unavailable contract/input or busy append lock is terminal `recovery`.

Reason: the observer must accumulate every eligible session fact without
turning missing source legs into a scheduler failure, but it must not report an
eligible input/contract fault as a completed observation. Claude's
falsification-first review was `supported-with-limits` and required this
data-only terminal distinction. This changes neither broker authority nor the
historical 21-session exclusion, and creates no model, target, PnL, GPU, Paper,
or live claim.

## 2026-08-01 - Bind optional multi-timeframe predictions to actual causal bars

Decision: extend the existing target-position policy with an optional
`CausalMultiTimeframeSequenceWindow`. When a caller owns that window, the
policy reuses the existing causal-window validator and rejects a prediction
unless its symbol, market, decision cutoff, and exact per-timeframe
`feature_window_end` agree with the revalidated completed bars. Existing
missing, duplicate, generated-at, future, and freshness behavior remains in
the single existing policy path.

Reason: a prediction previously self-reported its feature end, so a slow H1 or
3h expert could claim the decision cutoff while actually using an older or
partial bar. The real existing momentum producer passed the exact-equality
smoke, while a forged slow-timeframe cutoff stamp fails closed. Claude returned
`supported-with-limits`: a new evidence bundle would duplicate existing
contracts, and source/feature-schema binding cannot truthfully use mutable
untyped `ModelPrediction.metadata`. This is an opt-in structural boundary, not
a model-selection, training, GPU, target, PnL, Paper, broker, or live decision.

Independent review additionally required the policy to compare the identity
reconstructed from the contained bars after revalidation, rather than trusting
the outer window header. The sole existing target-policy consumer that already
owns a causal window now passes it explicitly. Other consumers without a
causal window remain unchanged until a separate input-boundary package can
supply one truthfully.

## 2026-08-01 - Let existing MTF momentum experts consume causal windows directly

Decision: add one public pure
`build_multitimeframe_momentum_evidence_from_causal_window` function to the
existing multi-timeframe momentum module. It takes the already-owned
`CausalMultiTimeframeSequenceWindow` and the existing expert config, rebuilds
the selected bars through the existing validator, uses only each
`lookback + 1` trailing tail, and emits the unchanged evidence and prediction
types. The raw 1m/session-resampling entry point stays supported.

Reason: a separate feature envelope or source-contract wrapper would have no
current consumer and would duplicate the causal-window contract. Direct input
binding keeps the existing momentum producer and output-side policy binding on
the same bar identity without widening or silently resampling a model input.
The raw and direct paths produce identical five-expert CPU evidence; a forged
QQQ header with foreign slow/all-frame bars and invalid selected bars becomes
categorical unready evidence. The Claude CLI call timed out and is recorded as
`review_unavailable`, not a verdict or a hold. This is not a data, target,
return, PnL, training, GPU, artifact, Paper, broker, or live decision.

## 2026-08-01 - Bind the frozen consensus replay to one causal input window

Decision: retain the fixed consensus replay's raw completed-1m builder only as
an unready compatibility preflight. For ready evidence, reconstruct one
canonical five-timeframe window from the same completed prefix, use the direct
momentum adapter as the sole ready prediction source, require exact evidence
equality, and pass that exact window to the existing target-position policy.

Reason: this extends the causal input/output integrity chain into the only
existing frozen multi-timeframe consumer without changing its strategy,
resampling rule, data, target, cost, sizing, source provenance, or digest. A
reconstruction/direct mismatch fails before policy; an unready raw preflight
keeps the existing no-window abstention path. The fixed 20-session digest and
typed local fixture result remain unchanged. Claude timed out as
`review_unavailable`; independent review found no semantic mismatch when the
completed prefix, canonical order, and `lookback + 1` geometry are preserved.
This creates no provider, account, order, Paper action, PnL, training, GPU,
artifact, or live decision.

## 2026-08-02 - Keep the KIS NAS D1 HMM preflight source-local and non-promoting

Decision: retain `kis-nas-d1-intraday-regime-hmm-preflight-v1` only as a
source-local preflight. Its fixed per-symbol two-state HMM fit and state map
use source indices `0..599`; the forward-only screen uses completed decision
bars `t=622..998` solely to classify the next bar `t+1` open-to-close target.
The `602..621` filter warmup does not enter fit, scaling, or target mapping.

Reason: the result clears its predeclared all-long, joint-null, cost, prefix,
multiplier, and extreme controls, but it remains a six-current-listing,
unadjusted, non-PIT, development-only source. Claude's
`supported-with-limits` review requires independent date/source replication,
adjusted-price correctness, initialization stability, and turnover-aware cost
accounting before any comparative claim. This decision creates no Paper input,
ensemble, GPU appointment, PnL/profitability claim, or live authority.

## 2026-08-03 - Close the KIS NAS D1 HMM family after the later-tail persistence check

Decision: close `kis-nas-d1-intraday-regime-hmm-preflight-v1` and its fixed
`kis-nas-d1-intraday-regime-hmm-persistence-v1` continuation as one
non-promoting HMM family. The later check was precommitted before source load,
fit only `0..599`, excluded original screen `600..999` from its input, and
evaluated only later `1020..1508 -> 1021..1509` decisions.

Reason: the source-local first screen did not persist under the fixed later
window: all predeclared cost relations are at or below comparator and the
per-symbol primary guard failed. Claude called the design `uncertain` unless
described as a persistence check rather than independent replication; the
falsification confirms no stronger interpretation is available. Do not retune,
retrain, ensemble, allocate GPU, or form a Paper input from this family.

## 2026-08-02 - Preserve Norgate ineligibility and freeze causal MTF windows

Decision: reattest the existing Norgate Current & Past membership snapshot
read-only and preserve every declared direct-historical-universe,
publication-time, PIT, campaign, model, ranking, and sealed-holdout flag as
false. The reattestation is source-safe aggregate evidence only; it cannot
qualify a universe, source, model, ranking, holdout, or Paper input.

Decision: freeze the six explicit causal `1m/5m/10m/1h/3h` window profiles as
one outcome-free catalog. Register the catalog without selecting a cell. A
future campaign must introduce its own one-profile selection custody in that
campaign's frozen contract before it opens data or evaluation; this catalog leaf
does not create a speculative selection mechanism.

Reason: Claude's `supported-with-limits` review identifies current-and-past
survivorship/backfill and enumerated-window multiplicity as the remaining
risks. These controls preserve their limits without creating a scheduler,
research queue, model, GPU appointment, or paper-trading gate.

## 2026-08-03 - Require constituent reconstruction for KIS slow MTF inputs

Decision: the target-free KIS QQQ/SPY MTF input boundary materializes every
frozen profile only from the verified local 1m prefix at 15:30 ET. Before a
selected `1h` or `3h` bar can reach the in-memory normalized projection, it
must have exactly 60 or 180 contiguous completed minute constituents in its
own interval, all ending by the cutoff, and a fresh full OHLCV/volume
reconstruction must equal the selected bar. A timestamp label alone is never
causal evidence.

Reason: Claude's preflight was `supported-with-limits` specifically on this
leakage surface. The implemented read-only smoke produced 21 common sessions
and 126 profile-pair inputs with only aggregate/hash evidence outside the
workspace. The boundary neither selects a profile nor opens a target, return,
model, evaluation, GPU, Paper, broker, or live consequence. A later campaign
must still freeze its own profile-selection, target, split, cost, baseline,
kill-test, and compute-stop contract.

## 2026-08-03 - Bind forward MTF commitments to the causal prefix, not whole head cache

Decision: retain the installed legacy QQQ/SPY observer for its existing
scheduler, but implement a separate kis-mtf-profiled-prospective-observer-v1
for six-profile forward input evidence. Its contract binds the completed
preflight summary and the exact in-memory 21-session historical exclusion.
For a fresh eligible session, the head source contract is hashed from each
verified completed 09:30-15:30 ET minute prefix rather than the mutable
whole-cache dataset hash. The immutable external store retains only opaque
hashes, profile identifiers, categorical readiness, and structural scope.

Reason: the legacy store persists session dates, symbols, and timestamps, which
cannot satisfy the new source-safe artifact boundary. A whole-cache identity
would also allow a post-cutoff collector append to alter a sealed 15:30
observation despite unchanged causal input. Prefix-derived identity preserves
that invariance while the shared projection still reconstructs every selected
1h/3h bar from exact 60/180 completed minute constituents. This creates no
model, target, selection, training, GPU, Paper, broker, or live consequence.

The implementation additionally reattests the original frozen preflight source
contract and receipt identities before accepting a historical binding; matching
only the number of historical sessions is insufficient. Exact canonical payload
equality is required for duplicate recovery, and corrupt or conflicting stored
records fail rather than becoming observations. These are evidence-integrity
properties of this one forward witness, not a new collection, approval, or
execution control.

## 2026-08-03 - Keep the KIS broad-D1 2.0 screen fixed and isolate event censoring

Decision: retain the first broad-D1 candidate's `high / low > 2.0` geometry
definition exactly. A separate research candidate may censor only the declared
completed feature window `t-19..t`; it must not remove a pair because the
unseen `t+1` target bar is an event. The original reject-on-event candidate and
the new event-censored candidate are distinct lineages. Every baseline,
bootstrap, and permutation null in the latter uses the identical causal
availability mask.

Reason: the aggregate audit found 34 events, enough to explain the initial
candidate's categorical geometry failure but not to justify post-hoc threshold
tuning. Claude's falsification-first verdict was `supported-with-limits` and
required a session-block null in addition to per-target temporal permutation.
The actual CPU result did not exceed its strongest baseline or either null, so
the event-censored lineage is closed without CUDA, model selection, ensemble,
Paper input, PnL claim, or source-quality promotion. A later broad-D1
hypothesis must be distinct and first resolve its own adjustment semantics.

## 2026-08-02 - Bind the fixed prospective SPY receipt directly to the existing virtual canary

Decision: add a named SPY-intraday receipt bridge and one Execution adapter,
not a generic route or scheduler. The Data loader accepts only a canonical
same-session external receipt; the Engine bridge derives an opaque
`ResearchDecisionReceipt` from its complete immutable identity; Execution
accepts only a current ready `enter` receipt before reusing the existing
one-share SPY account/quote/intent/cancel/reconciliation canary. The daily SPY
D1 route and broker-free local replay remain distinct.

Reason: the previously existing daily and intraday paths used different model
contracts, so routing the intraday receipt through the daily baseline would
misstate the decision source. Missing, malformed, stale, and abstaining inputs
now stop before credential/config/account/quote activity; changed receipt
content changes the research receipt and durable canary identity. Claude's
falsification-first verdict was `uncertain`: the implementation is retained,
but the next named activation review must independently prove import-time
credential isolation, timestamp-derived staleness, and route-discriminated
durable identity. This scoped Paper-route condition is not a hold on Data,
Research, or unrelated Paper work, and is not a model/PnL/GPU/live decision.

## Prospective SPY Paper Safety Reattestation - Use an exclusive execution expiry

Decision: treat the prospective SPY immutable receipt as execution-current
only for `decided_at <= now < valid_until`. At exactly `valid_until`, return a
receipt-scoped no-intent before Paper configuration, account, or quote access.

Reason: the downstream canary decision requires a strictly positive validity
interval, so inclusive adapter freshness at its exact expiry could otherwise
misclassify an inevitable preparation failure as a quote failure. The adapter
already derives freshness from immutable receipt timestamps and the call-time
clock; making the boundary exclusive preserves that one source of truth.
Subprocess import isolation, all ineligible exits, a clock crossing during
preparation, D1/intraday durable identity separation, and virtual-host
rejection are covered without a KIS call. Claude timed out as
`review_unavailable`; this is not treated as approval or disagreement.

## Profiled MTF Flattened Control - Keep sequence alignment model-specific

Decision: expose one deterministic flattened MLP-style view over the existing
`NormalizedCompletedBarProjection`, but do not introduce a universal sequence
adapter for LSTM, causal-TCN, or attention models. The flattened layout is
canonical and self-identifying: timeframe, offset, bar count, end timestamp,
and per-timeframe normalization-anchor policy are bound with the upstream
projection digest and values.

Reason: the existing projection already owns causal ragged per-timeframe
sequences, source/profile/cutoff provenance, and feature values. A generic
sequence wrapper would either duplicate that contract or silently choose
cross-timeframe alignment, padding, masking, and availability semantics before
a model campaign has frozen them. The new view therefore revalidates inherited
causal geometry only; it does not claim independent raw-value provenance. A
later sequence model must make those choices in its own frozen campaign
contract.

## Shared Active Root For Parallel Pytest Verification

Decision: move both ordinary and `-RequireCleanTempRoot` pytest-helper runs to
the same active child root, `C:\trpy\runs`. Before either root is used, verify
the `C:\trpy` parent and active child are ordinary non-link directories with a
resolved direct-parent relationship. Retain the existing unique per-run child,
24-hour stale-root cleanup, and fail-closed treatment of any recent active root.
The direct legacy `C:\trpy\r-*` roots are preserved untouched; they are neither
deleted nor moved by this change.

Reason: a unique per-run base path already prevents temp-file collision, but
the former global direct-root precondition could keep every later authority run
red solely because an interrupted earlier run remained for diagnosis. A shared
new active root keeps current fast-lane and authority runs mutually visible, so
it does not hide an in-flight or unresolved current run. Immediately before the
migration, no pytest/xdist process was observed; the legacy roots remain outside
the new active namespace. Claude's falsification-first verdict was
`supported-with-limits`; its binding conditions are the single shared root,
parent-and-child link checks, retained 24-hour cleanup, explicit documentation,
and regression assertions for all of those properties.

## 2026-08-03 - Use durable evidence for periodic role activity reports

Decision: retain canonical English role identifiers in policy, code, paths, and
future ledger records, while exposing Korean display aliases for operator
conversation. On `에이전트별 활동사항 보고해`, Codex produces a source-safe
per-role summary from current stateboards, recent Git commits, and linked
external receipts. It includes accomplishment, material difficulty, material
recovery, and the next ready action or owned external wait. The default period
is the preceding 72 hours.

Reason: a periodic operator view is useful when long-running work is reviewed
every two or three days, but per-agent journals and saved chat reports would
duplicate history and recreate report sprawl. Stateboards remain current-only;
Git and immutable external evidence remain durable history. A scheduled GPT
prompt may request the same report, but chat is only a delivery channel. Claude
returned `supported-with-limits`: aliases must remain display-only, records
must stay bounded and source-safe, and no generated report becomes a new
artifact or approval gate.

## 2026-08-03 - Make Throughput Review event-driven and frequent

Decision: the Codex Orchestrator invokes the temporary Throughput Review at
task start/resume, each bounded package handoff/failure/worker yield, before a
long-running GPU/collection/session dispatch, and after unexplained foreground
idle. After 30 minutes of active orchestration, the next new dispatch first
gets a review; this is a ceiling on unreviewed dispatch, not a timer or a
foreground wake-up. The review updates `agents/orchestration.md` only when a
shared current `ready / owned / due` fact or reversible improvement changes,
replacing the superseded entry rather than appending a review diary.

Reason: the orchestrator must actively keep independent lanes moving while a
worker waits or a constrained resource becomes idle. Event-driven checks keep
that discipline close to real dispatch decisions without creating a management
lane, a recurring report, a global stop, or a new approval gate. Claude
returned `supported-with-limits`; its binding limits are no wall-clock review
worker, no mandatory write for an unchanged state, and no authority for the
review to hold a ready lane.

## 2026-08-04 - Measure prospective SPY timing without widening the scheduler outcome

Decision: add one network-disabled, credential-free
`kis-paper-prospective-spy-timing-probe` service after the existing successful
intraday-head collector and before the existing SPY cycle. The scheduler passes
only its raw host dispatch/return timestamps and the collector's existing
source-safe SPY aggregate fields. The probe writes its own external receipt
and may read the existing head cache through the cache-only prospective capture
boundary. It must not become a terminal schedule stage, a scheduler exit-code
input, a second collector, an account/quote/order route, or a Paper permission.

Reason: a post-collection cache observation is useful for quantifying current
source and container lag, but it cannot prove the cache was available at the
15:30 ET decision. The fixed 04:31 KST timing is also DST-dependent: it is
before the cutoff in standard time and at or after the exclusive 15:31 ET
expiry in daylight time. Preserve raw UTC and Eastern endpoints, explicit
offset/DST facts, and Docker-inclusive duration so a later schedule proposal
has evidence without fabricating a feasibility conclusion. Claude's
falsification-first verdict was `supported-with-limits`; the external receipt,
network isolation, no-terminal-coupling, and no-feasibility constraints are
binding.

## 2026-08-04 - Couple the prospective SPY receipt to the existing virtual-Paper canary

Decision: append one `kis-paper-prospective-spy-cycle` Docker service to the
existing `thericher-kis-paper-intraday-head` dispatch after its Data collector
returns successfully. The service consumes only the existing `intraday-head`
SPY cache through the canonical prospective capture boundary. It records a
source-safe no-intent result before any Paper configuration, account, quote,
or order surface when capture is unavailable, stale, malformed, or abstaining.
For a current `enter`, it delegates only to the existing one-share
virtual-Paper canary, whose content-derived receipt identity, virtual-host
pinning, durable intent, reconciliation, cancellation, and cross-process lock
remain authoritative. Do not add a Windows task or embed Paper execution in
the collector.

Reason: the current capture, frozen decision, and tested canary already own
their respective contracts. A narrow post-collector seam makes their lifecycle
recoverable without importing historical broad-D1 results or creating a new
broker abstraction. Pre-cutoff host and isolated Docker smoke runs reached
only `no_intent/before_decision_cutoff`, so no Paper action occurred. The
existing 04:31 KST trigger and the baseline's exclusive one-minute validity
now require a bounded source-time measurement around 15:30 ET before either is
changed. The architecture challenge was `supported-with-limits`; the final
route review was `review_unavailable`, neither of which changes standing
authority.

## 2026-08-04 - Isolate the SPY paginated-prefix capability measurement

Decision: measure the frozen SPY 15:30--15:31 ET completed-prefix assumption
through a new Data-only worker, cache namespace, and network-disabled observer
rather than changing the existing intraday-head or Paper cycle. The collector
owns one in-memory KIS Paper market-data client and records its own actual UTC
start before credential loading; a start outside the exact positive window
returns before KIS access. It writes an immutable run only under the dedicated
external cache and is bounded to four pages of at most 120 rows.

The pre-cutoff negative control is intentionally limited to an actual-clock
check that the new run namespace is absent. It cannot claim provider
availability, and its payload says `source_availability: not_observed`.
The later observer reuses neither credentials nor network, revalidates the page
bound, seams, exact 360 completed 09:30--15:29 ET timestamps, and rejects any
out-of-prefix timestamp. Therefore its sole positive label remains
`availability_within_validity_after_collection`, with
`decision_time_availability: not_observed`.

Reason: a separate early KIS source probe would require either a second token
path inside thirty seconds or a timer-holding shared client, widening the
measured worker before this narrow capability is established. The actual-clock
fresh-run control plus strict post-collection timestamp scope prevents a warm
cache, host-time assertion, oversized page, or current-minute row from turning
into a false positive. Existing head/Paper behavior is unchanged; task-owned
runtime evidence can arrive without foreground idle or a new approval boundary.

## 2026-08-04 - Minimize KIS read-only account projection custody

Decision: move the local KIS Paper account-console runtime projection to schema
v3 and omit reference prices, position prices, open-order limit prices, and
order identifiers. The bridge retains only currencies, orderable amounts,
symbols, sides, quantities, counts, freshness, and categorical failures. Its
legacy discovery evidence is likewise fact-minimized rather than serializing a
broker snapshot. The loopback dashboard displays only that projection.

One current fixed-virtual-host bridge invocation completed and the loopback web
process rendered its fresh projection without KIS credentials or broker access.
Claude's falsification-first review was `uncertain` and specifically prompted
the raw-price removal. This decision does not change KIS Paper authority,
paper sizing, canary routing, live isolation, data collection, or a future
executor's fresh call-time account/quote/reconciliation checks.

Reason: the console needs an operational account view, but price and broker
identifier retention has no role in that read-only dashboard loop. Reducing
the projection narrows accidental persistence exposure while keeping the
deterministic Paper executor independent.

## 2026-08-04 - Recover an exact prior virtual canary before a fresh matching session

Decision: before the scheduled quote-session requests a fresh price or creates
a new virtual Paper intent, inspect only direct private canary state files for
the exact `SPY`/`AMEX`/buy/one-share scope. A prior pending state may resume
only its own reconciliation or acknowledged cancellation path. Recovery cannot
enter a new-submit path. If the old state remains ambiguous or cannot be read,
the new matching session records source-safe `recovery_required` and stops
without a fresh quote or order. Other Paper scopes, Data, and Research remain
independent.

Reason: a fresh timestamped run ID previously meant that a prior
`submission_started`, `submitted`, `outcome_unknown`, or `cancel_started`
state was not considered before the next matching session. The shared lock and
durable intent protected concurrent submissions but did not close that
cross-session recovery gap. The new exact-scope preflight preserves the
operator's standing private Paper authority while preventing a duplicate
matching order. Focused tests cover id-less ambiguity, same-day completion
evidence, cancellation recovery, no fresh quote/order on an unresolved prior
state, and source-safe session evidence. Claude returned
`supported-with-limits`; its retained conditions are the exact scope, the
second pending-phase check inside the recovery entry point, the shared lock,
and no inference that a completion observation is a terminal fill or clean
cancellation.

## 2026-08-04 - Isolate a finite SPY D1 stability observation from data qualification

Decision: install one weekday 23:15 KST
`thericher-kis-paper-daily-spy-stability-observer` between the existing 22:15
prior-session `SPY/AMS` daily-head task and the independent 23:35 virtual-Paper
canary. The observer may use only the virtual-Paper app pair and the existing
shared request/token-start gates. After a verified 15--90-minute-old head
snapshot and successful authentication, it can send one `dailyprice` request
and compare only the retained prior-session row hash. Its external receipt is
bounded to ten GET attempts, is guarded by a nonblocking cross-process receipt
lock, and contains only categorical status, timestamps, fixed scope, and
hashes. Its vocabulary includes `stable`, `changed`, `unavailable`, and
`outside_window`; every receipt retains `provider_finality: not_observed` and
is structurally outside Engine import paths.

Reason: the first D1 bridge proposal could not infer a provider-finality or
decision-time fact from the same cached snapshot, so Claude returned
`uncertain`. The revised observation received `supported-with-limits` only
after it kept the timing window, snapshot-age bounds, virtual-Paper identity,
finite budget, and non-promoting output explicit. Independent review found
three implementation faults before activation: authentication/config failures
were counted as GETs, the worker bypassed the shared KIS gates, and its finite
ledger was not cross-process serialized. The repaired implementation has a
separate pre-authentication phase, the narrow writable control mount, and a
nonblocking external lock; its focused tests and re-review passed. This adds
one Data fact without a data qualification, model campaign, GPU work, consumer
bridge, Paper permission, or change to existing execution authority.

## 2026-08-04 - Reattest the Norgate fixed-trio current build without promoting it

Decision: accept one explicit-snapshot v2 active-build conformance receipt at
`D:\thericher-v2\model-artifacts\data\norgate-active-build-revision-v1\revision-current-512-20260804-r1\receipt.json`.
It verified the immutable 512-session `SPY`/`QQQ`/`IWM` snapshot before any
active local read, read each symbol twice through the host-only Norgate client,
and recorded a `matching` result with 1,536 reference bars, 1,536 active bars,
and zero divergences. The receipt retains hashes, counts, and categorical
outcome only; it retains no raw bars, dates, paths, credentials, KIS call,
broker route, model, GPU result, PnL, or Paper input.

Claude's falsification-first verdict was `supported-with-limits`: agreement
between two reads and a frozen snapshot measures local current-build
repeatability, not vendor correctness, publication timing, point-in-time
availability, adjustment semantics, or capital-event completeness. A future
mismatch remains a `revision_detected` classification rather than a crash or
consumer promotion. Claude rejected the proposed source-local range-risk
diagnostic because those unresolved semantics can contaminate its next-session
range target and its short, overlapping three-ETF validation would not provide
enough independent evidence. No such campaign, CPU/GPU appointment, ensemble,
or Paper path is opened.

Reason: the explicit reference boundary closes the narrow gap between the
latest fixed-trio structural receipt and an active local source response while
preserving the distinction between repeatability evidence and causal research
input. It improves Data recovery without making the project wait for a new
provider or weakening any research or execution constraint.

## 2026-08-04 - Bind decision receipts to executable semantics

Decision: retain caller-provided `proposal_ref` as opaque lineage only. Every
new `ResearchDecisionReceipt` additionally carries two opaque, deterministic
commitments derived from its actual `TargetExposureProposal`: instrument/market/
decision class, and instrument/market/decision class/target exposure. KIS Paper
recomputes the first commitment from its execution binding; local Paper
recomputes both. A mismatch returns a receipt-scoped no-intent before an order
intent or KIS decision is created. Legacy receipt payloads remain parseable for
evidence/replay, but neither Paper route prepares an execution from one.

Reason: matching an arbitrary opaque lineage reference did not prove that an
execution binding retained the proposal's symbol or local target exposure. That
could corrupt the decision-to-intent/PnL attribution chain even though each
individual object was valid. The commitments preserve the source-safe receipt
boundary because they expose only hashes, never symbols, exposure values,
prices, raw inputs, credentials, or account data. The daily local replay now
passes its actual allocated target rather than a lossy fixed-lot surrogate.
Claude's bounded drift-check timed out as `review_unavailable`; an independent
Validation review found the fixed-lot regression before integration and its
repair plus the wrong-symbol/wrong-target and legacy fail-closed tests passed.

## 2026-08-04 - Reactivate the bounded QQQ provisional-Paper dispatch

Decision: after a successful run of the existing single
`thericher-kis-paper-intraday-head` collector, dispatch the already implemented
QQQ runtime receipt session before the slower SPY timing and Data-only observer
stages. The route consumes only its just-collected 90-minute completed local
window, replays it locally, proves two-minute freshness at both account and
submit boundaries, then uses the existing virtual-only receipt canary and
exact-session network-disabled validator. No new Windows task, broker adapter,
credential path, live route, or public surface is introduced.

Reason: the pre-existing QQQ route was left inactive when an older objective
forbade Paper/local-paper work, while the new SPY cycle is structurally tied to
15:30 ET and the same worker runs around 11:31 ET. That left the available
90-minute observed/provisional baseline unable to generate either a scoped
no-intent or real virtual-Paper lifecycle fact. The QQQ session's local replay,
freshness, account/open-order, quote, durable-intent, virtual-host, recovery,
and cancellation checks remain authoritative. Stale, malformed, missing,
misaligned, conflicting, paused, or unresolved inputs must remain no-intent;
the result is execution evidence only, never an alpha, PnL, or promotion claim.
Claude CLI timed out as `review_unavailable`; it was not treated as agreement
or a hold. A fake-Docker host-dispatch simulation plus focused QQQ/schedule
tests independently verified ordering and exact session validation.

## 2026-08-05 - Scope virtual-Paper recovery to the exact run

Decision: remove the quote-session scan that recovered every prior pending
`SPY`/`AMEX`/buy/one-share state before a new run. A replayed session ID still
uses its own durable state and existing recovery path. A distinct run retains
the shared execution lock, durable intent-before-side-effect, fresh account and
open-order snapshot, conservative matching-open-order rejection, virtual-host
pinning, and cancellation behavior. Historical state is neither deleted,
mutated, nor relabeled clean. A legacy terminal-field probe may use a derived
creation-time ET day only for the original deterministic identity form and
only when its timestamp/skew/validity interval is internally consistent; its
safe output explicitly distinguishes that derived anchor from an acknowledged
submission date.

Reason: the cross-run scan turned one historical unknown into a same-scope
global hold even though a distinct new intent already has a fresh call-time
account/open-order check. The refined boundary preserves same-intent recovery
and actual duplicate-order protection while allowing independent virtual-Paper
progress. A real derived-date history absence remains unqualified rather than
being misread as no order, cancellation, fill, terminal state, or PnL.
Claude's terminal-probe review was `supported-with-limits`; the separate
cross-run review timed out as `review_unavailable` and was not treated as
agreement. Focused tests cover exact-run no-resubmit, distinct-run old-state
preservation, current-open-order no-submit, malformed unrelated-state
containment, legacy positive history identity, and invalid legacy anchors with
no credential or network access.

## 2026-08-06 - Preserve rule-specific semantics before sharing target adapters

Decision: do not extract the current session-reset Donchian target adapter
into a generic rule adapter while adding the first session-reset EMA mechanism.
The first EMA package has a pure, independently implemented rule with an
explicit within-session seed policy and structural warmup state, plus a separate
rule-specific target adapter. Its hermetic local-paper seam test proves only
receipt-bound next-bar/restart replay; it does not create a source-data replay
or execution route. A future shared adapter may proceed only after every
participating rule exposes an explicit input-status contract and contributes a
stable rule identity, feature schema identity, and full parameter/seed payload
to proposal lineage.

Reason: Claude's falsification-first review was `supported-with-limits`, but
identified that the current adapter infers warmup from a Donchian-specific
reason prefix and hashes only Donchian parameters. Generic reuse could turn an
EMA warmup into a ready target or conflate equal lookback values across rules.
Keeping the rule and target adapter rule-specific preserves causal meaning and
avoids a premature shared execution boundary. This decision adds no KIS,
external-broker, KIS-Paper, PnL, GPU, or model-promotion behavior.

## 2026-08-06 - Bind local-paper next-bar fills to durable acceptance time

Decision: retain the existing acceptance event timestamp as local-paper replay
state rather than reconstructing only the `OrderIntent`. Reject a submission
that predates its intent creation, and raise on a requested fill or recorded
fill recovery when the later of intent creation and acceptance follows an
intraday execution bar start. Equality remains valid so a completed signal can
fill at the immediately following discrete bar open. For D1, apply a date-only
check only to the declared US market and venue-alias session-label contract:
acceptance after the execution label date fails, while same-date availability
is not treated as a sub-session proof. Other D1 markets fail closed until they
supply an explicit session-time contract. Do not append a retrospective
rejection after a recorded fill: fill events remain authoritative, while a
contradictory legacy log fails its exact replay.

Reason: independent Review found that an order accepted after an execution bar
could otherwise be paired with that historical bar and receive its open price.
Claude's falsification-first verdict was `supported-with-limits`: the durable
event time is sufficient without a schema migration, but caller timestamps are
still an internal-consistency surface rather than proof of strategy causality.
Focused offline tests cover distinct next-bar-open pricing, late acceptance,
pre-creation submission, pending-order restart, mismatched bar pairs, and a
late-accepted legacy fill. Claude's D1 follow-up was
`supported-with-limits`: the date-only US exception can admit post-open data on
the same UTC label date because the current source has no actual session-open
timestamp. That source limitation is intentional, named, and not a
fill-quality or model-performance claim. This changes no KIS route, credential
path, live behavior, model result, PnL claim, or Paper authority.

## 2026-08-06 - Do not backdate the QQQ observed runtime replay

Decision: retain `KisPaperIntradayRuntimeWindow.as_of` as the actual worker
observation timestamp and retain it as the QQQ proposal decision time. When the
only retained candidate replay bar already began before that decision, return
the exact local-only `decision_after_replay_bar` no-intent without creating
runtime state, an order, or a fill. Do not relabel the path as a counterfactual
decision at the preceding input-window end, because its local-retention and
Paper evidence would then attest a different time from the receipt.

Reason: Claude's falsification-first review was `supported-with-limits` for a
counterfactual alternative but identified that the existing availability
attestation rejects a decision before the worker observation. A filled replay
would therefore either backdate an order or split the receipt and availability
clocks. The scoped no-intent preserves causal truth while keeping the existing
future same-clock KIS Paper path available. Tests bind observation time to the
proposal, prove the no-intent creates no local state, and keep the actual
availability/promotion path separate. This adds no scheduler, KIS call, broker
route, credential use, live behavior, or model-performance claim.

## 2026-08-07 - Preserve validated QQQ session identity in the terminal receipt

Decision: pass the host dispatcher's existing validated safe QQQ prospective
session ID and matching validation session ID to the existing terminal receipt
only when each is present. Preserve absent, conflicting, or mismatched IDs as
their existing scoped receipt recovery outcomes.

Reason: the exact 00:29 KST task collected successfully and emitted a QQQ
`no_intent`, but the dispatcher omitted both already-derived IDs from the
receipt CLI, producing `prospective_session_id_unavailable` and preventing
offline validation reattachment. A network-disabled fake-Docker dispatcher test
now reads the actual passed receipt arguments: matching IDs complete, while
missing QQQ IDs, conflicting QQQ IDs, mismatched validation IDs, and conflicting
validation IDs recover. Claude timed out as `review_unavailable`; independent
Review identified the final conflicting-validation case, which the focused test
now covers. This changes no KIS call, scheduler, broker route, order behavior,
credential path, live behavior, fill, PnL, or model claim.

## 2026-08-09 - Project a closed pre-submit disposition from Paper lifecycle evidence

Decision: the offline Paper lifecycle reader emits `pre_submit_disposition`
only for `not_submitted` facts. It maps known local causes into a closed,
low-cardinality vocabulary and maps every unknown value to
`other_not_submitted`; all other lifecycle states omit the key entirely.

Reason: the prior source-safe lifecycle surface proved a non-submission but
could not distinguish an unavailable reconciliation from an expired or paused
intent. The new projection resolves that narrow operational ambiguity without
retaining a raw reason, broker body, account fact, price, credential, or order
identifier, and it changes no KIS call, scheduler, order action, reconciliation
behavior, sizing, or live route. Claude's falsification-first verdict was
`supported-with-limits`: default-deny mapping and absent-key behavior for
non-submissions are covered by focused offline tests; aggregate correlation
with existing opaque timestamps remains an acknowledged private evidence-surface
limit.

## 2026-08-09 - Keep intraday causal qualification hash-bound and default-deny

Decision: extend the offline intraday-head terminal reader with an optional
SHA-256-bound, source-safe causal-condition attestation. It can classify an
input as `qualified` only when that immutable external receipt matches the
terminal's capture, availability, and pair identities and names the independent
clock authority, `America/New_York` DST/session rule, completed M1 geometry,
non-overlapping chronological boundary, decision-time availability, and
provider finality. With no binding, malformed evidence, or any missing
condition, the exact input cannot qualify: absent bindings and missing
conditions remain `input_unavailable`, while malformed or mismatched bound
evidence fails closed through the reader's existing unavailable result.

Reason: the prior reader's single-value types made a future qualified outcome
impossible even if a later independent evidence source became available. The
new branch is deliberately unreachable in current production artifacts: no
installed task writes or binds an attestation, no scheduler or KIS path changed,
and the current result remains unavailable. Claude's falsification-first
verdict was `supported-with-limits`: the fixture proves only contract behavior,
not a provider property; the explicit independent-observer marker remains
assumed-honest-host provenance rather than cryptographic proof. Focused offline
tests cover the valid binding, a missing finality condition, tampering, and no
network access. No credential, KIS, Docker, order, model, GPU, Paper, live, or
public behavior changed.

## 2026-08-10 - Carry the QQQ provisional input grade through Paper reattachment

Decision: retain the existing task-owned QQQ runtime/Paper route and add one
compact, immutable interpretation to its loop, execution-session, and offline
validation evidence. A ready runtime window is always
`observed_provisional`; provider decision-time availability and provider
finality remain `not_observed`, terminal-state support remains `unqualified`,
PnL remains `not_observed`, and the result is never promotion-eligible. The v5
offline validator recomputes the expected grade from the verified cache/window
and rejects a missing or altered loop/session grade. Its v5 namespace preserves
earlier validation artifacts rather than overwriting them.

Reason: architecture already permitted an explicitly graded, bounded virtual
Paper observation but the QQQ authorization existed only as a nested baseline
field and the validator did not independently verify it. The new small contract
keeps the interpretation attached to the source-safe execution evidence without
adding a scheduler, collector, model, broker behavior, credential path, or
submission gate. Claude's requested drift-check timed out as
`review_unavailable`; this was not treated as agreement. Focused offline and
fake-dispatch tests cover the exact grade, missing/unavailable input, session
projection, validator reattachment, and a tampered finality value.

## 2026-08-10 - Make Tiingo IEX snapshot reattestation portable across zlib runtimes

Decision: retain the pinned Tiingo IEX normalized gzip SHA-256 check and every
raw-source hash check, but compare the compressed file's decompressed payload
against the exact canonical CSV rebuilt from the attested raw responses. Do not
require a new gzip byte stream to equal a stored stream generated by a different
runtime. The bounded comparison rejects truncated, invalid, extended, or
content-different gzip payloads and does not regenerate or overwrite the
immutable snapshot.

Reason: the host's Python/zlib-ng build and the Docker research image's Python
3.12/zlib build produced different compressed bytes for the same canonical CSV,
while the pinned stored gzip, manifest, raw hashes, and canonical payload all
matched. Exact compressed-artifact hashing still detects a changed stored file;
exact payload equality still binds it to its raw sources. Focused tests accept
an independently compressed equivalent payload and reject a changed canonical
payload. Claude's requested falsification-first review timed out as
`review_unavailable`; it was not treated as agreement or a hold.

The repaired reader enabled one CPU preflight and one CUDA appointment for the
fixed Tiingo IEX r1 masked-reconstruction matrix. All three fixed architecture
families completed with categorical finite-run and memory-release evidence only.
No weights, loss values, raw rows, predictions, returns, holdout, model choice,
KIS input, Paper action, PnL claim, or live behavior was created. This lineage
is closed to selection and cannot receive another appointment by implication.

## 2026-08-19 - Keep future causal-attestation writing networkless and default-deny

Decision: add a separate future-only writer that reads the current source-safe
intraday terminal projection and one external-observer input. It writes a
canonical immutable attestation outside Git only when the terminal has complete
capture coverage, exact availability and pair bindings, and an exact matching
run/timestamp input with complete clock, session-rule, completed-bar,
chronological-boundary, decision-time, and finality categories. Missing,
task-derived, stale, malformed, mismatched, or time-invalid input writes
nothing. The writer neither calls KIS nor changes a task, collector, Docker
service, broker route, existing terminal, or Paper action.

Reason: the existing reader already default-denied an absent or malformed
attestation, but had no bounded producer for a future independent-observer
artifact. Claude's falsification-first verdict was `uncertain`: matching hashes
cannot cryptographically prove that the external input was independently
observed. The artifact claim therefore retains the assumed-honest external
observer limitation, while exact run/timestamp binding rejects an explicit
task-derived input and a stale replay. Focused tests cover no network access,
outside-Git storage, idempotence, incomplete current-terminal denial,
task-derived input, stale input, and invalid time order. The real current
terminal smoke returned `not_written/session_coverage_incomplete`, so no
artifact was attached or backfilled.

## 2026-08-19 - Diagnose intraday capture gaps before changing the one task

Decision: retain the existing enabled one-action intraday-head Task and all
four trigger times. Add a metadata-only topology audit plus an external,
source-safe dispatcher `started`/`terminal` invocation marker. The marker is
written immediately before the existing collector and after the existing
schedule receipt; its terminal record hashes the exact start marker. Do not
change timing, page count, consumers, Docker services, collector locks, or the
Task definition until a later task-owned marker distinguishes the observed
boundary.

Reason: the audit found sparse retained chunks associated with the expected ET
slots, including an incomplete latest session with only its first slot retained.
But metadata cannot distinguish a missed Scheduler start from a collector,
provider, persistence, or de-duplication outcome. The Task is `Ready`, enabled,
and has one action, while Task Scheduler Operational logging is disabled. The
attempt to enable that log was denied by the host, so it remains a categorical
observability limitation rather than a reason to infer failure. Claude's
falsification-first verdict was `unsupported` for a downstream/timing fix from
the available evidence. Focused tests prove metadata-only auditing, external
receipt idempotence/hash binding, no raw data/credential/network path, and
dispatcher ordering. The marker proves only assumed-honest-host provenance,
not cryptographic Scheduler-origin proof or a provider/PnL/model fact.

## 2026-08-19 - Preserve the intraday invocation time boundary exactly

Decision: keep the existing one-task dispatcher and diagnostic-only marker
contract, but record the schedule-observed time and the actual later dispatcher
completion time as separate terminal fields. Add an offline source-safe reader
that requires the exact invocation run ID, schedule timestamp, terminal outcome,
and bound schedule receipt before it reports a narrow category. It may compare
metadata-only topology, but explicitly does not treat it as exact run binding.
It exposes the exact evidence pointers only relative to the external artifact
root.

Reason: the old terminal marker used the collector-return/schedule-observed time
as its completion value even though the terminal marker was written after the
schedule receipt. That erased the boundary the current Data objective is meant
to diagnose. This correction changes no Task definition, trigger, collector,
KIS/Docker route, Paper behavior, raw data, or consumer. The required Claude
drift request produced no verdict before its bounded local timeout, recorded as
`review_unavailable`, not agreement or a block. Focused tests cover time-order
validation, exact run/timestamp mismatch rejection, marker-unavailable and
start-only states, complete/partial/nonzero classification, and no secret or
Task-start surface. The provenance remains marker-present under an assumed-honest
host, never cryptographic Scheduler-origin proof.

## 2026-08-19 - Keep public RL references out of owned execution semantics

Decision: retain FinRL as an MIT source-only environment-interface reference.
Do not import its package, data pipeline, model weights, reward timing, cost or
fill conventions. The existing caller-owned `LocalPaperBroker` remains the only
future policy environment seam: a synthetic two-step external-policy fixture
must submit each independent decision before its next completed bar, fill through
the same fee/slippage contract, and replay terminal-flat realized-after-cost
accounting. This is an interface capability, not a market result, model result,
campaign, GPU appointment, or Paper action.

Reason: Claude's falsification-first verdict was `supported-with-limits`.
Freezing RL runtime adoption does not justify deferring data-independent proof
that a later external policy can use owned execution semantics. The focused
fixture proves that seam without a provider, credential, network, KIS, Docker,
runtime, raw market input, or new execution route. It also prevents a future
framework from silently substituting same-bar rewards or a different cost/fill
model for replay-parity evidence.

## 2026-08-19 - Treat an intraday collection-stage nonzero as task-path evidence

Decision: classify the first fresh hash-bound intraday marker as one exact
task-path `collection_exit_nonzero` fact only. Its bound schedule receipt is
`recovery` with scheduler exit `1`; it does not prove a collector process
started, or assign cause to Docker, provider, persistence, request pace, page
count, or Scheduler timing. Keep all task triggers, pages, consumers, KIS
routes, Docker services, and Paper behavior unchanged. The next recovery may
retain a reason only as a closed allowlisted category with free-text structurally
impossible, while preserving the original stage exit code.

Reason: the marker established the start, schedule-observed, and dispatcher-
completion boundary, but the collection stage's code is supplied by the host
service wrapper and not independent root-cause evidence. Claude's
falsification-first verdict was `supported-with-limits`: a generic diagnostic
can mask the nonzero or leak credentials/account identifiers through exception
text, and the existing receipt already localizes stage-level exit codes. A
behavior change needs a source-safe categorical reason that distinguishes a
deterministic dispatcher/config case from a collector/provider case in at least
two hash-validated bindings. Until then, the result is Data-only and never a
model, PnL, Paper, or live fact.

## 2026-08-19 - Retain only closed intraday failure categories

Decision: future immutable intraday invocation terminals may retain one of
`reason_unavailable`, `dispatcher_config`, or `collector_provider` beside the
existing collection-stage exit outcome. The scheduler dispatcher derives a
non-default category only from exactly one existing structured collector error
payload with the expected shape and approved fields. It retains no payload,
command output, exception text, credential, account value, market row, or raw
broker data. A zero collection exit must use `reason_unavailable`; malformed,
unknown, ambiguous, or free-text-looking output also stays
`reason_unavailable`. Readers interpret old immutable terminal bytes as
`reason_unavailable` without rewriting them.

Reason: the existing source-safe task-stage fact distinguishes only a nonzero
collection return, while a behavior change requires evidence that can rule out
at least one broad recovery class without expanding the diagnostic data surface.
The closed mapping preserves exit semantics and allows one later task-owned
hash-bound marker to provide a narrow Data fact. The scope-matched Claude
falsification-first request ended `review_unavailable` because the service was
overloaded; it was not treated as agreement or a cause verdict. Any future
category-based recovery still requires a fresh Claude verdict and two
independently hash-validated matching task bindings. The category remains
assumed-honest-host marker provenance, not cryptographic proof of Scheduler
origin.

## 2026-08-19 - Recompute the full selected-policy cycle before lineage

Decision: a selected-cohort lineage reference now requires the original
selection-policy entries and the frozen selection, per-symbol policy, and
allocation configs. Its builder independently replays the complete cycle and
rejects every supplied outcome that differs before producing an opaque proposal
reference. The cohort identity now includes policy and allocator geometry as
well as selection context and candidate outcomes.

Reason: replaying only the rank left a narrow integrity gap: a caller could
pair a valid selected symbol with a substituted same-identity downstream target
and obtain a receipt-compatible lineage reference. The narrow pure replay
preserves the existing separation between Research proposals and Execution
authority while making a target substitution fail before receipt or local-paper
preparation. Focused offline tests cover a forged allocation outcome and both
policy and allocator config mismatches. The requested Claude falsification
check returned no output before its bounded wait, recorded as
`review_unavailable`, not agreement. This changes no data, credential, KIS,
broker, Docker, GPU, model, Paper order, PnL, or live behavior; it still does
not prove complete-universe coverage or predictive score validity.

## 2026-09-21 - Partial reset toward a restart-safe Paper loop

Decision: on the operator's explicit instruction, supersede the incomplete
`kis-paper-d1-prospective-observation-pair-result-v1` company objective with
`kis-paper-spy-restart-safe-lifecycle-v1`. This is reassignment, not evidence
that D1 succeeded. Keep D1 measurement and its owned due state, immutable
receipts, quarantine, and exact reader bindings independent of the baseline
Paper lifecycle and source-local developmental research.

Already-seen lawful data may support new finite developmental contracts linked
to prior trial families, including bounded training. Closed masks, results,
and spent evaluation history stay intact; refreshed data or another split is
not a fresh holdout or independent replication. Match prediction targets to
execution payoffs and disclose outcome censoring. KIS timing/finality and
replay parity remain requirements for the claims/consumers that need them,
not a universal ban on development. These current rules supersede broader
historical source-reuse or company-wide waiting restrictions in older entries.

Repeated read-only reconciliation uses exact persisted identity and the owned
serialized path. The runbook's prior-attempt-proof prerequisite is retired;
it was not a runtime authorization boundary. Unknown side effects still block
duplicate submission of that exact intent. Submission-date recovery and the
never-submitted-intent state defect are explicitly deferred to Execution.

The bounded bootstrap changes only policy and D1 source/tests: one client must
budget one page per fixed target, retain its one token, and preserve a typed
`daily_page_limit_exceeded` diagnostic. The original one-page assertion did not
exercise that integration. This is not a pacing/quota, route, schedule, cache,
deployment, or broker change. Existing live, rights, paid, public, runtime,
holdout, and deterministic execution boundaries remain.

Claude's supplied-facts-only, tool-disabled challenge returned
`supported-with-limits`: tests must exercise the actual two-target factory,
fixture success must not imply deployment/reconciliation, D1 must not reappear
as a global prerequisite, and durable identity/serialization must remain.
The suggested external one-page quota counterexample was not found: the
existing pair collector already budgets two attempts while shared request and
token gates separately enforce pace. No new authority was inferred from Claude.
This operator-requested bootstrap is a focused-verified role repair and policy
reassignment, not company-objective completion or execution-recovery promotion;
the next objective retains the existing full integration verification contract.

## 2026-09-21 - Preserve submission time and distinguish unsent intents

The operator resumed implementation, postponing the Terra handoff. Persist an
optional write-once client attempt time before submission; retain it through
late reference recovery. An acknowledged timestamp cannot disagree with that
attempt. Backward-compatible missing legacy timestamps remain unknown. Query
history on the persisted local order day, never the recovery invocation day.
The official KIS [overseas order-history example](https://github.com/koreainvestment/open-trading-api/blob/main/examples_user/overseas_stock/overseas_stock_functions.py)
defines order start/end dates in local time. We did not adopt Claude's
speculative wider date query: the source supports the existing order-date
contract, and an absent row still cannot prove a fill or terminal outcome.

A never-sent intent blocked by an existing open order stays `intent_recorded`.
It does not adopt that order or gain cancel authority over it. Normal expiry,
exposure checks, serialization and no-resubmit for actual unknown submissions
remain. The private-state reader accepts and validates the optional timestamp.
This is recovery correctness, not a global permission or profitability gate.
Claude returned `supported-with-limits`; atomic file fsync/replace ordering,
time-field agreement, legacy ambiguity and expiry have focused coverage.

The separate FirstRate open/open CPU comparison links prior trial hashes and
labels all reused history development. Claude initially requested stronger
purge/censoring/parity evidence; explicit tests resolved this to
`supported-with-limits` before data dispatch. Its completed 48 cells authorize
no winner, holdout, GPU allocation or Paper consumer. A later distinct finite
research question remains possible under the reset; results are not rewritten.

## 2026-09-22 - Retire repeated diagnostics, preserve operational schedules

On the operator's explicit approval, disable the exact exhausted historical
backfills (3/3 and 2,119/2,119 terminal targets), finite stability/prefix studies,
recurring immediate-cancel quote smoke, and expired Cboe one-shots. Preserve
all data, private intents, receipts and explicit recovery commands. The actual
daily-SPY Paper task, current-data collectors and account observer remain;
account refresh pace is not reduced without freshness/load evidence. NAS forward
remains owned but its cache-unavailable failure needs scoped recovery, not a
fabricated quarantine/terminal classification.

The existing QQQ/SPY host runner now routes to v2 services and v2 guard receipts;
v1 remains quarantined and untouched. This is a two-ETF market-data path, not a
broker/accounting state migration. D1 has a fresh first observation and keeps
today's final later opportunity; both triggers expire at midnight. A missing
later result closes this bounded study as incomplete, not a reason to extend
it indefinitely or pause the company goal.

The default installer selects six operational jobs; explicit named reinstalls
preserve disabled/expiry state and do not replace a running task or build over
its image tags. Host rollback fields are under
`D:\thericher-v2\model-artifacts\ops\schedule-cleanup-20260922`.
Claude returned `supported-with-limits`: do not remove the only recovery owner,
equate exact cursor exhaustion with unlimited provider reach, or silently
reactivate a retired task. Execution retains unresolved-intent recovery.

An independent review probe unexpectedly re-registered eight existing tasks
when PowerShell module auto-loading escaped its mocks. The orchestrator stopped
the review, restored their original trigger start anchors from the prior safe
inventory, and rechecked task enabled states, expiry, timing and principal SID
equivalence. Last-run timestamps remained unchanged and no task was observed
running; this is Scheduler evidence, not a raw broker audit. The checked-in
test harness now disables module auto-loading after importing only standard
Management/Utility modules. No credential/live access or intentional broker
invocation occurred. Safe corrective facts are `rechecked-after-review.json`
in the same external directory; no task, private state or data was deleted.

## 2026-09-22 - Persist exact cumulative Paper fills in the existing store

Advance Paper accounting using the existing full original-order-date history
query and atomic private canary state, not another worker/report/permission gate.
Bind the unique direct row to its intent; never aggregate amendment lineage or
infer a fill from cancellation/absence. Persist cumulative quantities/amounts
once per exact identity, including before cancellation and recovery requery.
Keep last accepted totals on regression but expose current contribution only
after a current matching observation. Public receipts remain categorical.
Gross execution consideration excludes fees and settlement; orderable funds
cannot stand in for cash. No profitability or Paper promotion rule is added.

Official field reference:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/chk_inquire_ccnl.py
Claude's tool-disabled challenge returned `supported-with-limits`: preserve
per-order identity, distinguish stale/conflicting reads, and test amount units.
Resolution: the existing immutable per-run intent plus order/date identity
prevents cross-order inheritance; observation status/time are persisted, and
USD amount/quantity/price consistency is checked before accepting contribution.
This is not real-fill calibration, a terminal-cancel proof, or settled cash.
Independent source review additionally caught intermediate-read loss and a
progressing-clock issue; both have regression tests. No real broker action was
needed to implement the adapter. Explicit fillable SPY execution remains next.

## 2026-09-22 - Explicit fillable SPY cycle, separate from the canary default

Add a named SPY buy-one/sell-one execution baseline to the existing session
entry point. Its transient price uses fresh ask/bid and directional tick
rounding. The existing nonmarket/immediate-cancel command is unchanged. Reuse
the shared canary/session locks, durable intents and original-date cumulative
fills, not a second order ledger. A private account-bound cycle identity owns
only its two legs. The active SPY binding prevents another new SPY intent from
consuming that inventory between visits; existing reconciliation/cancellation
and other symbols remain independent. Unrelated historical unknown states
are not a new global permission hold.

Claude's two supplied-facts, tool-disabled challenges returned
`supported-with-limits`. Implement the exact-account binding, cross-cycle
exclusion and bounded old-order containment; classify inconsistent account/fill
facts narrowly rather than guessing. A finite owned invocation may reuse the
disabled quote-task registration with a wholly replaced one-time trigger and
settings. A container-local deadline must outlive neither a killed host wrapper
nor its task limit. No new recurring task or live route is authorized by this
decision. Actual deployment/dispatch facts belong in RUNBOOK and Execution.

The official REST example returns separate output1/2/3 objects:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_asking_price/inquire_asking_price.py
One bounded SPY Paper quote structure call on 2026-09-22 confirmed the clock,
last and scale in output1, with pbid1/pask1 in output2. Only field-presence facts
were output; no raw price, account/order call or order was made. The new book
parser follows that measured shape; missing book fields leave the legacy
last-only path usable. Fills remain unobserved until an actual session result.

## 2026-09-22 - Initial ten-percent strategy-Paper allocation

The operator explicitly approved approximately 10 percent of virtual cash for
actual strategy-Paper iteration. This improves the Paper/PnL learning loop, not
the size of the immediate roundtrip diagnostic. Standing Paper authority was
already sufficient; no profitability, D1 or renewed manual approval is needed.
The chosen interpretation is one initial aggregate allocation, not repeated
10-percent-per-order spending. `AGENTS.md` owns its sizing semantics. The
existing daily baseline needs quantity/reservation/owned-inventory integration;
this decision does not deploy that implementation or complete the lifecycle.

Claude's supplied-facts, tool-disabled challenge returned
`supported-with-limits`: use a literal provisional orderable-funds denominator,
account for concurrent entry cost plus pending buys, and reserve atomically with
durable intent ownership. Its assertion that the inherited position was SPY
was unsupported by the supplied facts. The second actual read-only check
confirmed neither SPY nor QQQ; do not turn that assertion into durable evidence.
Orderable funds are not settled cash or equity. Official field reference:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_psamount/chk_inquire_psamount.py
No private amounts, raw account rows, credentials or identifiers were supplied
to Claude or stored in this decision. Existing holdings are not silently sold
or adopted by a new strategy. Live authority remains unavailable.

## 2026-09-22 - Bind the daily strategy to its initial Paper allocation

Implement an opt-in budget mode in the existing daily SPY session, with a
scoped host launcher replacing that task's raw Compose action. Do not add a
recurring scheduler or enlarge the diagnostic buy/sell-one cycle. Existing
baseline direction is retained, but the new allocation policy is explicitly
separate from the baseline's old proposed exposure and historical fixed-lot
results. No profitability claim or model promotion follows.

One private account-bound funding record references the existing durable
intents. Recompute actual entry cost and residual buy reservations, rather
than maintaining a second fill ledger or repeatedly adding snapshots. Sales
release entry cost, not sale proceeds; the initial allocation is never topped
up from profits. Persist intent/reservation under the existing writer locks
before any POST. A possible prior side effect remains an exact recovery,
never a replacement order based on a new signal. Safe signal receipts are
retained for decision attribution, without raw prices or account amounts.

Claude's supplied-facts challenge returned `supported-with-limits`, raising
price-basis, inherited-position and crash-before-ack ambiguities. Resolution:
the cap is a frozen constant, entry cost is actual bound fill consideration,
and projection tests cover price improvement/repeated roundtrips. Initial SPY
must be flat; later account quantity must match owned fills. No inherited SPY
is adopted. Unknown POST identity cannot be manufactured from absent history,
and only that owned exposure stays under reconciliation. The reviewer found
no additional confirmed critical issue in its scoped source pass; it did not
independently rerun the final tests.

Retain optional exact `nccs_qty` in the existing private cumulative observation
without changing legacy payloads. Its absence is unknown, not zero. A fresh
bound zero remainder, no open order and matching position can close a partial
order; cancellation acknowledgement alone cannot. Official field reference:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/chk_inquire_ccnl.py
No live route, account reset, new credential class or real-money sizing is added.

Actual Docker deployment testing found the existing path validator rejected
the real `/app/private/canary` volume as repository storage. Accept exactly
that path only when its `/app/private` parent is an actual mount; retain the
host ignored-path exception and reject other repository directories. Mounted
and unmounted regressions plus the actual rebuilt-container probe cover the
fix. This changes no credential or broker authority. Final authority passed
3,903 tests / 19 skips with eight workers; 42 source hashes match across the
seven private-state consumers. The existing daily task's scoped launcher and
25-minute deadline are deployed with its trigger/principal unchanged. Preview
and installation are not actual strategy orders, fills or accounting evidence.

## 2026-09-22 - Expand research cohorts without changing tonight's Paper strategy

The operator requested all three parallel steps: expand usable training
samples, compare costs/holding frequency across rule/ML/DL models, and inspect
tonight's real virtual-account results. The previous 1,024-point TRAIN cap
sampled a full 24-hour grid before eligibility. A linked, separately frozen
development matrix uses all regular-session M5 training windows instead;
48 eight-epoch LSTMs and 24 Ridge fits share two folds, fixed contexts12/36,
30/60/120-minute horizons and the same cost bands. No source acquisition,
runtime replacement, winning-cell selection or Paper model replacement.

Claude's supplied-facts/tool-disabled challenge was `supported-with-limits`.
Resolution: timestamp start/end convention stays an explicit uncertainty;
seeing a 09:30 row would not independently verify it. Purge uses the first
scheduled EVAL decision minus the maximum 180-minute history, not the decision
itself. The 6-bps threshold is a fixed rule carried from earlier development,
not a breakeven assertion; a 5-bps/side cell is not necessarily negative by
construction since predictions can exceed the threshold. Report actual costs
and every cell without a promotion or independent-skill claim.

The night follow-up is a single thread heartbeat after the existing tasks,
not another order worker or Windows schedule. It separates signal, submission,
fill, inventory reconciliation and unresolved fees/settlement/net PnL.

Independent source review identified that wholly absent future payoffs could
otherwise appear as a successful zero-return comparison. After every model
decision is fixed, require 32 scored rows/eight disjoint-history blocks and
retain safe support counts on failure. The runner now preserves allowlisted,
identity-bound failure categories instead of replacing them all with a generic
error. The v1 metadata-only contract was recorded abandoned before any data
phase, and v2 freezes these corrections; no observed outcome chose the change.
Two delegated agents encountered service capacity failures. Main inspected
and integrated their existing runner/tests and completed the missing cohort
tests, rather than treating their unfinished narrative as evidence.

## 2026-09-22 - Prefer TimesFM 2.5 for reusable personal research

The operator asked whether solo noncommercial use permits TimesFM 3.0 and
delegated the choice. The actual 3.0 weight license defines permitted purposes
more narrowly than "not selling software": research/evaluation not tied to
commercial gain, production deployment or revenue generation. Its exclusions
include revenue-generating activity and production systems; restrictions also
cover outputs and fine-tuned derivatives. Personal ownership alone therefore
does not establish permission for an operational trading engine. This is not
a legal ruling that every private offline experiment is prohibited. A strictly
noncommercial/nonproduction experiment can be different, but do not assume
its outputs can then be transferred to a profit-seeking trading path.

Select official `google/timesfm-2.5-200m-pytorch` revision
`1d952420fba87f3c6dee4f240de0f1a0fbc790e3` under its Apache-2.0 model-card
license, which Google's repository explicitly confirms remains applicable
through 2.5. The model repository has no separate LICENSE file; do not claim
one was inspected. The pinned `timesfm==2.0.2` wheel independently contains
the Apache-2.0 license and uses safe tensor loading. Keep notices and hashes
with the external artifacts. No TimesFM 3.0 weights/code are acquired or used.

Official sources inspected:
- https://huggingface.co/google/timesfm-3.0-pytorch/blob/main/LICENSE
- https://huggingface.co/google/timesfm-2.5-200m-pytorch/blob/1d952420fba87f3c6dee4f240de0f1a0fbc790e3/README.md
- https://github.com/google-research/timesfm#license-notice-for-pretrained-weights
- https://pypi.org/project/timesfm/2.0.2/

Claude's supplied-facts, tool-disabled verdict was `supported-with-limits`:
distinguish a license-compatible offline study from operational/profit use,
verify the runtime license separately, and do not treat synthetic inference
as accuracy or profitability. Two reviewer inferences are not adopted:
authentication/gating alone would not disprove an Apache license, and a later
use does not automatically establish retroactive breach of a prior experiment.
Codex chooses 2.5 to avoid the unclear downstream scope without an approval wait.

This package advances public-model research integration only: pinned external
assets, an offline CPU/CUDA adapter and a bounded synthetic inference check.
The existing Torch/CUDA base and all Paper images/schedules stay unchanged.
Pretraining market overlap is not verified, so no market comparison or Paper
input follows from this runtime result. Next predictive breadth should compare
LightGBM and existing TCN/compact attention against matched controls on the
same payoff/cost contract, not describe more LSTM configurations as model-family
diversity. Public-model forecast benchmarking needs its own applicable source
and temporal-scope interpretation; it does not hold those locally trained
comparators or the scheduled KIS Paper baseline.

## 2026-09-22 - Compare model families with matched development controls

The next predictive breadth package fixes H30/context36 and reuses the prior
full regular-session cohorts, TRAIN-only normalization, purge and local-paper
cost semantics. Four LightGBM models and sixteen TCN/compact-Transformer models
are new; eight existing LSTMs are reloaded. This compares architectures without
silently reopening the closed LSTM window/horizon matrix. It remains seen-data
development, not independent validation, a selected winner or a Paper input.

LightGBM4.6.0 uses the official MIT license:
https://github.com/lightgbm-org/LightGBM/blob/v4.6.0/LICENSE
Parameter semantics: https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html
Its pinned wheel stays external and is installed offline without dependencies
into an ephemeral research container. Torch must load first for its bundled
OpenMP; native wheel loading needs an executable tmpfs. Neither fact requires
replacing the runtime or changing Paper dependencies.

Claude's falsification-first verdict was `supported-with-limits`: keep seen-data
and clock/action limitations, chronological exit-based purge, deterministic
single-thread CPU work, no evaluation-driven tuning, and whole-phase failure on
preemption. The five-layer dilated TCN is explicitly a new arm; the old single
kernel3 layer would not consume the full36-bar context. Compute is fixed epochs,
not equal parameters/FLOPs. We reject the suggestion that offline inference
requires baking the wheel into the base image: a hashed read-only mounted wheel
and offline temporary installation were actually tested. Before dispatch,
independent reviews led to normalizer/cohort checks, exact fold identities and
returned CUDA-to-CPU summary binding. No new gate, scheduler or authority role.

## 2026-09-23 - Repair actual Paper clock and history representation mismatches

The first budget decision reused its first-attestation time; strict availability
correctly rejected equality. Re-sample the actual decision clock after loading,
as the non-budget path already does. Fixed or future clocks still abstain; no
epsilon, backdating or relaxed predicate. The actual CLI leaves injected clocks
unset and no load occurs between the new sample and evaluation. Claude returned
supported-with-limits. This corrects chronology, not permission or model quality.

The existing one-share buy was acknowledged but twenty visits could not bind
its history. A read-only same-day probe found one page/row, zero literal/trim
matches and one positive numeric-only match with date, instrument, exchange,
side, currency and requested quantity all matching. Safe evidence:
`D:\thericher-v2\model-artifacts\execution\kis-paper-spy-fill-cycle\e6ad99be327e7ece5fb77ca234f75d9c2fbf266277cabbf0221a7d44b5204866\history-capability-20260923.json`.
The first diagnostic returned an uncategorized failure; the second completed
history but reached a read-only snapshot error. Neither established an account
or fill result. The final successful probe is history-only.

Official KIS examples confirm mock VTTS3035R, exchange-local query dates,
blank mock filters/order ID and M/F -> N continuation, but do not document an
ID-padding equivalence rule:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/inquire_ccnl.py
The repair is therefore measured private-Paper compatibility, not a universal
provider guarantee. Permit only positive ASCII-decimal leading-zero aliases
in history matching. Preserve raw acknowledgment IDs, hashes, cancel arguments,
full fill-field validation and ambiguous-row rejection. Capture already preserves
zeros; this was not local integer coercion. No global identity migration.

Claude returned supported-with-limits and an independent static review found
no blocker. Do not adopt two inaccurate reviewer suggestions: unknown evidence
is not itself ledger corruption, and partial fills need not fail because the
requested quantity is checked separately from filled quantity. Keep the earlier,
conservative multiple-row ambiguity check; do not silently choose one row by
discarding conflicting identities. The retained probe records the alias count;
actual runtime fill/reconciliation remains separate evidence, not inferred here.

The corrected same-cycle resume at 15:32Z still returned evidence_unavailable.
A separate single snapshot attempt at 00:36:48 KST was auth_rejected before
account parsing. Keep these observations distinct; neither proves the earlier
cause. The official balance example distinguishes mock NASD/NYSE/AMEX queries
from live NASD's all-US behavior, so a guessed duplicate-exchange explanation
does not justify changing the current Paper query pattern:
https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_balance/inquire_balance.py

Final verification passed 718 non-overlapping changed-path serial cases and
4,405 full cases / 19 skips with eight workers in 339.16s, helper exit zero.
The earlier full run passed assertions but failed cleanup on two fixture-owned
hardlink names. Add a finally-unlink teardown to that existing TimesFM test;
do not weaken the cleanup guard or delete the retained failed run manually.
The focused helper rerun passed 90 cases with cleanup before full authority.

## 2026-09-23 - Preserve reported venues in Paper balance reconciliation

An exact same-order capability probe confirmed auth and history worked while
the NASD balance parser rejected a valid positive row from another US venue.
All required fields were present, prices positive and currency USD; no raw row
was retained. A later three-query probe completed NASD/NYSE/AMEX and confirmed
the original full fill matched reported holdings. Official sample documentation
describes Paper filters as venue-specific, so record this as measured private
compatibility, not a general promise that NASD alone supplies a complete account.
Source: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_balance/inquire_balance.py

Keep all query/pagination completeness checks. Preserve actual allowed venue;
do not relabel or drop holdings. Reject within-query/page duplicates. Across
completed query groups merge only identical identity, currency, quantity and
average acquisition price. Keep the first valid indicative market mark; a
sequential mark change alone does not change inventory identity. Fresh bid/ask,
not this mark, still sets order prices; the budget uses orderable funds and
exact owned fill costs. No snapshot mark feeds these execution sizing paths.

Claude twice returned supported-with-limits. Accept its sequential-price
objection to full-row equality. Do not claim mark divergence was measured in
this probe, that every rule only tightens validation, or that retained marks
have independent exchange timestamps. Snapshot time is capture timing, not
an atomic valuation timestamp. Do not add an uncalibrated divergence threshold,
new timestamp subsystem or approval gate. Existing invalid-price/identity/
conflict checks remain. Tests cover both mark-only variation and hard conflicts.
Read-only recovery then persisted the exact buy fill and matching position.
The existing finite cycle opportunity moves to tonight with its same identity;
no replacement order, changed budget, recurring expansion or live behavior.

## 2026-09-23 - Isolate redundant turnover under unchanged model decisions

The linked persistent-position study uses existing H30/context36 LSTMs and
fixed naive/rule controls, with no training, tuning, GPU or sealed evaluation.
Only adjacent selected intervals in the same session merge. Both policies have
identical exposure, gross payoff, terminal times and post-decision common
session censoring. Net improvement must exactly equal eliminated boundary fees.
Claude returned supported-with-limits: that improvement is an accounting
identity; measured boundary counts are empirical, not a newly discovered alpha.
Retain planned/scored/censored support and matched-parent controls. This is
seen-data development, not a model selection or a Paper-strategy replacement.

## 2026-09-23 - Isolate NAS overlap conflicts by target

The owned NAS receipt proved a stored/incoming AAPL duplicate conflict, not
corrupt retained bytes. Catch only that exact merge error per target; retain
the original snapshot and categorical failure while committing independently
valid targets. Base-load/corruption/publication failures still abort. Preserve
the fixed universe, atomic index, request pacing and scheduler. A partial run,
preflight and forward projection must not treat a deferred target as fresh.
Claude supported this with limits. Do not adopt its suggested ban on a second
attempt receipt or all metadata generation changes: immutable attempt evidence
and failure counters remain legitimate, but never count them as new rows.
The bounded deployed attempt found all6 conflicts, so no coverage advanced.
Do not infer the correct value or reset old snapshots from that observation.

## 2026-09-23 - Retain NAS revisions without discarding new sessions

The owned collector opts into immutable whole-page revision retention. The
first-retained view keeps old overlap values and appends unseen dates; it is
not a point-in-time table. The same atomic index binds each distinct incoming
snapshot, its conservative local recorded-at time and its prior snapshot.
Readers verify both versions. Equal-page retries do not create another vintage.
The legacy predictive projection remains deferred for this contradictory view;
an exact hash-bound whole-page reader permits explicitly observed developmental
use only at or after recording, without a finality or historical-PIT claim.
Collection, unrelated research and Paper continue. No existing history is reset.

Claude returned supported-with-limits. Accept the warning that retained data
is not qualified data and that timestamps and corruption checks matter. Reject
unmeasured magnitude/count tolerances or repeated-agreement auto-finality:
they neither prove correctness nor justify another collection gate. NAS here
means the exchange code, not a network filesystem; existing local locking,
immutable creation, hash checks and atomic-index publication are retained.
