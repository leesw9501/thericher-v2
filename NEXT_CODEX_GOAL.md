# Next Codex Goal

## Objective

Expose a validated KIS Paper submit-rejection code without retaining raw broker
content, then run one new independent virtual-paper canary.

The independent run `canary-20260721T232137Z` reached clean initial
reconciliation and produced `submit_kis_rejected`, with no open order,
completion row, matching entry, or order reference in safe evidence. It and the
earlier ambiguous run are preserved evidence only. Never retry, replace,
modify, cancel, or reuse either run ID.

KIS Paper credential/account/data/order access and scheduled Paper work are
standing-authorized. A new independently identified canary is allowed after the
safe-code projection and tests are ready. KIS Live remains forbidden. Do not
read, print, or retain secrets, account identifiers, raw broker bodies, private
intent state, or raw order identifiers.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before edits or the fresh canary call:
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/paper_canary_runtime.py`
   - `tests/test_kis_paper_canary.py`
   - `tests/test_kis_readonly.py`
   - `docker-compose.yml`
4. Ask Claude for a concise falsification-first drift check before the fresh
   canary call. State that preserved runs remain untouched, the new run is
   independent, the virtual buy-limit/cancel surface is unchanged, and only a
   strictly validated KIS-style code may be projected. Do not send credentials,
   account data, raw broker output, private state, or order identifiers.

## Required Work

### Execution Agent

1. Reuse or extract one strict validator for a short KIS-style code: uppercase
   ASCII, bounded length, and at least one digit. Project only a valid `msg_cd`
   value for a rejected submit into sanitized state/evidence/runtime; omit it
   otherwise. Never project `msg1`, arbitrary response text, request bodies,
   secrets, account identifiers, or order identifiers.
2. Preserve compatibility for existing canary state/evidence/runtime files and
   keep the code projection informational: it must not alter routing, sizing,
   retry behavior, or the preserved runs.
3. Add focused tests for valid-code projection, invalid-code omission, and raw
   message exclusion from state/evidence/runtime. Keep the direct no-order-route
   recovery proof.
4. Run focused tests and Claude's check. Rebuild:

   ```powershell
   docker compose build kis-paper-canary
   ```

5. Run exactly one fresh current-image canary through the existing Compose
   command. It creates a new run ID and may submit/cancel its one virtual
   buy-limit order; it must not reuse preserved run IDs:

   ```powershell
   docker compose --profile kis-paper-canary run --rm --no-deps kis-paper-canary
   ```

6. Record only sanitized phase, closed reason, optional validated code,
   reconciliation counts/status, and artifact path. A fresh rejection or
   unknown outcome is preserved and never retried in this objective.

### Data And Research

- Keep collection and eligible research work independent of this narrow
  execution task.
- Preserve `raw_market_data_retained: false` as historical provenance only,
  never a permission switch. Preserve local simulation fills as
  `source: local_paper`.

## Completion Evidence

- Focused safe-code projection, raw-message exclusion, and no-order-route
  recovery regression proof.
- One current-image fresh virtual canary invocation with sanitized evidence
  outside Git.
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

`Expose KIS paper rejection code`
