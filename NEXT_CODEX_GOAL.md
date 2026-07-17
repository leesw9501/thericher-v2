# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded fresh-symbol trace/data availability inventory before any
further fresh-symbol replay.

This advances data collection, feature/model research, and backtest validation
by separating “clean local bars exist” from “compatible probability trace
exists” before spending GPU or replay time again.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary sidecars may run in parallel for scoped review, but do not build a
  durable multi-agent platform, scheduler, daemon, coordinator, notification
  loop, or auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not add a new research job kind, executable worker, or CLI.
- Do not run replay, model training, feature-input ablation, broad threshold
  search, or data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Prefer existing `D:\market_data` rows and existing probability traces.
- Keep ranked or reconstructed context labeled as `source: diagnostic_overlay`.
- Do not turn trace availability into an execution threshold, order-intent
  generator, risk rule, broker policy, replay rule, feature rule, gate, or
  model-promotion rule.

## Required First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/README.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Use temporary Codex sidecars for disjoint checks when useful:
   - Data/Infra: verify clean local-bar candidates and existing trace roots
     without broad scans or acquisition.
   - Engine Research: verify compatible trace lineage against the short
     feature-branch model and whether a future trace-compute batch is justified.
   - Review/Execution: verify no replay/order/gate semantics creep in.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Fresh-symbol opportunity prefilter:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-prefilter\engine-agent-fresh-symbol-opportunity-prefilter-20260717-r1\metrics.json`
- Fresh-symbol no-fill probe:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-short-replay-probe-20260717-r1\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Candidate probability trace root:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Record the prefilter result as the starting point:
   - `12` candidates,
   - `5` scored from existing compatible traces,
   - `0` threshold-crossing candidates,
   - AMT closest at max probability `0.539972`, gap `-0.001028`,
   - no replay, no order intents, and no fills.
2. Build one bounded trace/data availability inventory using existing files:
   - existing `snapshot=2026-06-18` local Yahoo rows,
   - existing `candidate-probability-trace` artifacts,
   - the short source-context feature-branch model lineage.
3. Avoid expensive full recursive market-data scans. Reading the single local
   Yahoo snapshot and known trace root is allowed. Start from at most `24`
   fresh symbols:
   - include clean candidates from the prefilter/Data sidecar,
   - include symbols with existing compatible short source-context traces,
   - exclude current branch, prior AMAT-bridge, and immediate no-fill replay
     symbols: ADBE, ADI, ADP, AEM, AMAT, AMZN, BA, AAPL, ABBV, ABT, ACN,
   - continue avoiding AMD and ABNB unless the inventory proves no better
     candidates exist.
4. Produce one compact external inventory artifact recording:
   - candidate symbols,
   - local row counts and first-`240`-bar data-quality warnings,
   - whether a compatible probability trace exists,
   - max probability and threshold gap when a compatible trace exists,
   - whether a future trace-compute batch is justified,
   - exact symbols/windows that would need trace compute,
   - no broker/KIS/credential/network/data-acquisition/replay behavior.
5. Do not run trace compute in this goal. If the inventory justifies trace
   compute, refresh `NEXT_CODEX_GOAL.md` toward one small Engine Research Agent
   trace-compute or replay-selection goal. If it does not, rotate toward an
   execution/paper or review/simplification lane.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused artifact/inventory smoke command,
- any Data Agent runner command used,
- any sidecars used,
- artifact paths written outside Git,
- whether Docker/GPU compute was used and why.

## Suggested Commit Message

`Inventory fresh-symbol trace availability`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced inventory artifacts,
- local-paper source evidence, if any,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
