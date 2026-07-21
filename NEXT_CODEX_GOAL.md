# Next Codex Goal

## Objective

Reconcile the first ambiguous KIS Paper canary outcome exactly once, without a
replacement order attempt.

The current-image virtual canary run `canary-20260721T225034Z` completed its
initial account reconciliation and then reported `outcome_unknown` with
`submit_transport_unknown`. Its safe evidence records no broker order
reference. That absence is not evidence that the submit side effect did not
reach KIS. The persisted state for this exact run is therefore the only
recovery target: reuse it once and allow the program to reconcile it without a
submit, modify, cancel, or new run ID.

KIS Paper credential/account/data/order access and scheduled Paper work are
standing-authorized. KIS Live remains forbidden. Do not read, print, or retain
secrets, account identifiers, raw broker bodies, or private intent state.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before the recovery call:
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `src/thericher_v2/execution/kis_readonly.py`
   - `tests/test_kis_paper_canary.py`
   - `docker-compose.yml`
4. Ask Claude for one concise falsification-first recovery check. State that
   the exact existing run is `outcome_unknown`, the one recovery command must
   not send a submit/modify/cancel request, and a new run is out of scope. Do
   not send credentials, account data, raw broker output, private intent state,
   or order identifiers.

## Required Work

### Execution Agent

1. Add or retain a focused deterministic proof that a persisted
   `outcome_unknown` run cannot call submit when resumed.
2. Run focused tests, Claude's short recovery review, and rebuild the current
   image:

   ```powershell
   docker compose build kis-paper-canary
   ```

3. Invoke exactly one recovery command using the existing run ID and its
   existing private state. It may perform the program's virtual read-only
   reconciliation only:

   ```powershell
   docker compose --profile kis-paper-canary run --rm --no-deps --entrypoint python kis-paper-canary -m thericher_v2.execution.kis_paper_canary --execute --cancel-after-submit --run-id canary-20260721T225034Z --repository-root /app --state-root /app/private/canary --runtime-projection /app/runtime/state/kis_paper_canary.json --paper-account-snapshot /app/runtime/state/paper_account_snapshot.json --emergency-state /app/emergency/emergency_state.json --artifact-root /app/model_artifacts
   ```

4. Record only the sanitized phase, reason, reconciliation status/counts, and
   evidence path. Do not infer that a missing reference proves no external side
   effect. Do not submit a replacement order in this objective.

### Data And Research

- Keep data and research work independent of this narrow execution recovery.
- Preserve `raw_market_data_retained: false` as historical provenance only,
  never a permission switch. Preserve local simulation fills as
  `source: local_paper`.

## Completion Evidence

- A focused no-resubmit regression proof.
- One current-image same-run recovery invocation with sanitized external
  evidence outside Git.
- No KIS Live access, raw broker body, credential, account identifier, or raw
  order identifier in Git, logs, dashboard, or artifact.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reconcile ambiguous KIS paper canary`
