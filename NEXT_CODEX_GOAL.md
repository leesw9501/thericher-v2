# Next Codex Goal

## Objective

Verify the first finite, rate-safe KIS Paper daily catch-up while continuing the
installed three-window intraday-head collection.

The daily worker now drains ready `QQQ/NAS` and `SPY/AMS` historical cursors
for at most 48 chunks or six hours. It is deliberately finite rather than an
unbounded parallel loop: all KIS Paper market-data requests share one external
1.25-second request-start gate, and an observed rate-limit response creates a
60-second shared cooldown. No verified daily KIS quota is assumed.

The active daily index currently has `QQQ/NAS` and `SPY/AMS` `ready` at
`20210107`; `IWM/AMS` remains scoped `source_limited` at its known invalid
cursor. The historical 1m QQQ/SPY cursors are terminal and must not be
re-downloaded by the historical worker; the independent head cache remains the
fresh-session path.

## Standing Authority

- Private `KIS_PAPER_*` market-data calls and local retention on `D:` are
  authorized. This goal is data-only and must not call account or order
  endpoints.
- Do not read `KIS_LIVE_*`, use a live route or real capital, buy data, accept
  unclear rights, publish anything, expose raw rows, or put data/artifacts in
  Git.
- Existing named Windows tasks own routine KIS-facing runs. Do not overlap a
  manually launched catch-up with a due or already-running copy of the same
  worker.

## Role-Owned Work

### Data Agent

1. Inspect only sanitized daily-index, gate, task, and chunk metadata before
   and after the first catch-up. Record whether QQQ/SPY drain, reach a scoped
   source limit, hit storage protection, or hit the shared rate cooldown.
2. Let the existing `02:35`, `04:35`, and `06:20` KST intraday-head schedule
   continue. After a complete cycle, classify coverage metadata; only an exact
   contiguous 390-minute QQQ regular session becomes a future Research input.
3. Do not repeatedly query IWM's unchanged invalid cursor or terminal
   historical 1m cursor. A different useful source scope may proceed
   independently.

### Engine Research Agent

Keep frozen historical baselines unchanged. Partial prospective head coverage
is not a model sample, candidate selection input, or GPU job trigger.

### Execution Agent

Keep Paper routing and account/order schedules unchanged. Do not infer an
order, fill, terminal state, or PnL from data-worker success.

## Completion Evidence

- Sanitized catch-up output and index metadata explain the QQQ/SPY cursor
  result without raw rows, secrets, account calls, or order calls.
- The common request gate prevents overlapping data workers from exceeding the
  configured pace, and a terminal historical minute cursor avoids redundant
  pages.
- Intraday-head coverage is classified independently; no duplicate scheduler,
  broker route, or artifact-in-Git behavior is introduced.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Accelerate rate-safe KIS data catchup`
