# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one compact MPWR local-paper trade-path and PnL attribution over the
existing MPWR replay-selection events.

This advances PnL attribution by explaining the `24` verified local-paper fills
created by the bounded MPWR-only replay-selection before any broader replay,
training, or exit-policy work.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars in parallel when useful:
  - Engine Research: verify the existing trade-path attribution primitive and
    duplicate-aware summary shape.
  - Data: verify selected MPWR local bars come from the existing Yahoo snapshot
    and no acquisition is needed.
  - Execution/Review: verify local-paper source preservation and no replay,
    gate, or promotion drift.
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
- Do not run model training, ablation, trace compute, trace recompute,
  threshold search, replay rerun, exit-policy simulation, or broker execution.
- Do not download market data into the Git workspace.
- Do not acquire new market data.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Do not include STX, GLW, INTC, QCOM, DELL, WDC, APP, or held
  MRVL/MU/SNDK/COHR symbols.
- Do not turn attribution output into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Preserve original generated fills as `source: local_paper`; any reconstructed
  path context must be `source: diagnostic_overlay`.

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
   contract, attribution contract, or local-paper behavior. If attribution can
   directly call the existing trade-path helper with existing event artifacts
   and selected MPWR bars, prefer that.

## Evidence To Consume

- MPWR replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-mpwr-replay-selection-20260717-r1\metrics.json`
- MPWR threshold-robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\fresh-symbol-mpwr-replay-selection-20260717-r1\metrics.json`
- MPWR probability trace:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace\engine-agent-fresh-symbol-independent-trace-only-batch-20260717-r1-fresh_mpwr\trace.json`
- Known local Yahoo snapshot:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known facts to preserve:

- MPWR is the only symbol in scope.
- The replay-selection completed `3` variants at fixed threshold pairs
  `0.541/0.497`, `0.542/0.497`, and `0.543/0.497`.
- Aggregate replay-selection output was `24` order intents, `24` fills, all
  `source: local_paper`, with no non-local, unknown, or unreadable fill
  evidence.
- Each variant produced `8` fills, PnL `-5.308800000000`, max drawdown
  `19.3140000000`, and final position `0`.
- MPWR trace max probability was `0.550297`, gap `+0.009297`, with `4`
  crossings against fixed descriptive buy threshold `0.541000`.

## Required Work

1. Confirm the facts above from the consumed artifacts.
2. Parse only the three MPWR replay-selection event artifacts and selected MPWR
   local bars needed to attribute the existing fills.
3. Produce one compact external attribution artifact recording:
   - consumed artifact paths,
   - exact event artifacts parsed,
   - local-paper fill source verification,
   - closed/open path counts,
   - gross and fee-aware PnL by threshold variant,
   - duplicate-aware unique market-moment summary if threshold variants repeat
     the same trade path,
   - adverse/favorable excursion context if available from selected local bars,
   - final position reconciliation,
   - no replay, broker, KIS, gate, threshold-search, exit-policy, or promotion
     semantics.
4. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If MPWR attribution shows repeated identical negative paths across
     thresholds, make the next goal a compact hold/rotate decision artifact.
   - If MPWR attribution shows distinct useful path evidence, make the next
     goal a bounded comparison against held fresh-symbol branch evidence,
     still without replay/training unless explicitly justified.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the attribution command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- local-paper source verification,
- diagnostic-overlay source evidence,
- whether a hold/rotate decision is justified and why.

## Suggested Commit Message

`Run MPWR trade-path attribution`

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
