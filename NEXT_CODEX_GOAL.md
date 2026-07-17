# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Prepare one concise operator decision bundle after stale queue hygiene.

This advances review/simplification and backtest/walk-forward validation by
summarizing which queues were retired, which contexts are merely held, and which
strategic lane the operator should choose next. This is a decision point; do not
invent a new compute or data objective without operator direction.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary Codex sidecars may be used as role reviewers for this goal, but they
  are runtime collaborators. Do not build a durable multi-agent platform,
  scheduler, daemon, coordinator, notification loop, dashboard, or auto-commit
  worker.

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
  `D:\thericher-v2\model-artifacts` for external artifacts if needed.

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
   replay contract, attribution contract, local-paper behavior, or daily-report
   policy. A concise operator bundle from existing artifacts/stateboards should
   not need a Claude check.

## Evidence To Consume

- Queue-hygiene artifact:
  `D:\thericher-v2\model-artifacts\review-simplification\review-stale-research-queue-hygiene-20260717-r1\metrics.json`
- Post-MPWR fresh-symbol retirement artifact:
  `D:\thericher-v2\model-artifacts\review-simplification\review-post-mpwr-fresh-symbol-retirement-20260717-r1\metrics.json`
- Current stateboards under `agents/`
- `HANDOFF.md`

Known facts to preserve:

- The fresh-symbol compute branch is retired from the active queue.
- MPWR and MRVL/MU/SNDK/COHR are passive held evidence, not active compute.
- DELL/MPWR/STX/WDC trace-only follow-up and MPWR replay follow-up are retired.
- Non-AMAT model-input/ablation is `hold_no_compute`: only `5` strict
  label-ready rows and `3` strict unique timing-context keys are available
  against the current `min_examples=8` floor, with `0` fresh strict unique
  contexts added by broader inventory outside prior AMAT-bridge reuse.
- No immediate data-lane, Engine Research, GPU, replay, or acquisition follow-up
  is justified by the latest artifacts.
- No operator data is needed now. The ADP missing strict early-label bar is only
  a conditional future need.

## Required Work

1. Produce one concise operator decision bundle under the daily report paths for
   the current KST date:
   - `reports/daily/YYYY-MM-DD-summary.md`
   - `reports/daily/YYYY-MM-DD-metrics.json`
   - `reports/daily/YYYY-MM-DD-next-goal.md`
2. The bundle should ask the operator to choose one next strategic lane, such as:
   - open a new bounded data universe,
   - define the next model-input research question,
   - prepare local-paper/paper-trading readiness work,
   - improve GPU/research infra ergonomics without new schedulers,
   - simplify/review before more compute.
3. Keep the bundle short. Do not create multiple reports or a new report family.
4. Update `HANDOFF.md` and agent stateboards only if needed to point to the
   operator decision bundle.
5. Refresh `NEXT_CODEX_GOAL.md` before ending so the next objective waits for,
   or clearly records, the operator lane decision.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- which sidecars or executable workers were used,
- whether Docker/GPU was used,
- produced report/artifact paths,
- what operator decision is needed,
- what was intentionally not built.

## Suggested Commit Message

`Prepare operator decision bundle`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced reports/artifacts,
- what was intentionally not built,
- next goal or operator decision needed.
