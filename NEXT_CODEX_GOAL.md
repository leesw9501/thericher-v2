# Next Codex Goal

## Objective

Add and run one bounded token-reusing continuation worker for the existing
fixed six-symbol KIS Paper daily-history cache.

The first three real collection cycles proved that the isolated cache can
advance at roughly 28--33 accepted pages per minute, but a short-lived Compose
process cannot retain its already-valid in-memory token across a categorical
cooldown. The worker must improve sustained historical coverage without an
orchestrator foreground wait, request flood, new dataset meaning, broker route,
or public service.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and all active
   stateboards.
3. Reattach the fixed NAS daily-history index and latest source-safe receipts
   under `D:\market_data` and `D:\thericher-v2\model-artifacts`; do not print
   raw rows, credentials, or broker bodies.
4. Ask Claude for a concise falsification-first drift-check before widening the
   collector into a token-reusing continuation worker. Do not send secrets,
   account facts, raw rows, or source values. `review_unavailable` is not a hold
   on this authorized private Data work.

## Required Work

1. Extend the dedicated daily-history CLI/profile so one bounded worker retains
   one in-memory Paper client/token through its own verified retry due times and
   resumes the same durable cache cursor without a new token POST per cycle.
2. Bound the worker by a named total runtime and global page/chunk budget. It
   may wait only inside its owned process for a source-safe `next_due`; it must
   exit truthfully on completion, source limit, storage floor, unknown recovery,
   or its bounded runtime/budget. Codex must not foreground-sleep for it.
3. Preserve the existing 1.0-second shared request-start gate and measured
   categorical cooldown. Do not infer a daily quota, lower the gate, create
   parallel workers for the same cache, or issue a request flood.
4. Emit one source-safe receipt per internal cycle plus a final aggregate
   continuation summary: cumulative accepted/categorical counts, elapsed bucket,
   client/token reuse fact, cursor projection, `next_due`, stop reason, and
   recovery class. Keep raw rows only in the existing D: cache.
5. Add focused tests proving client/token reuse after a retry wait, global
   bounds, no foreground-orchestrator sleep seam, durable resume/orphan safety,
   exact daily-only route isolation, canonical Compose roots, and no
   account/order/quote/live path.
6. Run one real bounded continuation through the dedicated Compose profile.
   Recheck that the frozen probe, panel, and QQQ/SPY/IWM catalog hashes remain
   unchanged. Update the Data stateboard with actual pace, coverage, estimate
   or `unknown`, ETA bucket or `unknown`, `next_due`, and recovery.

## Hard Boundaries

- Use `KIS_PAPER_*` only in the dedicated Data-only collector/profile. Never
  read or route `KIS_LIVE_*`.
- Preserve `THERICHER_MODE=off`; do not call account, position, open-order,
  order submit, modify, cancel, reconciliation, quote, or live endpoints.
- Do not call Tiingo, use paid data, change the fixed registry, or acquire a
  public historical universe.
- Do not create a model, GPU campaign, replay, PnL claim, or Paper decision
  from this current-listing cache.
- Do not store raw market data, credentials, or generated artifacts in Git.
- A source delay or failed page applies only to the owned worker. Persist it
  truthfully and continue every independent ready lane.

## Completion Evidence

- The continuation worker/profile reuses one in-memory client/token across at
  least one eligible retry cycle or records why that source condition was not
  encountered within its bound.
- Source-safe final summary and Data stateboard show cumulative progress,
  current cursor, pacing, remaining estimate/ETA category, `next_due`, and
  recovery state.
- Independent Validation confirms Data-only route/mount containment, redaction,
  bounds, and resumability.
- No account, order, position, quote, Tiingo, or live broker call occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A source-limited or recoverable partial worker is
evidence for that worker, not a reason to halt a different ready lane.

## Suggested Commit Message

`Reuse token for bounded daily history continuation`
