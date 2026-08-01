# Next Codex Goal

## Objective

Add the first pure target-exposure allocation stage for the engine.

The existing target-position policy proves how a caller-owned opportunity and
completed-bar model evidence can produce a target state. This bounded objective
adds the separate third decision stage: constrain or scale that proposed target
against caller-owned portfolio capacity and per-symbol limits, with no default
alpha, broker route, or external state.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   stateboards.
2. Reattach the completed QQQ consensus selection-null receipt only as closed
   evidence. Do not reuse it to tune, select, size, or promote a model.
3. Ask Claude for one short falsification-first drift check before changing the
   target-position contract. A timeout is `review_unavailable`, not support or
   a general hold.

## Work

1. Define a small caller-owned allocation input and pure output contract that
   can cap or scale an otherwise eligible `TargetExposureProposal` using only
   declared current portfolio exposure, available capacity, per-symbol cap,
   and bounded confidence/risk multipliers. Invalid, stale, inconsistent, or
   capacity-exhausted inputs must produce a categorical no-increase result.
2. Keep selection and sizing separate: the allocator must not read data,
   select symbols, infer confidence, choose model weights, manufacture an
   alpha signal, or create a default exposure. It must not change the existing
   frozen consensus policy or its artifacts.
3. Prove entry scaling/capping, no-op hold, exits, exhausted capacity, invalid
   inputs, deterministic identity, and the absence of credential, network,
   KIS, broker, order, artifact, and GPU access. The output may compose with
   the existing local-paper preparation bridge in a unit test only; it must not
   create a KIS Paper action or modify the scheduler.
4. Record the narrow contract and recovery facts in the appropriate stateboards
   without adding a report, gate, queue, or new durable role.

## Completion

- A pure, deterministic allocation stage exists with focused tests and no I/O.
- The fixed QQQ family remains closed and unpromoted.
- No GPU experiment, KIS call, credential read, broker action, or generated
  model artifact is created.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue. The scheduler remains an independent lane.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add target exposure allocation foundation`
