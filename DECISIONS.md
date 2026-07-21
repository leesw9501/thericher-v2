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
