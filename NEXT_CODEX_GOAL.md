# Next Codex Goal

## Objective

Make ambiguous KIS Paper canary submit failures safely diagnosable, then run one
independent new virtual-paper canary.

The first current-image canary, `canary-20260721T225034Z`, remains
`outcome_unknown` after its one permitted reconciliation-only recovery. The
recovery found an available account, no open order, no completion row, and no
matching entry, but the missing order reference prevents a clean absence claim.
Preserve that run and never retry, replace, modify, or cancel it.

KIS Paper credential/account/data/order access and scheduled Paper work are
standing-authorized. A separately identified new canary is allowed after its
diagnostic code and tests are ready. KIS Live remains forbidden. Do not read,
print, or retain secrets, account identifiers, raw broker bodies, private intent
state, or raw order identifiers.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before edits or the fresh canary call:
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `src/thericher_v2/execution/kis_readonly.py`
   - `tests/test_kis_paper_canary.py`
   - `tests/test_kis_readonly.py`
   - `docker-compose.yml`
4. Ask Claude for a concise falsification-first drift check before the fresh
   canary call. State that the old unknown run is preserved, the new run is
   independent, its fixed virtual buy-limit/cancel surface is unchanged, and
   diagnostics retain only a closed safe code. Do not send credentials, account
   data, raw broker output, private state, or order identifiers.

## Required Work

### Execution Agent

1. Add a small closed diagnostic path for canary submit failures. It may use
   HTTP status class and an allowlisted KIS-style code only when present; it
   must never retain `msg1`, arbitrary body text, request bodies, secrets,
   account identifiers, or broker order identifiers.
2. Add focused tests for safe diagnostic classification and for the absence of
   unsafe raw response content in runtime/evidence. Keep the existing direct
   no-order-route recovery proof for the old run.
3. Run focused tests and Claude's check. Rebuild:

   ```powershell
   docker compose build kis-paper-canary
   ```

4. Run exactly one fresh current-image canary through the existing Compose
   command. It creates a new run ID and may submit/cancel its one virtual
   buy-limit order; it must not reuse the old run ID:

   ```powershell
   docker compose --profile kis-paper-canary run --rm --no-deps kis-paper-canary
   ```

5. Record only sanitized phase, closed reason/diagnostic, reconciliation
   counts/status, and artifact path. A successful cancellation is prospective
   Paper execution evidence, not model promotion. An unavailable or unknown
   new run is preserved and never retried in the same objective.

### Data And Research

- Keep collection and eligible research work independent of this narrow
  execution task.
- Preserve `raw_market_data_retained: false` as historical provenance only,
  never a permission switch. Preserve local simulation fills as
  `source: local_paper`.

## Completion Evidence

- Focused safe-diagnostic and no-order-route recovery regression proof.
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

`Diagnose KIS paper canary submissions`
