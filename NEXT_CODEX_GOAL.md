# Next Codex Goal

## Objective

Run one fresh KIS virtual-paper account bridge after the diagnostic projection
upgrade and classify the account route from sanitized evidence.

This is an Execution recovery objective, not a paper-trading approval step.
The operator has already authorized private KIS Paper reads, retention,
schedules, sizing, submit/modify/cancel, and reconciliation. The goal obtains
the next technical fact needed by the existing virtual-paper canary without
storing a broker body or credential.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   stateboards in `agents/`.
3. Read before the bridge call:
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/kis_paper_console_bridge.py`
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - their focused tests.
4. Inspect only sanitized evidence under
   `D:\thericher-v2\model-artifacts\execution`; do not inspect `.env`, private
   canary state, token values, account identifiers, or raw broker bodies.

## Scope

- Use the existing fixed virtual-paper host and the credential-bearing
  `kis-readonly` Compose profile.
- Run exactly one bridge invocation for this objective:

  ```powershell
  docker compose --profile kis-readonly run --rm --no-deps kis-readonly
  ```

- KIS Paper calls, later paper orders, and KIS-derived data retention are
  standing-authorized. This objective simply chooses a read-only call for a
  bounded recovery observation.
- Do not read `KIS_LIVE_*`, construct a live route, print credentials/account
  identifiers/raw broker bodies, buy anything, or expose a public service.
- The bridge is `read_only`; its `account_snapshot_complete` result describes
  this call only. It is not a `safe_to_submit` or manual-approval mechanism.

## Required Work

### Execution Agent

1. Classify the previous `balance_rejected` bridge and the persisted canary as
   `reconcile`; the canary has no broker order reference or submit evidence.
2. Run the single bridge invocation above.
3. Inspect its new sanitized artifact and runtime projection only.
   - On `complete`, record freshness, currencies, position count, and open-order
     count. The next objective may run the authorized canary submit/cancel/
     reconcile cycle without asking for approval.
   - On `unavailable`, record the reason plus the allowlisted endpoint,
     transaction ID, and HTTP status. Do not retry in a loop; use the result to
     form the next narrow route-repair objective while Data and Research work
     continue.
4. Refresh `agents/execution.md` and `HANDOFF.md` with the recovery class.

### Data And Validation

- Confirm that historical `raw_market_data_retained: false` is factual
  provenance, not a collection permission switch. Preserve raw-file/hash checks
  because they are data integrity, not paper-workflow gates.
- Keep focused regression coverage for virtual-only routing, no secret/raw-body
  persistence, diagnostic allowlisting, and no order action from the bridge.

## Completion Evidence

- One fresh sanitized bridge artifact outside Git.
- A current recovery classification in the Execution stateboard and handoff.
- No KIS Live access, no order request in this objective, and no secret/account
  data in Git, logs, or artifacts.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Clarify KIS paper execution authority`
