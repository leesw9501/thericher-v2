# Next Codex Goal

## Objective

Build `kis-paper-canary-lifecycle-closure-v1`.

Close one eligible, existing KIS Paper virtual-order canary lifecycle as
source-safe operational evidence. The objective is a durable interpretation of
what the existing owned task actually did: no intent, intent only,
submitted/cancelled cleanly, or scoped unknown/recovery. It advances Paper
execution readiness, not strategy profitability or model selection.

## Hard Boundaries

- Use only the existing `thericher-kis-paper-quote-session` owned task and its
  established Paper-only route for any broker side effect. Do not manually
  invoke the Windows task, its Docker profile, a KIS client, or a replacement
  canary. The task's normal eligible session owns timing and submission.
- `KIS_PAPER_*` use by that named existing path is authorized. Never read,
  reference, route, print, log, or persist `KIS_LIVE_*`; do not enable a live
  route or real-money behavior.
- Inspect only source-safe task facts, immutable receipts, and categorical
  loopback dashboard paths. Never print credentials, account identifiers,
  balances, positions, raw broker bodies, raw price rows, order identifiers, or
  private snapshot values.
- Do not add a new scheduler, provider, dashboard surface, agent, model,
  strategy, signal, market-data cache, capital envelope, or human-release gate.
- A `not_submitted`, unavailable, or unknown result narrows only that exact
  lifecycle. Reconcile it through its existing exact durable path; it cannot
  block distinct authorized Paper work or create an approval wait.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Reattest the existing quote-session task configuration and current image
   provenance through source-safe Task Scheduler/Docker facts. Confirm its
   existing route remains virtual-only and its execution receipt reader remains
   credential-free; do not create a duplicate task or start a container.
2. After its first eligible owned run, read only the resulting immutable
   source-safe lifecycle receipt. Recompute the reader's required receipt/hash
   bindings and record the categorical lifecycle, reconciliation state, and
   local Paper/Paper-only scope. Missing evidence is `unknown`, never inferred
   as success, busy, or failure.
3. If the reader exposes one exact recoverable technical defect, repair and
   test only that reader/route contract. Do not resubmit an unknown intent or
   broaden the canary. If the lifecycle is clean, retain its exact result and
   stop this objective without inventing a model or PnL interpretation.
4. Inspect the credential-free loopback dashboard only through categorical
   health/status paths. Its display is an operational aid, not broker evidence
   or a new public surface.
5. While the task owns an external due time, continue ready non-conflicting
   offline Data/Engine/Execution package preparation. Do not foreground-wait;
   preserve the task-owned `next_due` and reattach only after evidence exists.
6. Refresh the active stateboards, `HANDOFF.md`, `RUNBOOK.md`, and
   `DECISIONS.md`; run the required verification; commit, push, replace this
   file with one material next company objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Close KIS Paper canary lifecycle evidence`
