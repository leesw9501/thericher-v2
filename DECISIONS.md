# Decisions

This is append-only. New decisions go at the bottom.

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
