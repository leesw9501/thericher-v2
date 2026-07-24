# Next Codex Goal

## Objective

Audit the existing KIS Paper daily-SPY exact-intent recovery path before adding
any stale-order automation. Prove whether the current session, receipt observer,
and terminal-field probe already preserve a safe outcome when an acknowledged
durable intent is absent from a current open-order snapshot. Add code only for a
concrete uncovered invariant; otherwise close the audit as no-change and leave
prospective KIS data readiness as the next path.

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
   - `agents/execution.md`
   - `agents/data.md`
   - `agents/review.md`

3. Ask Claude for a short falsification-first drift-check before relying on an
   audit conclusion or adding any recovery behavior. Do not send credentials,
   account/order identifiers, raw KIS payloads, or source rows.

## Hard Boundaries

- Keep the audit read-only and paper-only. Do not submit, modify, cancel, or
  retry an order; do not call or read `KIS_LIVE_*`.
- Prefer pure fixtures and existing sanitized local evidence. Do not read `.env`,
  credentials, secret-like files, or raw private state for the audit.
- Do not create a second observer, terminal probe, scheduler, timer, quota,
  stale threshold, approval gate, dashboard, or report family.
- An absent exact order remains categorically ambiguous until existing source
  evidence proves otherwise. Never infer fill, cancellation, terminal lifecycle,
  PnL, or model performance from absence or aggregate positions.
- Keep generated evidence outside Git and preserve the existing `kis_paper` vs
  `local_paper` route distinction.

## Role-Owned Work

### Execution Agent

1. Trace the exact durable run identity through the daily session, receipt
   observer, and terminal-field probe using only code and synthetic fixtures.
2. Define the existing safe result for an acknowledged intent that is absent
   from a current open-order snapshot and lacks qualified terminal semantics.
3. Add a narrowly scoped implementation only if a reproducible fixture proves
   the existing path violates that safe result. It must preserve the same intent
   identity and remain read-only.

### Validation Agent

1. Try to break the conclusion with a clean lifecycle fixture whose exact intent
   becomes absent from the open-order snapshot.
2. Verify that the result is neither a false terminal/PnL claim nor a global
   paper hold, and that another distinct correctly scoped intent is unaffected.

### Data Agent

Confirm whether qualified terminal enum, amendment-ordering, and completion
facts already exist locally. Report only the source fact; do not invent a new
provider or collection job for this audit.

## Completion Evidence

- One exact state-to-outcome map exists for the acknowledged-but-absent case.
- Focused tests demonstrate bounded ambiguity, route isolation, and no new
  order side effect.
- The outcome is either `existing path sufficient`, `minimal invariant fix`, or
  `terminal source semantics unavailable`; it is never a model/PnL conclusion.
- Claude's concise verdict is recorded only if it changes a durable decision.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Audit paper exact-intent recovery`
