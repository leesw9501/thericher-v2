# Next Codex Goal

## Objective

Reattach the first automatic broad KIS Paper D1 panel-postprocess outcome and
record its source-local per-target chronology distribution for a later
date-based Research design, while the broad collector continues independently.

The result may establish only frozen coverage and lineage. It must not make a
point-in-time universe, corporate-action, ranking, model, ensemble, PnL, Paper
signal, or broker claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect the installed broad task, current source-safe index facts, the
   generation-604 manifest, and any external postrun receipt without printing
   raw rows, prices, volumes, symbols, credentials, account facts, or broker
   bodies.
3. Ask Claude for a short falsification-first check before changing panel
   completeness semantics, creating a date split, or making a Research
   eligibility claim. Treat a chronology distribution as an observation, never
   as a boolean eligibility result.

## Authority And Boundaries

- The postrun consumer is offline. Do not read credentials, call KIS, start or
  stop a collector, change a cache cursor/pacing gate, or launch a duplicate
  task.
- Do not mutate raw cache bytes or collector locks, acquire data, rank symbols,
  create a target/label, fit a model, run GPU work, or create a Paper
  intent/order/canary/live route.
- Preserve the automatic task boundary: the broad task itself owns collection
  and invokes postprocess only after its Docker collector returns zero.
- A missing postrun artifact is an external timing fact, not a foreground wait
  or a reason to weaken the two-index stability/coverage rules.

## Work

1. **Data:** when a postrun receipt appears, reattach its candidate panel and
   generation-604 continuity receipt through existing offline loaders. Confirm
   all receipt hashes, full non-quarantined breadth, non-regressing coverage,
   and zero retained-row mismatches.
2. **Validation:** record a compact, perishable external chronology observation
   with candidate identity, aggregate per-target span buckets, and limitations.
   Do not compute a global common-history threshold or `feasible` boolean: the
   shallowest and source-limited current survivors must not become a hidden
   Research eligibility rule. Retain no source rows, prices, labels, rankings,
   or model output.
3. **Research:** use only the observation to identify later design questions.
   Do not treat it as a campaign contract, create a split/target/label, fit, or
   dispatch a model in this objective.
4. If postrun is `retry` or absent, preserve the scoped source-safe fact and
   leave the collector running. Do not poll or sleep in the foreground; advance
   only already-ready non-conflicting work.
5. Refresh the Data/Research/orchestration stateboards, replace this file with
   exactly one next objective, and continue.

## Completion

- A source-safe postrun result is independently reattached as `complete` or
  its scoped `retry` reason is preserved.
- Any chronology observation remains external, offline, aggregate-only,
  perishable by candidate generation, and explicitly non-promoting.
- No KIS call, credential read, raw-cache mutation, model/GPU run, Paper
  action, or live behavior occurred in this objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Qualify broad D1 postprocess output`
