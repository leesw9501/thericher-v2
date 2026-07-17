# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one compact post-compaction handoff review.

This advances review/simplification and backtest/walk-forward validation by
checking whether the lane-5 simplification sequence should pause for operator
direction or open one new bounded non-compute objective. Do not open compute,
data acquisition, broker, Docker/GPU, dependency, scheduler, dashboard, or
durable-platform work from this review.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary Codex sidecars may review stale context, but do not build a durable
  multi-agent platform, scheduler, daemon, coordinator, notification loop,
  dashboard, or auto-commit worker.

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
  threshold search, replay rerun, exit-policy simulation, broker execution, or
  data acquisition.
- Do not perform a broad recursive scan of `D:\market_data`.
- Do not turn held evidence into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` for any external review artifact.

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
   - `D:\thericher-v2\model-artifacts\review-simplification\operator-selected-simplification-review-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\review-simplification\stateboard-active-queue-compaction-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, or daily-report policy. A compact artifact/stateboard review
   should not need a Claude check.

## Required Work

1. Inspect current handoff/stateboards and the two latest review artifacts.
2. Decide whether any bounded non-compute simplification objective remains
   useful, or whether work should pause for operator direction.
3. Produce one compact external review artifact under
   `D:\thericher-v2\model-artifacts\review-simplification` recording:
   - consumed handoff/stateboards/artifacts,
   - whether another bounded non-compute objective is recommended,
   - why compute/acquisition/broker/Docker/platform work remains closed.
4. Update `HANDOFF.md` and `agents/review.md` only if needed.
5. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- whether work should pause or continue with a bounded non-compute objective,
- what was intentionally not built,
- next goal.

## Suggested Commit Message

`Review post-compaction handoff`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced artifacts,
- what was intentionally not built,
- next recommended goal.
