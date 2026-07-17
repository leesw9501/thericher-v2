# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one small Review/Simplification pass to retire or compact the non-AMAT
branch context as passive evidence.

This advances feature/model research and backtest and walk-forward validation
by preventing a known `hold_no_compute` branch from repeatedly re-entering the
active queue without fresh independent evidence.

## Current State

- Non-AMAT evidence-floor inventory kept the branch `hold_no_compute`:
  `5/8` strict rows, `3/8` strict unique keys, `0` fresh rows/keys outside prior
  AMAT-bridge reuse.
- Data source-context inventory found the blocker is not primarily broad raw
  local-data availability.
- Primary blockers are prior AMAT-bridge provenance reuse and missing
  local-paper label context.
- The only explicit raw gap is conditional ADP `2026-06-09T14:05:00Z`; no
  immediate operator data request or no-auth acquisition is justified.

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
  data acquisition, Docker/GPU/dependency work, or another broad review pass.
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
   - `agents/review.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `D:\thericher-v2\model-artifacts\data-agent\non-amat-source-context-inventory-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\feature-input-stability\non-amat-independent-evidence-floor-inventory-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, daily-report policy, durable worker policy, or any compute/data
   contract.

## Required Work

1. Confirm whether non-AMAT branch context can be retired from active queues and
   kept only as passive evidence until a future objective names a fresh
   independent evidence source.
2. Keep the review bounded to the two latest external artifacts and relevant
   stateboard text.
3. Produce at most one compact external review artifact under
   `D:\thericher-v2\model-artifacts\review-simplification`.
4. Update `HANDOFF.md`, `agents/review.md`, `agents/engine-research.md`, and
   `agents/data.md` only if needed.
5. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Retire non-AMAT held branch context`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data acquisition, Docker/GPU, or broker behavior was touched,
- produced artifacts,
- what was retired or kept passive,
- what was intentionally not built,
- next recommended goal.
