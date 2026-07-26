# Next Codex Goal

## Objective

Implement the first measured KIS Paper intraday session-capture worker.

The worker turns the observed terminal-head behavior into a Data-owned,
recoverable source path. It is not a claim that KIS supports historical
pagination or continuous sessions yet, and it must not make a model, order, or
live behavior decision.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, DECISIONS.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest the existing source-safe head coverage without a KIS call:

~~~powershell
uv run python scripts\inspect_kis_intraday_head_coverage.py
~~~

## Required Work

1. Build the Data-owned worker on the existing KIS Paper market-data client.
   Each bounded invocation creates exactly one in-memory client/token and has
   concurrency one. Keep the current request-start gate and cooldown intact.
2. Use `tr_cont` as the only pagination authority. When continuation is
   present, use the validated cursor path. When a response is terminal, collect
   only current-head data and never invent a historical `KEYB` cursor.
3. Keep raw rows, manifests, provenance, deduplication, cursor/recovery state,
   and coverage data only under `D:\market_data`. Retain strict source conflict
   rejection. Report only source-safe status, coverage, and recovery facts.
4. Classify each attempted regular session against the exact 390-minute
   contract. A partial or gapped terminal-head result must remain partial; do
   not fill it from another provider or turn it into a prospective input.
5. Add focused fake-transport tests for client/token lifetime, continuation and
   terminal behavior, bounded recovery, strict conflict handling, coverage
   classification, no broker/account/order/live route, and external-only data
   storage. Use a temporary external root in tests where appropriate.
6. Run one bounded KIS Paper Data-only smoke after tests pass. It may use only
   the Paper token and market-data endpoints. Do not call account, position,
   order, or live endpoints, print raw rows/prices, or wait for a market
   session. A retry/due time belongs to the worker and cannot block another
   ready lane.
7. Do not create a duplicate scheduler. The existing head task may consume the
   worker only when its tested source/provenance/recovery contract remains
   intact; otherwise leave installation for a later bounded goal.

## Hard Boundaries

- Keep raw market data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- KIS Paper market-data access is authorized. Do not read `KIS_LIVE_*`, enable
  live behavior, or call KIS account, position, order, cancel, or modify
  endpoints in this goal.
- Do not print, log, commit, or send secrets, account identifiers, raw broker
  payloads, raw prices, or sealed holdout labels to Claude.
- Do not loosen the existing rate/cooldown controls, parallelize KIS requests,
  infer historical reach from a terminal page, or make model/promotion/Paper
  order claims from this Data result.

## Claude Check

A falsification-first drift-check for this worker was attempted on 2026-07-26
KST, but the Claude CLI OAuth session was expired and no private material was
sent. This scoped tooling failure does not block the Data-only objective. Retry
Claude before a material scheduler widening, model promotion, ensemble
selection, holdout interpretation, or execution-risk change.

## Completion Evidence

- Test-backed, source-correct single-client worker with a bounded recovery
  contract and no widened broker route.
- One source-safe Data-only smoke result or a scoped, recoverable provider
  failure record.
- Stateboards, RUNBOOK.md, HANDOFF.md, and DECISIONS.md reflect actual coverage
  and the next falsifiable data question.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Data-local rate wait or partial session does not stop
another ready lane.
