# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add one bounded broker-free local-paper replay invariant audit.

This advances paper trading and PnL attribution by making existing local-paper
fills and deterministic account replay easier to verify before future model
work feeds the paper loop.

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
   - `agents/execution.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/infra.md`
   - `agents/review.md`
   - `D:\thericher-v2\model-artifacts\review-simplification\non-amat-held-branch-retirement-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, daily-report policy, durable worker policy, or any compute/data
   contract. A small invariant helper/test inside the existing local-paper
   boundary does not require Claude unless it changes replay behavior.

## Required Work

1. Inspect the existing local-paper simulator, event/fill metadata, account
   replay, and tests.
2. Add the smallest useful invariant audit for existing local-paper replay. It
   should verify source separation and deterministic accounting without broker
   access.
3. Keep it local-only and focused. Prefer a helper plus focused tests over a new
   framework, report family, gate, daemon, or dashboard.
4. If an external smoke artifact is useful, write one compact artifact under
   `D:\thericher-v2\model-artifacts\execution-paper`.
5. Update `HANDOFF.md`, `agents/execution.md`, and other stateboards only if
   needed.
6. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Add local paper replay invariant audit`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data acquisition, Docker/GPU, or broker behavior was touched,
- produced artifacts,
- invariant added,
- what was intentionally not built,
- next recommended goal.
