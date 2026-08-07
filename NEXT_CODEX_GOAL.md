# Next Codex Goal

## Objective

Build `source-local-ema-local-paper-pnl-attribution-v1`.

Use the completed `source-local-session-reset-ema-mechanics-v1` external replay
receipt and the exact same frozen local QQQ/NAS M1 input to calculate one
cost-aware, aggregate PnL attribution through the existing `source: local_paper`
simulator path. This is a descriptive, source-limited retrospective attribution;
it is not a model-selection, profitability, campaign, or KIS Paper-input result.

## Hard Boundaries

- Do not call KIS, invoke or alter a task, submit/modify/cancel a Paper order,
  or read credentials or any `KIS_LIVE_*` value.
- Do not inspect or commit raw bars, prices, fill events, provider payloads,
  account/order data, credentials, weights, or generated artifacts. Keep
  artifacts under `D:\thericher-v2\model-artifacts`.
- Reuse the exact frozen 15/30 EMA rule, completed-session selection,
  next-bar-open fill semantics, terminal-flat behavior, and fee/slippage model.
  Do not introduce a second simulator, broker route, cost model, strategy, or
  parameter sweep.
- Do not compare candidates, tune after outcomes, rank a strategy, promote a
  result, create a Paper input, allocate GPU, or interpret this 20-session
  source-local result as decision-time-valid or generally profitable.

## Required Work

1. Run a concise Throughput Review and inspect the completed EMA precommit and
   summary plus existing local-paper replay/accounting helpers. Ask Claude only
   if a shared fill, cost, replay, or attribution semantic must change; do not
   wait on a review.
2. Reattach the external parent receipt and freeze its source identity, exact
   rule/cost/fill/terminal semantics, aggregate metric schema, and strongest
   kill test before replaying any input.
3. Build a small Engine-owned/Execution-attested source-safe attribution and
   CLI. It may retain only aggregate closed-trade, gross-delta, fee, net-delta,
   and replay-consistency facts, plus `complete` or `input_unavailable`.
   Write immutable artifacts outside Git.
4. Add focused tests proving external-parent integrity, local-paper-only and
   replayable fills, terminal flatness, fee-aware arithmetic, no future-bar
   influence on prior closed trades, external-artifact-only output, and no
   network/credential/KIS/broker access.
5. Run one CPU-only local-cache smoke without printing raw data, then refresh
   Engine Research, Execution, and orchestration stateboards.

## Verification

Run focused tests and the source-local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add source-local EMA PnL attribution`
