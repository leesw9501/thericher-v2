# Next Codex Goal

## Objective

Capture the first new, complete KIS Paper QQQ canary lifecycle through the
already-installed freshness-gated session path.

This is execution-plumbing evidence, not a strategy/model validation. The
existing deterministic QQQ receipt, one-share target resolution, durable intent,
submit/cancel/reconciliation behavior, and source-safe runtime projection own
the action. Historical D1 data and all Research artifacts remain out of scope.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Inspect existing Task Scheduler state and the current source-safe QQQ
   head-cache/session receipts. Do not manually start, stop, duplicate, or
   modify the Data collector or installed intraday-head task.
3. Reattest the existing offline preconditions: current QQQ input, regular
   session gate, deterministic target resolution, intent-before-side-effect,
   route isolation, and ambiguous-outcome reconciliation contract. Do not edit
   the decision table, sizing, freshness budget, or strategy.
4. Use the completed Claude review in `DECISIONS.md`: historical D1 audit status
   does not gate this independent authorized Paper lifecycle.

## Paper Contract

- Only the existing KIS Paper virtual route may read `KIS_PAPER_*`, and only
  after its own fresh eligible receipt passes its current regular-session and
  execution-control checks. Never read or route `KIS_LIVE_*`.
- Preserve the existing target resolution and one-share behavior. Do not add a
  symbol, decision rule, model, ensemble, price rule, size rule, or retry rule.
- Persist the exact durable intent before a broker side effect. An ambiguous
  submit/cancel outcome pauses replacement of that exact intent until the
  existing read-only reconciliation path resolves it; it never becomes a global
  hold or a reason to retry speculatively.
- The installed task remains the owner of collection and session invocation.
  Do not add a per-goal reservation, one-shot wrapper, manual approval gate, or
  duplicate scheduler. This goal's completion observation is the first new
  lifecycle outcome, not a restriction on later correctly scoped Paper work.
- Persist and report only source-safe lifecycle categories, intent/run hashes,
  route mode, and reconciliation status. Do not persist or output credentials,
  account identifiers, balances, prices, broker bodies, fill values, or PnL.
- A clean lifecycle proves plumbing only. It does not validate a model, signal,
  profitability, historical D1 data, or live readiness.

## Parallel Work Packages

1. **Execution:** reattest the existing route's pre-submit and recovery
   invariants, then let the installed fresh-session path own the first new
   eligible Paper lifecycle. Reconcile an exact unknown outcome through the
   existing read-only path only.
2. **Data:** preserve the independent QQQ head-cache/currentness contract and
   report only its source-safe ready/stale/no-intent facts. A stale receipt does
   not cause a manual collector launch or stop other ready lanes.
3. **Temporary Validation:** add or reattest focused coverage for intent
   persistence, route isolation, no-live credentials, fresh-before-account and
   fresh-before-submit checks, cancellation/reconciliation, and source-safe
   artifact projection. Do not simulate a profitability result.
4. **Engine Research:** remain independent. Do not consume canary or historical
   D1 facts as a model, GPU, ensemble, ranking, or PnL input.

## Completion

- A new source-safe QQQ session evidence record reaches `canary_completed` and
  its matching terminal lifecycle/reconciliation evidence is complete, or an
  exact technical failure is preserved and recovered without duplicate submit.
- No live route, model/strategy change, manual duplicate scheduler, broad
  historical-data dependency, secret output, balance/price/fill/PnL output, or
  Paper authority gate is introduced.
- Refresh Execution/Data/Research/orchestration stateboards, replace this file
  with one next objective, verify, commit, push, and continue. If the installed
  task is awaiting its next eligible fresh receipt, keep it scheduled and move
  independent ready work forward rather than foreground-waiting.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add KIS D1 discontinuity census`
