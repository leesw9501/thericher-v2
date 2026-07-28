# Next Codex Goal

## Objective

Validate the existing KIS Paper overseas-stock `1m` empty-response
classification without widening broker authority, then establish whether the
observed `SPY/NAS` result is route-specific or request-shape-limited.

The completed `SPY/NAS` `PINC=1` probe made one token request and one minute
request, accepted no page, and emitted `minute_response_empty`. It is
`unavailable` for that exact request shape. It is not proof of an exchange
mismatch, a source limitation, or provider-wide intraday reach.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the read-only KIS minute client, capability probe, source-safe
   transport tests, and existing QQQ/NAS and SPY/AMS evidence. Do not inspect or
   print raw market rows.
3. Ask Claude for one short falsification-first drift check before changing the
   route-registry contract or relying on the paired capability inference. Do not include
   credentials, account identifiers, raw rows, or provider bodies.

## Authority And Boundaries

- `KIS_PAPER_*` is standing-authorized only for private **market-data** work in
  this objective. Do not call account, quote, order, cancellation, modification,
  or reconciliation endpoints.
- Use one in-memory client/token, one active probe, and the installed one-second
  request-start gate. Do not parallelize requests or create a request flood.
- Do not retry `SPY/NAS` in this objective. After local classification tests,
  make at most one `SPY/AMS` `PINC=1` native-route control request.
- Store data only under `D:\market_data` and evidence only under
  `D:\thericher-v2\model-artifacts`. Keep raw rows, credentials, provider
  bodies, and account facts out of Git, logs, stateboards, and Claude.
- Do not read or route `KIS_LIVE_*`, change paper-order behavior, select or
  promote a model, add a collector/scheduler, or add a dashboard/report flow.

## Work

1. **Data:** add transport-level focused tests proving the existing client maps
   a successful response with an empty `output2` to `minute_response_empty`
   only after successful payload validation, while rejected or malformed
   responses retain their distinct safe categories. Do not retain raw provider
   code, message, body, or rows.
2. Split the minute route registry into exact native routes established by
   existing data-bearing evidence and observed-only candidates. Preserve current
   QQQ/NAS and SPY/AMS contracts; retain SPY/NAS only as an observed unavailable
   candidate, not a collection target.
3. Add focused tests for classification, registry scope, no raw response
   retention, no account/order/live surface, and the one-client request budget.
4. Run one `SPY/AMS` `PINC=1` native-route control through the capability probe
   with one page. Record only source-safe response and request categories.
5. Interpret the pair narrowly:
   - a native data-bearing control plus the prior SPY/NAS empty-success result
     makes the alternate route unavailable for that exact request shape;
   - a native empty-success result leaves time/request-shape capability
     unresolved;
   - a native rejection/invalid result leaves provider-route capability
     unresolved.
   In every outcome, do not bootstrap a historical collector here.

## Completion

- The prior SPY/NAS observation and one native SPY/AMS control have clear,
  source-safe categories and remain exact-scope evidence.
- No KIS account/order call, live route, secret output, raw-row Git artifact,
  model promotion, collector, or new approval gate exists.
- Refresh Data and orchestration stateboards, replace this file with exactly one
  next objective, then continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Classify KIS minute route capability`
