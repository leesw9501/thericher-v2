# Next Codex Goal

## Objective

Build `kis-paper-m1-current-head-duplicate-recovery-v1`.

Repair the exact QQQ/NAS and SPY/AMS current-head collector recovery path that
currently terminates as `rejected/minute_duplicate_conflict`. Preserve a
compatible existing causal head and immutable provenance so the already-owned
future scheduler invocation can retain a valid forward observation when source
data is compatible. This is recovery engineering only: it does not claim
historical reach, finality, point-in-time availability, data qualification,
prediction, profitability, or Paper readiness.

## Hard Boundaries

- `KIS_PAPER_*` may be read only through named Paper-owned paths. Never print
  or persist credentials; never read or route `KIS_LIVE_*`.
- Do not call account, position, quote, order, cancellation, or any live route.
- Do not create, duplicate, manually invoke, or retime the existing QQQ/SPY
  scheduler, Docker service, cache root, cursor chain, or collector. Its next
  task-owned invocation remains the only actual KIS collection owner.
- Preserve existing raw snapshots, manifests, cursors, immutable terminals, and
  source-safe receipts. Do not delete, rewrite, relabel, or infer missing
  historical provenance. A conflicting candidate must remain non-promoting.
- Use visible shared-worktree WIP only after reattesting its precise contract;
  unowned provenance alone is never a block and does not justify staging or
  changing unrelated IWM/backfill work.
- Do not create a recurring scheduler, broad backfill, model, research
  campaign, GPU job, dataset qualification, local-Paper intent, broker order,
  public service, or mutable latest-record rule.

## Required Work

1. Run a concise Throughput Review. Confirm that both bounded M1 endpoint
   probes are terminal and that collector duplicate recovery, not another probe,
   is the next material Data bottleneck.
2. Ask Claude CLI for a short falsification-first drift check before changing
   duplicate, cursor, recovery, or immutable-provenance semantics. Send no raw
   rows, values, paths, or credentials; do not wait for the result.
3. Inspect the exact current terminal, capture binding, task contract, and any
   visible generic backfill WIP. Reattest the smallest owned recovery behavior
   with focused tests or replace only that bounded package.
4. Freeze the recovery contract: exact accepted-head preservation rule,
   candidate conflict rule, cache/manifest/cursor invariants, source-safe
   outcome taxonomy, restart behavior, strongest destructive-write kill test,
   and the later task-owned evidence that can prove a successful recovery.
5. Implement or reattest the smallest deterministic recovery. Add focused fake
   tests proving an identical conflict preserves existing bytes and cursor,
   compatible non-conflicting data appends exactly once, malformed or
   provenance-mismatched candidates fail closed, no task/KIS/credential path is
   needed for recovery tests, and source-safe results remain replayable.
6. Run CPU-only fake/local smoke and a read-only scheduler/task preflight only.
   Do not manually trigger the task or call KIS for this objective. Reattach any
   already-produced task-owned source-safe evidence without a mutable-latest
   fallback.
7. Refresh Data and orchestration stateboards with the exact recovery contract,
   current scheduled owner/due fact, and the next recovery or collection action.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Recover KIS Paper M1 duplicate conflicts`
