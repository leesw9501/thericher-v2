# Next Codex Goal

## Objective

Build `private-kis-paper-account-snapshot-observer-v1`.

Turn the completed one-shot `kis-readonly` account bridge into the smallest
owned, concurrency-safe observer cadence that keeps the private loopback
dashboard's read-only KIS Paper snapshot useful during its five-minute runtime
TTL. This advances Paper-trading observability only; it is not an order,
strategy, or live feature.

## Hard Boundaries

- Read only `KIS_PAPER_*` through the existing `kis-readonly` bridge. Never
  read, reference, route, log, or persist `KIS_LIVE_*`.
- The observer may call only the bridge's already-attested token plus read-only
  account endpoints. It must never submit, modify, cancel, simulate, or imply
  a broker order, and it must not call quote or market-data endpoints.
- Keep the dashboard credential-free, loopback-only, and snapshot-only. Do not
  turn dashboard refresh into a KIS call, add public serving, or create a
  dashboard order action.
- Retain raw responses, credentials, account identifiers, order identifiers,
  prices, and balances only in the existing sanitized runtime snapshot where
  the contract permits them; never put them in Git, task logs, evidence,
  stateboards, browser screenshots, or new artifacts.
- Reuse the existing one-shot Compose service and its runtime/artifact mounts.
  Do not create a competing bridge, duplicate scheduler, daemon, broad agent
  platform, or unbounded retry loop.
- A missed, rejected, stale, or overlapping invocation must leave a truthful
  unavailable/categorical result, never a fabricated fresh snapshot. It does
  not block independent Data, Research, or Paper work.

## Required Work

1. Run a concise Throughput Review. Data's owned collection and Engine
   preparation remain independent. Reattest the actual complete bridge receipt,
   five-minute snapshot TTL, and existing task-registration conventions.
2. Ask Claude for a short falsification-first drift check before creating a
   recurring schedule, because it widens recurring external reads. Treat a
   timeout or unavailable result as `review_unavailable`, not a block.
3. Design and implement the smallest goal-owned observer worker/task using the
   existing `kis-readonly` command. It must have one owner, bounded overlap,
   a named session/freshness predicate, a source-safe outcome, and a recovery
   action. Derive its cadence from the snapshot TTL and measured bridge scope;
   do not invent a provider quota or durable throttle.
4. Test the observer's schedule/worker contract: only the existing service and
   read-only bridge may run; no live config, order/quote/market-data path,
   duplicate concurrent run, raw account content, or dashboard credential path
   is allowed. Prove stale or failed runs become unavailable rather than old
   facts.
5. Install and run one bounded observer invocation when the named predicate is
   eligible, then reattach only categorical result, timestamps, and safe
   evidence pointer. Inspect the dashboard without printing account values or
   identifiers. Do not wait in the foreground for a later scheduled run.
6. Refresh Execution, Infra, orchestration, RUNBOOK, and HANDOFF with the
   current owner, cadence/recovery fact, evidence pointer, and next action.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Schedule private Paper account observer`
