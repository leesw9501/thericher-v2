# Next Codex Goal

## Objective

Restore KIS Paper **market-data** authentication and then finish the finite,
rate-safe daily catch-up for `QQQ/NAS` and `SPY/AMS`.

The first committed catch-up invocation on 2026-07-24 reached the Paper token
endpoint and returned only the safe `auth_rejected` category before it retained
a row. The shared request gate recorded no rate-limit event, so this is not a
daily or per-second quota conclusion. The local Paper credential pair was
present to the data-only container but KIS did not issue a token. `IWM/AMS`
remains independently `source_limited` at its known bad cursor.

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

### Data Agent

1. Verify only non-secret configuration facts: complete Paper key pair present,
   non-live mode, fixed virtual market-data host, and sanitized token outcome.
2. If KIS continues to return `auth_rejected`, ask the operator to confirm or
   replace the active KIS **Paper** App Key/App Secret in local `.env`; give no
   value in the report. Do not brute-force token retries.
3. As soon as a token succeeds, run the existing finite catch-up worker. It
   reuses one Paper client, starts all requests through the shared 1.25-second
   gate, and stops after drain, 48 chunks, six hours, a source limit, storage
   protection, recovery need, or categorical rate cooldown.
4. Continue the independent three-window intraday-head schedule. Its partial
   coverage remains Data evidence until an exact contiguous 390-minute QQQ
   regular session exists.

### Engine Research Agent

Keep frozen historical baselines unchanged. The credential incident and partial
head coverage are not model inputs or GPU triggers.

### Execution Agent

Keep Paper routing and account/order schedules unchanged. Do not infer an
order, fill, terminal state, or PnL from a data-worker token outcome.

## Completion Evidence

- A sanitized token outcome identifies either restored Paper market-data access
  or the exact operator credential action still needed.
- On restored access, the daily index metadata and catch-up result explain the
  QQQ/SPY cursor progress without raw rows, secrets, account calls, or orders.
- The shared rate gate and terminal historical-minute handling remain intact;
  no duplicate scheduler, broker route, or artifact-in-Git behavior is added.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Record KIS market-data authentication recovery`
