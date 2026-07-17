# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run the first bounded fresh-symbol trace-only GPU batch before any further
fresh-symbol replay.

This advances feature/model research and backtest validation by using the
existing short source-context model to compute compatible probability traces for
clean fresh symbols, then deciding whether replay is even worth a later goal.

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
- Do not run local-paper replay in this goal.
- Do not run model training, feature-input ablation, broad threshold search, or
  data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Prefer the existing Docker `research` path with PyTorch CUDA for trace
  inference. Keep base/runtime dependencies torch-free.
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
   - Engine Research: verify trace-only execution shape and source-model
     compatibility.
   - Infra: verify Docker daemon, `research` service, CUDA visibility, and
     artifact mounts after the Windows restart.
   - Review/Execution: verify no replay/order/gate semantics creep in.

4. Ask Claude CLI for a short drift-check before adding or changing any
   research-job dispatch path. If an existing Docker command can run trace-only
   safely, prefer that over adding code.

## Evidence To Consume

- Trace/data availability inventory:
  `D:\thericher-v2\model-artifacts\data-agent\fresh-symbol-trace-data-availability-20260717-r1\metrics.json`
- Fresh-symbol opportunity prefilter:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-prefilter\engine-agent-fresh-symbol-opportunity-prefilter-20260717-r1\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Candidate probability trace root:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Confirm the inventory result:
   - `17` inventory candidates,
   - `5` compatible short source-context traces,
   - `0` compatible threshold crossings,
   - `12` clean local first-`240` candidates missing compatible traces,
   - no trace compute, no replay, no order intents, and no fills.
2. Run one bounded trace-only batch for:
   - MRVL, COHR, MU, GLW, INTC, SNDK, QCOM.
3. Use the exact local data window from the inventory:
   - Yahoo snapshot:
     `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   - `max_bars=240`
   - `2026-06-09T13:30:00+00:00` through
     `2026-06-09T17:29:00+00:00`
   - slice IDs: `fresh_mrvl`, `fresh_cohr`, `fresh_mu`, `fresh_glw`,
     `fresh_intc`, `fresh_sndk`, `fresh_qcom`.
4. Use the short source-context model lineage from:
   `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`.
5. Prefer an existing trace-only primitive through Docker `research`. If the
   current single-shot runner cannot dispatch trace-only work, add the smallest
   bounded trace-only dispatch needed inside the existing research-job/Engine
   Research Agent path after Claude drift-check. Do not add a new daemon,
   scheduler, durable worker, dashboard, or broad platform.
6. Produce one compact external trace-batch artifact recording:
   - symbols and windows traced,
   - source model and data-source compatibility,
   - probability count, max probability, threshold gap, and crossing count,
   - CUDA/Docker readiness and artifact root,
   - no replay/order/fill/broker/KIS/credential/network/data-acquisition
     behavior.
7. If at least one compatible trace crosses the fixed descriptive buy threshold
   `0.541000`, refresh `NEXT_CODEX_GOAL.md` toward one small broker-free
   local-paper replay-selection goal. If none cross, rotate to review or a
   different Engine Research input question instead of replaying.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the trace-only command used,
- any focused trace-batch smoke/assertion command,
- any sidecars used,
- whether Docker/PyTorch CUDA was used and where artifacts were written,
- whether a future replay is justified.

## Suggested Commit Message

`Run fresh-symbol trace-only batch`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced trace artifacts,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
