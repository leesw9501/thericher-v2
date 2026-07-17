# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded MPWR-only broker-free local-paper replay-selection using the
existing probability trace.

This advances backtest and walk-forward validation by testing whether the
single fresh-symbol trace selected by the planning artifact can create
replayable local-paper evidence, without expanding symbol scope or rerunning
model compute.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars in parallel when useful:
  - Engine Research: verify the existing trace-to-replay primitive/command.
  - Data: verify MPWR uses existing local Yahoo rows and no acquisition.
  - Execution/Review: verify broker-free local-paper-only replay and no gate or
    promotion drift.
- These sidecars are runtime collaborators. Do not build a durable multi-agent
  platform, scheduler, daemon, coordinator, notification loop, dashboard, or
  auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, dashboard, or auto-commit worker.
- Do not run model training, ablation, trace recompute, threshold search,
  exit-policy simulation, or broker execution.
- Do not download market data into the Git workspace.
- Do not acquire new market data.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Local-paper replay is allowed only through the existing broker-free local
  paper research path. Any generated fills must remain labeled
  `source: local_paper`.
- Do not include STX, GLW, INTC, QCOM, DELL, WDC, APP, or held
  MRVL/MU/SNDK/COHR in the replay.
- Do not turn replay output into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.

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
   job kind, dispatch path, agent governance, artifact contract, replay
   contract, or local-paper behavior. If MPWR replay can directly call the
   existing threshold-robustness/local-paper primitive with the existing trace
   artifact and no code changes, prefer that.

## Evidence To Consume

- Fresh-symbol trace-comparison planning artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-trace-comparison-replay-planning-20260717-r1\metrics.json`
- Independent fresh-symbol trace-only batch:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-independent-trace-only-batch-20260717-r1\metrics.json`
- MPWR probability trace:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-independent-trace-only-batch-20260717-r1-fresh_mpwr\trace.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
- Known local Yahoo snapshot:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known facts to preserve:

- MPWR is the only future replay candidate selected by the planning artifact.
- MPWR max probability was `0.550297`, gap `+0.009297`, with `4` crossings
  against fixed descriptive buy threshold `0.541000`.
- STX, GLW, INTC, and QCOM remain comparison context only.
- DELL and WDC remain non-crossing context.
- APP remains deferred as a source-context training symbol.
- MRVL, MU, SNDK, and COHR remain held after duplicate-aware path/PnL evidence.

## Required Work

1. Confirm the facts above from the consumed artifacts.
2. Run exactly one bounded MPWR-only broker-free local-paper replay-selection
   using existing trace evidence only:
   - `max_bars=240`,
   - existing `snapshot=2026-06-18`,
   - existing MPWR probability trace,
   - fixed threshold pairs `0.541/0.497`, `0.542/0.497`, and `0.543/0.497`,
   - artifacts outside Git.
3. Do not recompute traces, run inference, train, ablate, search thresholds,
   simulate exits, acquire data, or add symbols.
4. Produce one compact external replay-selection artifact recording:
   - consumed artifact paths,
   - fixed threshold pairs,
   - replay variant metrics,
   - local-paper order intent and fill counts,
   - local-paper fill source verification,
   - PnL/drawdown/final position evidence,
   - no broker/KIS/gate/promotion semantics.
5. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If MPWR produces fills, make the next goal a compact trade-path/PnL
     attribution over the MPWR local-paper events before any broader replay or
     model work.
   - If MPWR produces zero fills, make the next goal a compact zero-fill
     opportunity attribution or rotate away from fresh-symbol work.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the replay command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- local-paper source verification,
- whether future attribution is justified and why.

## Suggested Commit Message

`Plan fresh-symbol replay selection`

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
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
