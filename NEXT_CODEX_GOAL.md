# Next Codex Goal

## Objective

Establish KIS Paper **market-data** token reuse and throughput behavior, then
finish the finite daily catch-up for `QQQ/NAS` and `SPY/AMS` while mapping the
actual historical 1m capability.

On 2026-07-24, a data-only token check returned `token_issued`. An immediately
following catch-up ran in a separate short-lived process and returned the safe
`auth_rejected` category before retaining a row. KIS documents a one-day token
lifetime and at-most-once-per-minute reissuance, so this sequence is
inconclusive for credential health, not evidence that the local Paper key pair
must be replaced. `IWM/AMS` remains independently `source_limited` at its
known bad cursor.

## Standing Authority

- Private `KIS_PAPER_*` market-data calls and local retention on `D:` are
  authorized. This goal is data-only and must not call account or order
  endpoints.
- Read local Paper configuration only through the existing strict loader. Never
  print, log, hash into an artifact, commit, or send an App Key, App Secret,
  token, account value, raw response, or `KIS_LIVE_*` value to Claude.
- Do not read `KIS_LIVE_*`, use a live route or real capital, buy data, accept
  unclear rights, publish anything, or put data/artifacts in Git.

## Role-Owned Work

### Codex Orchestrator

Keep `agents/orchestration.md` as a cross-lane-only projection. A KIS or other
provider cooldown belongs to its named worker and must yield to ready
independent work rather than hold the foreground orchestrator in a long sleep.
Do not duplicate Data, Research, or Execution queues there, and do not turn
resource observations into a second goal or an approval gate.

### Data Agent

1. Verify only non-secret configuration facts: complete Paper key pair present,
   non-live mode, fixed virtual market-data host, and sanitized token outcome.
2. Add a shared non-secret five-minute token-request-start spacing guard across
   short-lived data workers. Reuse one in-memory Paper client per finite run;
   never persist a bearer token. This guard is separate from market-page
   throughput and must not slow pages after token issuance.
3. Run one spaced, data-only QQQ/SPY catch-up/capability invocation. Record
   only request categories, counts, continuation outcome, and retained-cache
   metadata. It must not call account, order, or live endpoints.
4. Treat a further sanitized token failure as credential evidence only when it
   occurs after the shared spacing guard in a single-client run. Do not
   brute-force retries or ask the operator to replace values before that kill
   test.
5. After normal token behavior is established, test the overseas-minute
   endpoint's actual historical seek capability in a separately labeled,
   bounded QQQ/SPY probe. Keep an undocumented `KEYB` seed out of the normal
   collector unless the source result proves its semantics; record only the
   supported range/outcome and preserve valid raw data on `D:`.
6. Continue the independent three-window intraday-head schedule. Its partial
   coverage remains Data evidence until an exact contiguous 390-minute QQQ
   regular session exists.

### Engine Research Agent

Keep frozen historical baselines unchanged. The credential incident and partial
head coverage are not model inputs or GPU triggers.

### Execution Agent

Keep Paper routing and account/order schedules unchanged. Do not infer an
order, fill, terminal state, or PnL from a data-worker token outcome.

## Completion Evidence

- A sanitized, spaced single-client result distinguishes token issuance from
  data-endpoint access without claiming a credential fault prematurely.
- The daily index metadata and catch-up result explain QQQ/SPY cursor progress,
  while the minute probe explains only the observed historical capability, with
  no raw rows, secrets, account calls, or orders in the report.
- The collection path yields external waits to its worker/scheduler and leaves
  independent ready work available; no duplicate scheduler, broker route, or
  artifact-in-Git behavior is added.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Improve KIS market-data recovery`
