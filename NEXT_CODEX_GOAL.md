# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Engine Research trace-only GPU batch for DELL, MPWR, STX, and
WDC.

This advances feature/model research by filling the trace gap identified by
the Data Agent lane-rotation inventory, while keeping replay, local-paper
execution, model training, and threshold iteration held.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, actually use temporary Codex sidecars in parallel when useful:
  - Engine Research: verify trace-only command shape and threshold context.
  - Data: verify DELL/MPWR/STX/WDC local rows and no acquisition need.
  - Execution/Review: verify no replay/order/gate semantics.
- These sidecars are runtime collaborators. Do not build a durable multi-agent
  platform, scheduler, daemon, coordinator, notification loop, dashboard, or
  auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not run local-paper replay or create order intents/fills.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, dashboard, or auto-commit worker.
- Do not run model training, ablation, replay reruns, threshold search,
  exit-policy simulation, or broker/local-paper execution.
- Do not download market data into the Git workspace.
- Do not acquire new market data.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep trace candidate summaries labeled as `source: diagnostic_overlay`.
- Do not turn trace probabilities into replay triggers, execution thresholds,
  order-intent generators, risk rules, broker policies, feature rules, gates,
  or model-promotion rules.

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

3. Ask Claude CLI for a short drift-check before adding or changing any helper,
   job kind, dispatch path, agent governance, artifact contract, or replay
   contract. If the trace batch can directly call the existing trace primitive
   or existing Engine Research Agent runner without code changes, prefer that.

## Evidence To Consume

- Data Agent lane-rotation inventory:
  `D:\thericher-v2\model-artifacts\data-agent\data-agent-fresh-symbol-lane-rotation-inventory-20260717-r1\metrics.json`
- Fresh-symbol trace-only batch for prior symbols:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-trace-only-batch-20260717-r1\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Known local Yahoo snapshot:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known facts to confirm:

- MRVL, MU, SNDK, and COHR are held and must not be included.
- GLW, INTC, and QCOM already have crossing traces; do not replay them here.
- APP is deferred because it is marked as a source-context training symbol.
- DELL, MPWR, STX, and WDC have clean first-`240` local Yahoo windows and no
  compatible short source-context trace.

## Required Work

1. Confirm the lane-rotation inventory facts above.
2. Run or prepare exactly one bounded trace-only GPU batch for DELL, MPWR, STX,
   and WDC using the existing trace primitive/path:
   - `max_bars=240`,
   - existing `snapshot=2026-06-18`,
   - existing short source-context feature branch,
   - artifacts outside Git.
3. Do not run replay, local paper, training, ablation, threshold search, or exit
   simulation.
4. Produce one compact external batch summary recording:
   - consumed artifact paths,
   - per-symbol trace artifact paths,
   - probability min/mean/max,
   - threshold gap against the fixed descriptive buy threshold,
   - threshold crossing counts,
   - source/model/data lineage,
   - no replay/order/gate semantics.
5. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If one or more of DELL/MPWR/STX/WDC cross the fixed descriptive threshold,
     make the next goal a compact trace-comparison or replay-selection planning
     artifact first, not immediate replay.
   - If none cross, rotate away from fresh-symbol trace compute.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the trace command used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- whether future replay/model work is justified.

## Suggested Commit Message

`Inventory next fresh-symbol trace batch`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced artifacts,
- local-paper source evidence carried forward, if any,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
