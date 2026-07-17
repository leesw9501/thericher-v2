# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Auto-select the next lane as Engine Research and define one bounded
duplicate-aware evidence question before spending GPU time.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution. The operator clarified that ordinary lane choice should not
block progress because all lanes are eventually required. Codex should use the
existing lane-rotation policy and stop only for true operator decisions.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary Codex sidecars may review or inspect bounded evidence, but do not
  build a durable multi-agent platform, scheduler, daemon, coordinator,
  notification loop, dashboard, or auto-commit worker.

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
  threshold search, replay rerun, exit-policy simulation, broker execution,
  data acquisition, Docker/GPU/dependency work, or another review-only pass.
- Do not perform a broad recursive scan of `D:\market_data`.
- Do not turn held evidence into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` for external artifacts.

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
   - `D:\thericher-v2\model-artifacts\review-simplification\post-compaction-handoff-review-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, daily-report policy, durable worker policy, or any compute/data
   contract.

## Required Work

1. Inspect current stateboards and the post-compaction review artifact.
2. Select the smallest useful Engine Research evidence question that could
   justify later GPU time.
3. Keep the question duplicate-aware and bounded. It must specify:
   - the evidence source artifacts or stateboard context it uses,
   - why the question improves feature/model research or PnL attribution,
   - what compute, replay, training, ablation, threshold search, or data
     acquisition remains explicitly closed,
   - what evidence would be enough to open a later bounded GPU or replay goal.
4. Produce one compact external planning artifact under
   `D:\thericher-v2\model-artifacts\engine-research-planning`.
5. Update `HANDOFF.md`, `agents/engine-research.md`, and `agents/review.md`
   only if needed.
6. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Define next engine research evidence question`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data, Docker/GPU, or broker behavior was touched,
- produced artifacts,
- what was intentionally not built,
- next recommended goal.
