# Next Codex Goal

## Objective

Restore readiness-driven throughput for the first KIS-compatible Paper trading
loop. Advance Data, Engine Research, and Execution in parallel from existing
KIS evidence while measuring the exact KIS intraday capability needed for
continuous collection.

The prospective first-five QQQ 1m pair remains a prerequisite only for its
pair-bound prospective observation, prospective campaign, and any later
promotion that explicitly depends on it. It is not a global hold on historical
Research, Data collection, local simulation, or Paper execution preparation.

## First Reads

1. Run:

~~~powershell
   .\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, DECISIONS.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest the current source-safe intraday baseline:

~~~powershell
   uv run python scripts\inspect_kis_intraday_head_coverage.py
~~~

## Parallel Work Packages

### Data

1. Run a bounded KIS Paper market-data capability probe through the owned
   market-data client. It may use KIS_PAPER_* only for market-data token and
   price endpoints; it must not call account, position, order, or live
   endpoints.
2. Record only source-safe evidence: route class, accepted-page count,
   continuation category, page-size/coverage category, response/error class,
   token reuse behavior, elapsed time, and the resulting calibration fact.
   Never print raw bars, prices, request headers, tokens, account identifiers,
   or response bodies.
3. Determine whether the existing 1m endpoint can produce contiguous
   regular-session capture, its usable historical range, and a measured
   request-start ceiling. Keep the existing cache source-separated and retain
   strict conflict rejection.
4. Propose one owned, single-client adaptive capture path after the probe
   establishes its route-specific facts. An implementation in this objective
   may preserve or strengthen the current rate/cooldown controls, but may not
   loosen or remove them. A later replacement needs its own evidence-backed
   decision. The path must reuse an in-memory Paper token for the worker
   lifetime, remain concurrency-bounded, and never become a parallel flood.
   The existing scheduled head remains a Data-local source while this work
   proceeds.

### Engine Research

1. Create a frozen historical KIS campaign contract using only an eligible
   source-separated dataset. State the target, feature availability time,
   chronological development/holdout split, cost model, naive baseline,
   metrics, stop rules, and artifact root.
2. Resume a CPU baseline and one bounded replication/comparison from the
   existing historical KIS daily or complete intraday input. Treat the prior
   GRU, LSTM, TCN, and compact-attention screens as descriptive evidence, not
   selected candidates.
3. Queue at most one GPU job after its campaign contract and data qualification
   are frozen. The job may test a defined hypothesis or replicate a candidate;
   it may not open a sealed holdout, create a Paper order, or claim a promoted
   model. Store every generated artifact under D:\thericher-v2\model-artifacts.
4. Keep the prospective first-five consumer/campaign path isolated. It becomes
   an additional observation input only when Data supplies its immutable pair;
   it does not replace historical validation.

### Execution

1. Keep local_paper, kis_paper, and kis_live routes separate. Do not read
   KIS_LIVE_* or create a live route.
2. Reattest and simplify the deterministic decision-to-target-weight-to-intent
   contract needed by a later eligible Research candidate. Model output remains
   untrusted input; sizing, route selection, persistence, and reconciliation
   remain Execution-owned.
3. Use existing authorized KIS Paper scheduled evidence and read-only
   reconciliation facts where useful. Do not create a Paper intent solely to
   manufacture activity or infer a fill/PnL from an absent or ambiguous record.

## Throughput Rules

- A Data rate/backoff wait belongs only to its worker. Codex advances the other
  two packages instead of foreground-waiting.
- No package may turn an unavailable source, incomplete prospective session,
  scheduled due time, no-intent result, or model result into a company-wide
  approval or progress latch.
- One GPU job runs at a time. Active Paper inference/execution reliability
  preempts training that could interfere with it.
- Commit only a bounded change backed by a behavior, contract, test, or
  measurement result. Do not commit a scheduler reattestation or document-only
  restatement as a substitute for engine progress.

## Hard Boundaries

- Keep raw market data in D:\market_data and generated artifacts in
  D:\thericher-v2\model-artifacts or /app/model_artifacts. Never commit either.
- Do not print, log, commit, or send credentials, tokens, account identifiers,
  raw broker payloads, raw prices, or sealed holdout labels to Claude.
- No paid data, paid service, unclear-rights asset, public service, or major
  runtime/framework replacement.
- KIS Paper is authorized for private work. KIS Live remains unavailable.
- Preserve source separation, point-in-time feature timestamps, chronological
  splits, and exact local_paper fill labeling.

## Claude Check

The required short drift-check for this governance change was attempted on
2026-07-26 KST. Claude CLI OAuth was expired, so no credentials, raw data, or
holdout material was sent. This is a scoped tooling failure, not a hold. Before
relying on a material scheduler widening, model promotion, ensemble selection,
holdout interpretation, or execution-risk change, retry the required
falsification-first check.

## Completion Evidence

- Source-safe KIS capability-probe result and an evidence-backed capture
  recommendation or implemented bounded path.
- A frozen historical campaign contract plus CPU baseline result; if a GPU job
  runs, its immutable artifact and scoped conclusion.
- A simplified, test-backed Execution integration contract with route isolation
  intact.
- Stateboards/HANDOFF reflect actual lane readiness rather than an external
  wait.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, integrate the three packages, commit and push their bounded
evidence, and replace this file with exactly one next company objective.
