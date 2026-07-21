# Next Codex Goal

## Objective

Run one bounded KIS virtual-paper **read-only reconciliation** and refresh the
sanitized account/position/open-order facts used by the existing canary.

This objective resolves the current `auth_rejected` recovery fact. It makes no
order request and does not turn virtual-paper access into a live route. A fresh
successful snapshot makes the following bounded canary-submit objective ready
without a new operator approval.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and all active
   stateboards under `agents/`.
3. Read before any external call:
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/kis_paper_console_bridge.py`
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - their focused tests.
4. Inspect only sanitized evidence under
   `D:\thericher-v2\model-artifacts\execution`; do not read private canary
   state, `.env`, token values, account identifiers, or raw broker bodies.

## Standing Authority And Scope

- The operator has standing-authorized `KIS_PAPER_*` virtual-paper token,
  account, position, open-order, and reconciliation calls for this private
  project.
- Use only the fixed KIS virtual-paper host and allowlisted read-only endpoints
  through the existing credential-bearing console bridge.
- Do not read `KIS_LIVE_*`, construct a live route, print secrets/account
  identifiers/raw responses, submit/modify/cancel an order, or invoke the
  canary submit service in this objective.
- Generated sanitized evidence remains under
  `D:\thericher-v2\model-artifacts\execution`; Git receives only aggregate,
  non-secret recovery facts.

## Required Work

### Execution Agent

1. Classify the existing canary state as `reconcile`: its latest intents are
   `intent_recorded` with no broker order reference or submit evidence, not an
   unknown submitted order.
2. Run exactly one existing read-only bridge invocation:

   ```powershell
   docker compose --profile kis-readonly run --rm --no-deps kis-readonly
   ```

3. Inspect the resulting sanitized runtime/evidence projection only.
   - On `complete`, record only freshness and safe aggregate facts such as
     position/open-order counts and currencies; do not submit an order here.
   - On `unavailable`, record only the allowlisted reason code and classify the
     result as `reconcile`; do not retry in a loop or substitute any credential.
4. Update the Execution stateboard and handoff with the recovery classification.
   A successful read-only result should make one narrow virtual-paper canary
   submit/cancel/reconcile cycle the next objective. An unavailable result must
   not block independent Data or Research work.

### Validation

- Preserve focused tests proving virtual-host-only routing, secret-safe
  projection, read-only bridge behavior, and no order call from the bridge.
- Add a focused regression only if the real bridge result exposes an actual
  implementation gap. Do not add a report family or retry worker.

## Boundaries

- No live behavior, paid service, public service, model change, GPU work, market
  data download, paper submit/modify/cancel, or capital decision is part of this
  objective.
- `auth_rejected` is an external integration fact, not an approval gate. Do not
  invent a credential, inspect secret values, or replace virtual credentials
  with live ones.
- Ask Claude only if an unexpected broker/position inconsistency changes the
  recovery interpretation or if a future objective proposes submission after an
  ambiguous outcome. A normal read-only outcome needs no review ceremony.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reconcile KIS paper account state`
