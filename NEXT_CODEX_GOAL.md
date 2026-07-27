# Next Codex Goal

## Objective

Resolve the two target-local deferred states in the fixed six-symbol KIS Paper
daily-history cache without widening its source scope or restarting completed
targets.

The bounded continuation worker is complete. The current cache has four
terminal target states and exactly two deferred cursors: `MSFT/NAS` with
`daily_response_invalid` at its observed `2017-Q4` boundary, and `NVDA/NAS`
with `transport_failure` at its observed `2010-Q1` boundary. This objective
turns each into a truthful target-local recovery result or resumed cursor; it
does not recreate the whole historical collection.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and all active
   stateboards.
3. Reattach the daily-history index and latest source-safe continuation/cycle
   receipts under `D:\market_data` and
   `D:\thericher-v2\model-artifacts`; do not print raw rows, credentials,
   request headers, account facts, or broker bodies.
4. Ask Claude for a concise falsification-first recovery drift-check. State the
   two failure classes, the exact target-local scope, cache/index evidence,
   route isolation, and the fact that would reject the recovery. Do not send
   secrets, raw rows, account facts, or source values. `review_unavailable` is
   not a hold on this authorized private Data work.

## Required Work

1. Prove the exact deferred state from the durable index and source-safe
   receipts. Recheck that the frozen universe probe, six-symbol panel, and
   QQQ/SPY/IWM catalog hashes remain unchanged before and after the work.
2. Add or extend one bounded target-local recovery path for only `MSFT/NAS` and
   `NVDA/NAS`. It must preserve the durable cursor, immutable snapshots,
   existing 1.0-second shared request gate, 60-second categorical cooldown,
   five-minute cross-process token-start guard, and one-worker ownership.
3. Classify a recovery attempt truthfully. A valid resumed page may advance
   only its own cursor. A repeated structural invalid response, a transport
   failure, an empty terminal page, or non-advancing cursor must remain scoped
   to that target with a durable recovery/source-limit fact. Do not edit the
   index by hand, reset a target opportunistically, or use another provider to
   fill or relabel KIS rows.
4. Add focused tests for exact target allow-listing, preservation of terminal
   targets, recovery classification, stale-due handling, client/token and
   route containment, immutable external evidence, and no foreground
   orchestrator sleep.
5. Run one bounded recovery through the dedicated Data-only Compose profile.
   Record only source-safe aggregate outcome, cursor/coverage buckets,
   accepted/categorical counts, `next_due`, recovery, and route/artifact
   isolation. Continue independent ready work while its worker owns any retry
   due.
6. Refresh the Data, Execution, Research, and orchestration stateboards with
   actual recovery evidence, current bottleneck, and next handoff.

## Hard Boundaries

- Use `KIS_PAPER_*` only in the dedicated Data-only collector/profile. Never
  read or route `KIS_LIVE_*`.
- Preserve `THERICHER_MODE=off`; do not call account, position, open-order,
  quote, order submit, modify, cancel, reconciliation, or live endpoints.
- Do not call Tiingo, buy data, change the six-symbol fixed registry, acquire a
  public historical universe, or blend another source into this cache.
- Do not create a model, GPU campaign, replay, PnL claim, or Paper decision
  from this current-listing cache.
- Do not store raw market data, credentials, or generated artifacts in Git.
- A target-local delay, error, or source limit is evidence for that target only
  and never a global pause or approval hold.

## Completion Evidence

- Tests prove only the two deferred targets can enter the bounded recovery
  path, while complete/source-limited targets remain unchanged.
- One source-safe bounded recovery result records a truthful outcome for both
  targets and preserves cache/index recoverability.
- Independent Validation confirms Data-only mount/route containment, bounded
  recovery behavior, redaction, and frozen-artifact stability.
- No account, order, position, quote, Tiingo, or live broker call occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A target that remains deferred or becomes source-limited
is valid evidence for that target, not a reason to stop another ready lane.

## Suggested Commit Message

`Recover deferred daily history targets`
