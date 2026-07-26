# Next Codex Goal

## Objective

Integrate the tested KIS Paper intraday session-capture worker with the one
existing intraday-head task.

This is a bounded Data/Infra integration: make the existing scheduled head
collector use the tested capture mode while preserving source provenance,
recovery, and the isolated offline-observer handoff. It is not a new scheduler,
historical-pagination claim, model decision, order, or live behavior change.

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

1. Ask Claude CLI for a concise falsification-first drift-check before changing
   the profile/dispatcher. State the claim, kill case, source/provenance risk,
   current task/profile, observer isolation, blast radius, and reversal fact.
   An expired CLI session is scoped tooling evidence, not a hold on this
   authorized private change.
2. Change only the existing `thericher-kis-paper-intraday-head` profile/task
   path to use `--mode session-capture`. Keep its existing triggers, named
   task, concurrency behavior, execution limit, maximum page count, one-client
   collector, lock, request gate, cooldown, strict conflict rule, and `tr_cont`
   continuation contract. Do not create a scheduler or task.
3. Preserve the current Data-to-Research handoff: after an eligible QQQ
   collection, its isolated metadata-only preparation and network-disabled
   observer remain available; partial or extended-session capture data remains
   Data-only evidence. The collector exit remains authoritative, and observer
   failure must not rewrite collection freshness or recovery.
4. Keep raw rows, manifests, provenance, deduplication, cursor/recovery state,
   and capture receipts only under `D:\market_data`. Keep generated artifacts
   outside Git. Do not print paths, rows, prices, credentials, account data, or
   sealed holdout labels.
5. Add focused profile/dispatcher tests proving the one existing task invokes
   the capture mode, no duplicate schedule or widened KIS route exists, the
   collector is still one-client/concurrency-one, and the offline observer is
   isolated from KIS credentials and network access.
6. Reattest the Docker profile and source-safe metadata without a market-time
   wait. A later scheduled run is operational evidence; it is not a reason to
   delay this bounded integration.

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

The prior worker drift-check and retry on 2026-07-26 KST found the local Claude
CLI OAuth session expired; no private material was sent. Retry for this
profile/dispatcher change before relying on it. A repeat OAuth failure is
scoped tooling evidence, not an approval gate for this private non-live work.

## Completion Evidence

- Test-backed existing profile/dispatcher integration with no duplicate
  scheduler, widened broker route, or observer-to-collector feedback path.
- Reattested Docker/source-safe metadata evidence and an explicit statement of
  what a later scheduled run must prove.
- Stateboards, RUNBOOK.md, HANDOFF.md, and DECISIONS.md reflect the integration
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
