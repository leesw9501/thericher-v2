# Next Codex Goal

## Objective

Rebuild the current `kis-readonly` Docker image, then run one fresh KIS
virtual-paper account bridge that can emit the current sanitized diagnostic
projection.

The previous one-call bridge attempt was `balance_rejected` with no order, but
its output still used the old `safe_to_submit` schema. It therefore exercised a
stale pre-`2a58c87` image, not the committed bridge code. This is runtime
recovery, not an approval step: private KIS Paper reads, retention, schedules,
sizing, submit/modify/cancel, and reconciliation remain standing-authorized.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
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

1. Rebuild without a KIS call:

   ```powershell
   docker compose build kis-readonly
   ```

2. Then run exactly one KIS bridge invocation:

   ```powershell
   docker compose --profile kis-readonly run --rm --no-deps kis-readonly
   ```

- Use only the fixed virtual-paper host through the existing profile.
- Do not read `KIS_LIVE_*`, construct a live route, print credentials/account
  identifiers/raw broker bodies, buy anything, or expose a public service.
- The bridge is `read_only`; its `account_snapshot_complete` value describes
  that call only. It is not a `safe_to_submit` or manual-approval mechanism.

## Required Work

### Execution Agent

1. Classify the stale-image `balance_rejected` result and persisted canary as
   `reconcile`; the canary has no broker order reference or submit evidence.
2. Build the image, confirm the build succeeds, then run the single bridge call.
3. Inspect the new sanitized artifact and runtime projection only.
   - On `complete`, record freshness, currencies, position count, and open-order
     count. The next objective may run the authorized canary submit/cancel/
     reconcile cycle without asking for approval.
   - On `unavailable`, require the current `scope`/`account_snapshot_complete`
     output shape and record only the reason plus allowlisted endpoint,
     transaction ID, and HTTP status. Do not retry in a loop; form the next
     narrow route-repair objective while independent work continues.
4. Refresh `agents/execution.md` and `HANDOFF.md` with the recovery class.

### Validation

- Keep focused coverage for virtual-only routing, no secret/raw-body
  persistence, diagnostic allowlisting, and no order action from the bridge.
- Treat historical `raw_market_data_retained: false` as provenance only; retain
  raw-file/hash checks as data integrity rather than paper-workflow gates.

## Completion Evidence

- A successful current-image build.
- One fresh sanitized bridge artifact outside Git that uses the current output
  shape.
- A current recovery classification with no KIS Live access, order request, or
  secret/account data in Git, logs, or artifacts.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Record KIS bridge runtime recovery`
