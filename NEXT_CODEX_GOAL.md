# Next Codex Goal

## Objective

Close the bounded handoff from the existing scheduled KIS Paper intraday-head
collector to the already precommitted prospective QQQ research-readiness
preparer. Reuse the one existing `thericher-kis-paper-intraday-head` task and
its Docker service: after a completed head collection, run one sequential,
metadata-only preparation attempt. Before five complete QQQ regular sessions it
must record only a retriable pending fact; when the first five are available it
must use the existing preparation contract to create its external precommit and
planning receipt exactly once, then verify and reuse that same identity on a
later unchanged scheduled replay.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/orchestration.md`
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/review.md`

3. Ask Claude for a short falsification-first drift-check before coupling the
   collector to the preparation call. Do not send credentials, raw bars, cache
   paths, or artifact contents.

## Hard Boundaries

- Reuse the existing head task and Docker profile. Do not add a second Windows
  task, scheduler, polling loop, timer, service, queue, dashboard, or report
  family.
- The preparation call is metadata-only and must not make an extra KIS request,
  read a credential, open raw bar files, train a model, use GPU, emit a decision,
  or submit/modify/cancel a Paper order.
- Preserve the collector's own outcome: a preparation failure or pending result
  cannot invalidate a committed chunk, mutate its cursor, or turn a completed
  collection into a failure.
- Use the existing first-five chronological-session contract unchanged. Do not
  retune features, alter splits, add a model, inspect a sealed or burned region,
  or promote an ensemble.
- Generated receipts and any runtime evidence stay under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`, never Git. Do
  not expose raw rows, prices, secrets, account facts, or order identifiers.
- Mount only the existing external artifact root needed for the preparation
  receipt. A repeated unchanged head run must validate/reuse its existing
  receipt instead of failing on its presence or creating a duplicate.
- `KIS_LIVE_*` remains unavailable. Any KIS call may occur only through the
  existing Paper market-data collector under its standing authorization.

## Role-Owned Work

### Data Agent

1. Trace the current collector, Compose mounts, and metadata-preparer boundary.
2. Add the smallest sequential handoff that carries a deterministic safe run
   identity, reuses a verified unchanged preparation receipt, and preserves
   independent collection recovery.
3. Keep fewer-than-five-session readiness as a nonblocking pending fact and
   retain the existing cache/index semantics.

### Engine Research Agent

1. Verify that the handoff consumes only the existing first-five QQQ
   prospective contract and creates no model/GPU/candidate result.
2. Confirm the existing preparer's first-five and external-artifact invariants
   remain the only research side effect.

### Validation Agent

1. Use synthetic index/cache fixtures to prove pending, first-ready, verified
   unchanged replay, and preparation-failure behavior.
2. Prove no duplicate scheduler or KIS/order route is introduced and that a
   preparer failure leaves the collection result recoverable.

## Completion Evidence

- One existing scheduled head execution can perform the handoff without a
  second scheduled worker.
- Synthetic tests prove zero artifact before five complete sessions, exactly one
  external precommit/plan receipt for the first ready set, verified reuse on an
  unchanged replay, and no duplicate artifact.
- The collector result and cache/cursor remain authoritative when preparation is
  pending or unavailable.
- A focused offline/container smoke uses no credential or KIS call beyond any
  already-owned collector invocation.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Connect prospective intraday readiness handoff`
