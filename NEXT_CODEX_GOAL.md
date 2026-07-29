# Next Codex Goal

## Objective

Materialize the first full-breadth, source-local KIS Paper D1 coverage panel
from the active broad cache and compare it with the earlier generation-604
panel, while the collector and all Paper schedules continue independently.

The panel is a frozen coverage and lineage input for later Data/Research work.
It is not a point-in-time universe, corporate-action qualification, ranking,
training set, model, Paper signal, or broker action.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the mutable broad-cache index, its one-worker lock/task state, and
   the immutable generation-604 panel without printing raw rows, prices,
   symbols, credentials, account facts, or broker bodies.
3. Reuse the existing offline broad-panel materializer and continuity comparator
   rather than building a new cache or reporting framework. Ask Claude only if
   a proposed change would alter panel semantics, collection authority, or a
   later Research promotion boundary.

## Authority And Boundaries

- This objective is offline. Do not read credentials, call KIS, or change any
  Data/Paper task, collector pace, cache cursor, or shared request gate.
- Do not acquire data, mutate raw cache bytes, open the broad collector lock,
  run a model/GPU campaign, rank symbols, create a strategy claim, or create a
  Paper intent/order/canary/live route.
- Store the manifest only under `D:\market_data` and source-safe comparison
  receipts only under `D:\thericher-v2\model-artifacts`; never write raw rows,
  prices, volumes, credentials, or account facts to Git or artifacts.
- Read the mutable index twice around reattestation. If it changes, return a
  scoped retry/reconcile fact and yield to the next collector-free window; do
  not stop the collector or wait in the foreground.
- Preserve the 604 panel as immutable. A zero-mismatch overlap comparison
  establishes only retained-row continuity for its shared target/session rows.

## Work

1. **Data:** when the broad worker is not running, materialize one stable panel
   from the latest all-target-covered index generation using the existing
   source-safe materializer.
2. **Validation:** compare the new panel against the immutable generation-604
   panel and record aggregate shared/mismatched target and row counts. A
   mismatch is a nonzero, scoped lineage result; it does not repair the cache.
3. **Data:** add focused tests only if the full-breadth snapshot reveals a real
   materializer or continuity gap. Do not add a generic panel framework.
4. Refresh Data/Research/orchestration stateboards with the new panel identity,
   limitations, and next action. Replace this file with exactly one next
   objective, then continue. The existing broad and QQQ/SPY-forward tasks, and
   the scheduled virtual Paper quote session, must keep their own due times.

## Completion

- One external immutable full-breadth broad D1 panel manifest exists, or a
  source-safe scoped retry/reconcile receipt truthfully explains why it could
  not stabilize in this objective.
- The generation-604 overlap comparison has a source-safe external result.
- No KIS call, raw-cache mutation, model/GPU run, Paper intent/order, or live
  behavior occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Materialize broad D1 coverage panel`
