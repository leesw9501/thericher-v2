# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `prospective-spy-paper-session-cycle-v1`: one idempotent, goal-owned
session-cycle that connects the existing Data prospective-SPY completed-bar
observation, frozen Engine baseline, and existing virtual KIS Paper adapter.

The product outcome is a recoverable Paper-only lifecycle from a current,
frozen observation. It is not a claim that a historical static strategy is
profitable, and it must not reuse the completed broad-D1 momentum result.

## Boundaries

- KIS Paper market-data/account/quote/order calls and Paper
  submit/modify/cancel are already authorized by `AGENTS.md`; use only the
  named owned paths. Never read, route, or mention `KIS_LIVE_*`.
- Preserve the frozen prospective-SPY baseline parameters and decision
  semantics. Do not tune it, substitute the static broad-D1 result, select a
  winner, create an ensemble, widen size, or make a PnL/profitability claim.
- A missing, stale, malformed, abstaining, or duplicate observation must
  create only a source-safe no-intent/recovery record and must not load Paper
  configuration, query account/quote, or submit an order.
- On a current eligible `enter`, use only the existing one-share SPY virtual
  Paper canary path with persisted intent, virtual-host pinning, reconciliation,
  and cancellation semantics. No live behavior, public dashboard change, or
  new capital policy is allowed.
- Keep raw data on `D:\market_data` and generated artifacts on
  `D:\thericher-v2\model-artifacts`; do not retain secrets, raw bars, account
  identifiers, or broker payloads in Git, stateboards, logs, or artifacts.
- The external market-session due time belongs to the owned worker/scheduler.
  Do not foreground-wait for it or create a duplicate collector.

## Required Work

1. **Data:** expose or integrate the existing prospective-SPY completed-bar
   observation as one immutable, timestamped session input for the cycle. Keep
   KIS collection and mutable cache ownership inside the existing Data path.
2. **Engine Research:** reattach the existing frozen prospective-SPY baseline
   unchanged and emit only a source-safe categorical `enter` or no-intent
   decision for that session input. No historical backtest or model training.
3. **Execution:** connect the current eligible `enter` branch to the existing
   virtual-Paper adapter. Prove no-intent paths are credential/account/quote/
   order-free; prove an eligible branch is virtual-host-pinned, durable,
   idempotent, and reconciles an unknown prior outcome before another submit.
4. **Integration:** add one owned session-cycle runner or scheduler hook with
   no foreground sleep. It must emit a categorical source-safe receipt for an
   out-of-window or no-intent run and let the existing owner schedule the next
   eligible session.
5. Ask Claude for a short falsification-first route review before relying on
   the first newly integrated eligible Paper submission. A timeout is
   `review_unavailable`, not agreement or a block; preserve the result without
   sending secrets, account facts, or raw market data.

## Completion Evidence

- focused fixture coverage for Data/Engine/Execution integration and all
  no-intent, duplicate, stale, virtual-host, and unknown-outcome branches;
- one source-safe session-cycle receipt from a host and isolated Docker run;
- if no current eligible `enter` occurs, a categorical no-intent/out-of-window
  receipt is completion evidence and the owned worker continues independently;
- if an eligible `enter` occurs, one existing-size virtual-Paper lifecycle has
  durable intent and reconciliation evidence, with no live route;
- refreshed Data, Engine Research, Research Steward, Execution, orchestration,
  and handoff stateboards; required verification, commit, and push.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
