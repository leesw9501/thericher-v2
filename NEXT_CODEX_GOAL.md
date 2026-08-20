# Next Codex Goal

## Objective

Complete `kis-paper-d1-prospective-observation-pair-result-v1`: independently
reattach and validate the first complete QQQ/SPY D1 two-observation result
emitted by the installed task-owned observer for one exact completed session.
The result may only classify that session as `measurement_only_match`,
`input_unavailable`, or `disqualified`; it never qualifies a dataset or
promotes a model, GPU campaign, Execution input, Paper order, or live behavior.

## Context

- The installed task is `thericher-kis-paper-d1-prospective-observation-pairing`.
  It owns the `08:15` and `23:20` KST Tuesday-Saturday opportunities.
- Its state and immutable, source-safe receipts are under
  `D:\thericher-v2\model-artifacts\data\kis-paper-d1-prospective-observation-pairing\v1`.
- It observes only the existing isolated QQQ/NAS + SPY/AMS v2 cache through
  the KIS Paper `dailyprice` route. The cache stays read-only to this work.
- The implementation smoke was `not_due`; no actual pair result exists yet.

## Boundaries

- Do not manually invoke the task, Docker service, KIS client, collector, or
  scheduler. Do not poll in the foreground.
- Read only source-safe Task Scheduler facts and source-safe state/receipt
  fields through the existing offline reader. Never print or retain raw rows,
  credentials, account identifiers, request/response bodies, or private state.
- Never read, route, or mention `KIS_LIVE_*`. Do not use account, position,
  quote, order, or broker endpoints.
- A missing, incomplete, invalid, or mismatched result applies only to the
  bound session. It must not become a general Data, Research, Execution, or
  Paper hold.
- Do not change the v1 quarantine or write, clear, relabel, or copy either
  cache lineage.
- Do not create a feature, target, model, training run, GPU appointment,
  backtest, intent, Paper order, public service, or live behavior.

## Required Work

1. Run `scripts\start_next_codex_task.ps1`, then read the current handoff,
   policy, runbook, and Data, Engine Research, Execution, and orchestration
   stateboards before inspecting a result.
2. Reattach only a fresh complete result through
   `read_current_kis_paper_d1_prospective_observation_pairing_outcome`. It must
   validate the hash-bound current pointer plus the same source-contract hash,
   completed-session key, target set, first-receipt identity, and immutable
   receipt identities. Treat any missing or invalid link as scoped
   `input_unavailable` or `disqualified`, never as a success. A
   `first_recorded` pointer is incomplete; only a validated `later` receipt is
   a two-observation result.
3. If no complete result is present, preserve the worker-owned `next_due` and
   dispatch or continue a ready non-conflicting package. Do not foreground-wait
   or manufacture a retry/schedule.
4. Before relying on an actual result, ask Claude for a concise
   falsification-first review of the exact measurement claim. Record only its
   categorical verdict and the evidence pointer; `uncertain` or
   `review_unavailable` narrows this result alone.
5. Refresh the stateboards, `HANDOFF.md`, and `RUNBOOK.md` with source-safe
   evidence. Run required verification for changes, commit, push, and replace
   this file with exactly one next material company objective.

## Strongest Kill Test

Any absent target, corrupt or unbound first receipt, changed source contract,
different session key, or changed canonical row hash disqualifies the exact
session. A hash match alone proves neither decision-time availability, provider
finality, corporate-action status, nor a predictive-use qualification.

## Verification

~~~powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
~~~
