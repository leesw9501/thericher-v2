# Next Codex Goal

## Objective

Restore KIS **virtual-paper** token access and complete the first bounded US
buy-limit canary reconciliation through the existing `kis-paper-canary` Docker
service.

The canary implementation, private recovery volume, sanitized runtime
projection, and local dashboard are ready. On 2026-07-21, the first actual
token/account attempt returned `auth_rejected` before an account snapshot or
order submit. This is an external KIS virtual-application recovery fact, not a
capital, profitability, one-shot, raw-retention, or per-call approval gate.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and
   `agents/execution.md` first; then read `agents/data.md` and
   `agents/engine-research.md` for independent work readiness.
3. Read the sanitized canary/dashboard runtime state and external evidence
   metadata only. Do not print, copy, or commit private recovery state,
   credentials, account identifiers, raw requests, or raw responses.

## Work Packages

### Execution Agent

1. Verify only the presence/shape of the four `KIS_PAPER_*` values in the
   credential-bearing canary container; do not read `KIS_LIVE_*` or print a
   secret/account value.
2. Re-run the existing persisted canary by run ID when it is still valid. Its
   durable intent is authoritative: reconcile first and never submit a
   replacement after an unknown outcome.
3. When that intent has expired without a side effect, start one fresh default
   bounded canary through:

   ```powershell
   docker compose --profile kis-paper-canary run --rm --no-deps kis-paper-canary
   ```

   Keep the fixed virtual host, US buy-limit-only route, whole share, explicit
   limit, automatic accepted-order cancellation, and sanitized artifacts.
4. If token access succeeds, verify acknowledgement/reconciliation and the
   credential-free dashboard projection. This is execution connectivity
   evidence only, never a return or model-quality claim.
5. If KIS continues to return `auth_rejected`, record only the safe reason and
   exact recovery instruction: verify or regenerate the **virtual-paper** app
   key/secret in KIS, update local `.env`, and rerun. Do not substitute live
   credentials, guess credentials, brute-force retries, or add a new approval
   process.

### Data Agent

- Keep KIS market-data cache bytes separate from canary/account evidence.
- Continue no-cost, ready offline data-contract work only if it does not
  interfere with the KIS recovery attempt. Do not make `auth_rejected` a data
  collection blocker.

### Engine Research Agent

- Keep the deterministic canary decision independent of model/GPU work.
- Continue CPU preparation only for a distinct falsifiable candidate; do not
  manufacture GPU work merely because KIS token recovery is external.

### Validation

- Verify no live host/credential is reachable, no duplicate submission occurs
  after a recovered/unknown run, canary artifacts remain outside Git, and web
  code stays credential-free.

## Operating Boundaries

- All `KIS_PAPER_*` reads and virtual submit/modify/cancel/reconciliation are
  standing-authorized. No paper-capital, profitability, dashboard, trade-count,
  or individual-call confirmation is required.
- `KIS_LIVE_*`, live hosts, real-money behavior, paid purchases, and public
  exposure remain unavailable.
- Keep generated artifacts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`; raw market data stays under `D:\market_data`; neither
  belongs in Git.
- Retain technical correctness only: virtual-only routing, secret-safe output,
  intent-before-side-effect, no retry after unknown outcome, and reconciliation
  before a replacement.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Recover KIS paper canary authentication`
