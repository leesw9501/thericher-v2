# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Pause for operator direction and choose the next strategic lane.

This advances review/simplification by preventing review-only work from
becoming process scaffolding. The lane-5 simplification sequence is complete:
stale queues were retired, Engine/Data/Infra active queues were compacted, and
the post-compaction handoff review found no further useful bounded
non-compute simplification objective.

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
  data acquisition, Docker/GPU/dependency work, or another review-only pass
  until the operator chooses a lane.
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
   behavior, daily-report policy, or any durable worker policy.

## Required Work

Ask the operator to choose exactly one next strategic lane. Do not start
implementation until the operator chooses.

Recommended lanes:

1. Engine Research: define one new duplicate-aware evidence question before
   spending GPU time.
2. Data: define one exact data-collection or data-quality objective with stop
   rules.
3. Execution/Paper: prepare the next broker-free paper-loop or risk-control
   slice without KIS credentials.
4. Infra: improve reproducibility only if a concrete runtime bottleneck is
   selected.
5. Review/Simplification: only if tied to a concrete engine-loop risk, not
   another general cleanup pass.

## Verification

If the next task only asks for operator direction, no tests are required. Once
a lane is selected and implementation changes are made, run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Choose next strategic lane`

## Completion Report

When a lane is selected in a future task, report:

- chosen lane,
- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data, Docker/GPU, or broker behavior was touched,
- what was intentionally not built,
- next recommended goal.
