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
