# Next Codex Goal

## Objective

Connect the separate NAS D1 forward cache to one bounded, automatic prospective
shadow-observation loop: collect at most once for each newly completed US
equity D1 session, then consume the cache only when its fixed six-symbol,
three-session common window is complete.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattach the frozen NAS panel, forward-cache index, and first source-safe
   forward receipt. Confirm that the frozen panel remains unchanged and record
   the current all-six common-session count without printing raw rows.
3. Ask Claude for a concise falsification-first check of the proposed schedule
   scope and the forward-cache-to-observer temporal boundary. If local OAuth is
   still expired, record `review_unavailable` and continue this private,
   non-promoting package.

## Contract

- Data owns the forward-cache maintenance trigger and source provenance. Engine
  Research owns the read-only prospective consumer. Validation remains
  independent; Execution has no assigned broker work.
- Use only the existing KIS Paper market-data client and the fixed six-symbol
  NAS D1 forward profile. Do not call account, position, order, quote, or live
  endpoints; do not read `KIS_LIVE_*`, submit an order, or expose data publicly.
- A goal-owned Windows scheduler may invoke the dedicated Docker profile after
  a completed US session, but its worker must be idempotent, bounded to one
  current-D1 page per symbol, observable through source-safe receipts, and
  recoverable. It must not foreground-wait or invoke a parallel collector for
  the same cache.
- Retain raw rows only under the existing D: forward-cache root and generated
  receipts only under the configured D: artifact root. Never write raw rows,
  credentials, account data, model weights, or provider bodies to Git.
- Keep the frozen historical panel immutable. A valid forward duplicate may
  advance source-safe accepted-page evidence but must not replace snapshots.
  Transient faults are `deferred`; `source_limited` requires evidence for a real
  endpoint/data limitation.
- The current listing basket is not a point-in-time universe. Do not select,
  tune, rank, ensemble, promote, or create a Paper action from cache coverage
  or a prospective observation.

## Work

1. **Data:** implement or adapt one idempotent goal-owned schedule that invokes
   the existing `kis-paper-daily-nas-forward` Docker profile once after each
   eligible completed D1 session. Reattach its last receipt/cache before a new
   call and leave unrelated schedules untouched.
2. **Engine Research:** extend the NAS shadow observer's input boundary to
   consume the verified historical-plus-forward projection in memory. It must
   emit a source-safe no-op or `input_unavailable` result below three common
   sessions and run the already frozen observer path only when the exact common
   window exists.
3. **Validation:** add focused tests for schedule idempotency, no credential or
   broker route in the offline consumer, unchanged frozen panel, strict three-
   session all-six eligibility, and source-safe recovery receipts.
4. **Orchestration:** run one bounded offline smoke. A future session waiting
   state belongs only to the scheduler; continue another ready lane rather than
   holding the company objective.

## Completion

- The daily forward collector has one bounded, recoverable automatic trigger
  with source-safe evidence and no account/order/live surface.
- The prospective observer reads a verified in-memory historical-plus-forward
  projection and cannot consume an incomplete or non-common six-symbol window.
- Focused tests cover the schedule, cache-to-observer boundary, and route
  isolation. Refresh stateboards and replace this file with exactly one next
  objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Automate NAS D1 forward observation`
