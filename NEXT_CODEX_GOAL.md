# Next Codex Goal

## Objective

Expose one strictly allowlisted KIS virtual-paper upstream failure code for the
read-only bridge, then rebuild the image and run one fresh bridge invocation.

The rebuilt current image reached `balance` / `VTTS3012R`, received HTTP 500,
and sent no order. Its endpoint/transaction/HTTP diagnostic proves the bridge
is current but does not identify the virtual endpoint cause. The smallest useful
next fact is KIS `msg_cd` only when it matches a narrow safe format. This is
integration recovery, not a paper-work approval step: private KIS Paper work is
standing-authorized and KIS Live remains forbidden.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before edits or the bridge call:
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/kis_paper_console_bridge.py`
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `tests/test_kis_readonly.py`
   - `tests/test_paper_account_snapshot.py`
4. Use only official KIS documentation/examples to verify the public `msg_cd`
   field semantics. Do not send KIS credentials, account data, artifacts, or raw
   broker output to Claude or another external service.

## Scope

- Extend failure diagnostics only with `upstream_code` derived from KIS `msg_cd`
  when it is uppercase alphanumeric and has a bounded length. Reject or omit
  every other value.
- Never persist `msg1`, a raw body, tokens, app keys, app secrets, account
  identifiers, order references, or free-form exception text.
- Keep virtual-host-only routing, read-only endpoint allowlists, and no order
  action in this objective.
- Do not read `KIS_LIVE_*`, construct a live route, buy anything, or expose a
  public service.

## Required Work

### Execution Agent

1. Add focused tests proving a safe `msg_cd` becomes `upstream_code`, while an
   unsafe/free-form value and `msg1` never reach runtime or external evidence.
2. Update both the read-only and console-bridge diagnostic validators so their
   allowlists agree.
3. Run the focused tests, then rebuild:

   ```powershell
   docker compose build kis-readonly
   ```

4. Run exactly one fresh bridge call:

   ```powershell
   docker compose --profile kis-readonly run --rm --no-deps kis-readonly
   ```

5. Record only the current reason, endpoint, transaction ID, HTTP status, and
   optional safe upstream code. On `complete`, make the authorized canary
   submit/cancel/reconcile cycle the next objective. On `unavailable`, use the
   code to define the next narrow implementation or KIS-account recovery step;
   do not retry in a loop.

### Data And Validation

- Keep `raw_market_data_retained: false` as provenance rather than a permission
  switch, while retaining raw-file/hash checks as data integrity.
- Preserve virtual-only routing and no-order behavior from the bridge.

## Completion Evidence

- Focused regression proof of the diagnostic allowlist.
- A current-image build and exactly one fresh sanitized bridge artifact outside
  Git.
- No KIS Live access, order request, raw broker body, credential, or account
  identifier in Git, logs, or artifacts.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Expose KIS bridge failure code`
