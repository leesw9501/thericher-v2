# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-capture-cycle-v1`: one small local-cache-only
runner that invokes the existing 15:30 ET forward-input observer and the 15:45
ET forward-outcome witness at their exact due slots.

This improves the real forward-data loop while Engine work remains independent.
It is not a generic scheduler, provider client, or model campaign.

## Boundaries

- Ask Claude for one concise falsification-first check before changing the
  capture/outcome lifecycle or duplicate/conflict recovery semantics.
- Reuse the existing immutable observer and outcome-witness contracts. Keep
  their D:-only raw snapshot, source-safe artifact, duplicate, mutation, and
  conflict behavior authoritative.
- The runner may read only local KIS-shaped cache data. Do not call KIS, read
  `.env` or credentials, submit an order, access account/Paper routes, enable
  live behavior, download data, or start a persistent sleeper/service.
- Outside the exact 15:30 input or post-15:45 outcome slot, return a scoped
  no-op without writing a terminal unavailable record. A missing cache/input
  remains recoverable on a later invocation.
- Do not open targets, train models, allocate GPU, persist a model artifact,
  calculate PnL, or create a Paper intent.

## Required Work

1. Data: add one executable capture-cycle runner with an injectable observed
   UTC time. It must select at most one due observer action, use the existing
   local cache roots, and emit only source-safe summary fields.
2. Add focused fixture tests for 15:30 input capture, post-15:45 outcome
   capture, outside-slot no-op, idempotent retry, stale/mutated source
   containment, D:-only artifact placement, and import isolation from network,
   credentials, execution, and GPU/model routes.
3. Reattach the real local cache once without KIS calls. Record the categorical
   source-safe result, update Data/Engine/Research Steward/orchestration
   stateboards, and leave Engine's zero-pair receipt scoped to its own input.

## Completion Evidence

- a tested local-cache cycle runner with no long foreground wait;
- host and Docker read-only reattachment with matching source-safe result;
- no raw values, credentials, targets, models, or broker effects in Git or
  artifacts; commit, push, and replace this file with one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
