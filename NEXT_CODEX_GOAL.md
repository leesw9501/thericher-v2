# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-paper-virtual-lifecycle-canary-v2`: prepare, schedule, and attest
one bounded current KIS virtual-Paper lifecycle attempt through the existing
deterministic canary path. Its outcome may be categorical no-intent, rejected,
cancelled-and-clean, or unknown-and-reconciled; it must never be described as a
model or profitability result.

## Boundaries

- `KIS_PAPER_*` reads and virtual order submit/modify/cancel/reconciliation are
  standing-authorized. Never read or route `KIS_LIVE_*`.
- Use the existing virtual-host-pinned canary, fresh account/quote checks,
  durable intent, cancellation, and reconciliation ownership paths. Do not
  create a second broker adapter, manual fixed-price order, public service, or
  dashboard submission route.
- A distinct new intent uses the existing shared execution lock and its own
  call-time reconciliation to reject a matching open order. Reconcile an exact
  unknown outcome before replacing that same intent; an unrelated historical
  unknown does not create a global Paper hold.
- Keep all secrets, account identifiers, raw broker bodies, order identifiers,
  and raw prices out of Git, logs, stateboards, dashboard projections, and
  Claude prompts. Keep `KIS_LIVE_*` unavailable.
- Do not make Data collection, prospective model readiness, or GPU work depend
  on the canary outcome. Their installed workers continue independently.

## Required Work

1. Ask Claude for a concise falsification-first execution/recovery drift check
   before relying on the existing Paper submission boundary. State the exact
   virtual host, durable-intent/reconciliation kill test, fresh-account/quote
   requirement, and the fact that would prohibit a new intent.
2. Inspect the current canary state, runtime projection, installed task/schedule
   ownership, and route allowlist without printing private values. Freeze a
   one-attempt contract using the existing service and a current US regular
   session. If existing task ownership already supplies the exact attempt, do
   not add a duplicate task.
3. Execute or let the named worker execute at most one new current virtual
   canary attempt. Use the existing call-time checks and preserve its categorical
   result; do not foreground-retry, submit a replacement intent, or infer an
   order result from absent evidence.
4. Reattach the resulting source-safe state only through the existing runtime
   projection and independent offline validator. When a pre-canary runtime's
   safe `run_id` is an explicit `paper-session-*` ID, the existing projector
   may read only that exact immutable session receipt with `--session-id`; it
   must never select a latest artifact. A `prior_submission_unresolved` result
   retains the prior direct-canary runtime and still requires its direct
   lifecycle path. Verify the loopback dashboard remains credential-free and
   cannot trigger a broker action.
5. Add focused tests only for any newly discovered recovery/route condition;
   otherwise reattest the existing route, duplicate-intent, and secret-safe
   projection contracts. Refresh Execution and orchestration stateboards with
   durable evidence.

## Completion Evidence

- Claude records `unsupported`, `uncertain`, or `supported-with-limits` without
  granting authority;
- one bounded, current virtual-Paper lifecycle attempt or its exact
  worker-owned categorical completion exists with no live credential or secret
  output;
- required verification passes, commit and push complete, then this file is
  replaced with exactly one next company objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
docker compose --env-file .env.example --profile kis-readonly config --quiet
```
