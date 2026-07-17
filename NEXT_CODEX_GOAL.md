# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded queue-hygiene pass over older Engine Research and Data
stateboard handoffs.

This advances backtest and walk-forward validation by retiring stale active
queue context and surfacing the next independent non-fresh-symbol evidence
question, without running compute or growing process.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars only if useful:
  - Review: identify stale queue/context sprawl.
  - Engine Research: identify one next independent non-fresh-symbol evidence
    question without queueing compute.
  - Data/Infra: verify no data acquisition, broad scan, Docker, or dependency
    work is needed.
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
  threshold search, replay rerun, exit-policy simulation, broker execution, or
  data acquisition.
- Do not perform a broad recursive scan of `D:\market_data`.
- Do not turn queue-hygiene output into execution thresholds, risk rules,
  broker policies, replay rules, feature rules, gates, or model-promotion
  rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` for any external artifact.

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
   job kind, dispatch path, agent governance, artifact contract, data contract,
   replay contract, attribution contract, or local-paper behavior. If the pass
   can be produced by reading stateboards and existing artifact summaries with
   a one-off script, prefer that.

## Evidence To Consume

- Post-MPWR fresh-symbol retirement artifact:
  `D:\thericher-v2\model-artifacts\review-simplification\review-post-mpwr-fresh-symbol-retirement-20260717-r1\metrics.json`
- `agents/engine-research.md`
- `agents/data.md`
- `agents/review.md`
- `HANDOFF.md`

Known facts to preserve:

- The fresh-symbol compute branch is retired from the active queue.
- MPWR and MRVL/MU/SNDK/COHR are passive held evidence, not active compute.
- No immediate data-lane, Engine Research, GPU, replay, or acquisition follow-up
  is justified by the latest fresh-symbol artifacts.
- Longer candidate training is held until a future artifact defines enough
  independent duplicate-aware context.

## Required Work

1. Inspect older Engine Research and Data stateboard handoffs for stale active
   queue entries that were already resolved by later artifacts.
2. Produce one compact external queue-hygiene artifact recording:
   - consumed stateboards/artifacts,
   - stale context retired,
   - active held context that remains passive,
   - one recommended next independent non-fresh-symbol evidence question, or a
     clear reason no such question is ready.
3. Update `HANDOFF.md` and agent stateboards only as needed to keep queues clean.
4. Refresh `NEXT_CODEX_GOAL.md` again before ending with one single objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the queue-hygiene command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- what stale context was retired or held,
- what lane should rotate next and why.

## Suggested Commit Message

`Clean stale research queue context`

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
- local-paper source evidence if referenced,
- diagnostic-overlay source evidence if referenced,
- what was intentionally not built,
- next goal.
