# Next Codex Goal

## Objective

Add a small testable pacing policy to KIS virtual-paper read-only requests,
then rebuild the image and run one fresh bridge invocation.

The latest rebuilt bridge reached `balance` / `VTTS3012R`, received HTTP 500
with the sanitized KIS code `EGW00201`, and sent no order. KIS's official
sample repository identifies that code as a per-second request-limit exceedance.
The bridge presently sends one token request followed rapidly by open-order,
three-venue balance, and orderable-funds requests. This is integration recovery,
not a paper-work approval step: private KIS Paper work is standing-authorized
and KIS Live remains forbidden.

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
4. Do not send KIS credentials, account data, artifacts, or raw broker output
   to Claude or another external service.

## Scope

- Pace actual virtual read-only external requests with an injectable monotonic
  policy. The first dispatch may proceed immediately; every later dispatch must
  respect the configured minimum interval.
- Use a conservative `1.0` second default for the real KIS transport. Do not
  add automatic retries, exponential backoff, a scheduler, or a new gate.
- Preserve virtual-host-only routing, endpoint allowlists, fail-closed parsing,
  the safe `EGW00201` projection, and no order action in this objective.
- Do not read `KIS_LIVE_*`, construct a live route, buy anything, or expose a
  public service.

## Required Work

### Execution Agent

1. Add focused deterministic tests with an injected monotonic clock/sleeper
   proving the initial request is immediate and later external requests are
   spaced by the configured interval. Keep existing route and fail-closed tests.
2. Keep fake/offline transports fast; production bridge traffic must use the
   paced real transport without relying on wall-clock assertions in tests.
3. Run focused tests, then rebuild:

   ```powershell
   docker compose build kis-readonly
   ```

4. Run exactly one fresh bridge call:

   ```powershell
   docker compose --profile kis-readonly run --rm --no-deps kis-readonly
   ```

5. Record only the current sanitized reason/diagnostic and artifact path. On
   `complete`, make the already-authorized canary submit/cancel/reconcile cycle
   the next objective. On `unavailable`, define the next smallest technical
   recovery from the observed code; do not retry in a loop.

### Data And Validation

- Keep `raw_market_data_retained: false` as provenance rather than a permission
  switch, while retaining raw-file/hash checks as data integrity.
- Preserve virtual-only routing and no-order behavior from the bridge.

## Completion Evidence

- Focused regression proof of production pacing and unchanged offline behavior.
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

`Pace KIS paper read-only requests`
