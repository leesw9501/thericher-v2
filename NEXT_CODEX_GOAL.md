# Next Codex Goal

## Objective

Reuse the tested KIS virtual request pacing in the narrow paper-canary
transport, then run one authorized submit/cancel/reconcile cycle.

The read-only bridge now completes under a one-second minimum external-request
gap. Its safe snapshot records one position and zero open orders, but no raw
account or price data. The canary uses a separate virtual-only transport and
can make token, read-only reconciliation, submit, cancel, and completion-query
requests in one bounded run. It must inherit source pacing before its first
actual Paper order attempt. Private KIS Paper work is standing-authorized; KIS
Live remains forbidden.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before edits or the canary call:
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `src/thericher_v2/execution/kis_paper_console_bridge.py`
   - `tests/test_kis_paper_canary.py`
   - `tests/test_kis_readonly.py`
   - `docker-compose.yml`
4. Ask Claude for a concise falsification-first drift check before the real
   canary call. Do not send credentials, account data, raw broker output,
   private intent state, or order identifiers.

## Scope

- Share or reuse the read-only transport's injectable monotonic one-second
  pacing for the canary's real virtual external requests. The first valid
  external request may proceed immediately; later ones must be spaced.
- Keep fake/offline canary transports fast. Preserve virtual-host-only routes,
  the fixed one-share buy-limit/cancel surface, persisted intent, no duplicate
  submit after ambiguity, and sanitized evidence.
- Build the current `kis-paper-canary` image, then invoke its existing Compose
  command exactly once. It is authorized to submit and cancel one virtual order.
- Do not add a generic broker adapter, retry loop, scheduler, sell route, live
  route, public endpoint, paid service, or manual approval gate.

## Required Work

### Execution Agent

1. Add focused deterministic pacing tests for the real canary transport,
   including a failed external attempt consuming a slot. Keep existing order
   lifecycle and fake-transport tests fast.
2. Review the persisted canary recovery through the program's sanitized outcome
   and existing state semantics; never dump private intent/order content.
3. Run focused tests and Claude's short review. Rebuild:

   ```powershell
   docker compose build kis-paper-canary
   ```

4. Run exactly one existing canary command:

   ```powershell
   docker compose --profile kis-paper-canary run --rm --no-deps kis-paper-canary
   ```

5. Record only sanitized phase/reason/counts/artifact path. If `cancelled` with
   clean reconciliation, make prospective paper observation and PnL attribution
   the next objective. If unresolved or unavailable, define the smallest
   recovery objective and do not submit again in the same goal.

### Data And Validation

- Keep `raw_market_data_retained: false` as provenance rather than a permission
  switch, while retaining raw-file/hash checks as data integrity.
- Preserve local-paper replay as `source: local_paper`; this objective's KIS
  event is virtual-broker evidence, not a simulated fill.

## Completion Evidence

- Focused pacing and canary lifecycle regression proof.
- One current-image canary invocation and sanitized external evidence outside
  Git.
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

`Pace KIS paper canary transport`
