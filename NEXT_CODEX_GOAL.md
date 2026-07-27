# Next Codex Goal

## Objective

Refresh and attest one current private KIS Paper account-to-dashboard projection
through the existing virtual-only read-only bridge. The outcome may be a
sanitized complete snapshot or a sanitized unavailable result, but it must
truthfully show the bridge's current scope without creating an order, canary,
replay, model input, or live behavior.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, DECISIONS.md, RUNBOOK.md, and all active
   stateboards.
3. Read `src/thericher_v2/execution/kis_paper_console_bridge.py`,
   `src/thericher_v2/execution/paper_account_snapshot.py`, the `kis-readonly`
   Compose service, and their focused tests before a KIS Paper call.
4. Inspect the existing local runtime snapshot and related external
   source-safe evidence only through their validated readers. Never print their
   account facts or raw content.

## Required Work

1. Use only the existing Docker `kis-readonly` profile to make one bounded KIS
   Paper read-only bridge invocation. It may receive `KIS_PAPER_*` through
   Compose, but Codex must not open, print, copy, or pass `.env` values on a
   command line.
2. Verify the resulting local runtime projection through the validated snapshot
   reader and dashboard view boundary. Confirm `source: kis_paper`,
   `read_only: true`, and `submission_capability: false` when a complete
   snapshot is available; otherwise retain only the safe unavailable category
   and allowlisted diagnostic metadata.
3. Keep the web surface loopback-only and credential-free. Do not write account
   identifiers, balances, position values, order values, raw KIS bodies, or
   tokens to Git, external artifacts, Claude, logs, or chat.
4. Use temporary Execution and Validation roles to independently check virtual
   route pinning, no-order isolation, snapshot sanitization, and recovery
   behavior. Data records only whether this goal consumed no provider rows or
   cache mutations.
5. Add focused tests only for a concrete defect found in the existing bridge or
   projection path. Do not build a new dashboard, report framework, or account
   abstraction merely for this run.

## Hard Boundaries

- Use `KIS_PAPER_*` only through the owned read-only bridge. Never read or use
  `KIS_LIVE_*`.
- Preserve `THERICHER_MODE=off`.
- Do not submit, modify, cancel, reconcile, or create a KIS Paper order intent.
- Do not call Tiingo or acquire market data for this objective.
- Do not expose a public service or change paper-vs-live routing.
- A complete, stale, unavailable, or failed snapshot is evidence about this
  bridge invocation only. It is never an approval gate or a blocker for another
  ready lane.

## Completion Evidence

- One current, sanitized local projection or safe unavailable bridge outcome
  from the virtual-only read-only service.
- Independent Execution and Validation confirmation that no order/live route or
  secret/account payload reached the dashboard, artifact, Git, or logs.
- No submitted, modified, cancelled, or reconciled broker order.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A KIS Paper unavailable result, a rate wait, or a
lane-local bridge failure does not stop independent ready work.
