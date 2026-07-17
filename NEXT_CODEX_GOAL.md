# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Wait for the operator to choose the next strategic lane.

This advances review/simplification and backtest/walk-forward validation by
preventing stale held evidence from turning into automatic compute or process
growth. Do not invent a new research, data, replay, or infra objective without
the operator's lane choice.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary Codex sidecars are runtime collaborators only. Do not build a
  durable multi-agent platform, scheduler, daemon, coordinator, notification
  loop, dashboard, or auto-commit worker while waiting for lane choice.

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
- Do not store generated GPU/model artifacts or market data in the repo.

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
   - `reports/daily/2026-07-17-summary.md`
   - `reports/daily/2026-07-17-metrics.json`
   - `reports/daily/2026-07-17-next-goal.md`

## Operator Decision Needed

Queue hygiene found no ready bounded compute question. The latest daily bundle
asks the operator to choose exactly one next strategic lane:

1. Open a new bounded data universe.
2. Define the next model-input research question.
3. Prepare local-paper or paper-trading readiness work.
4. Improve GPU/research infra ergonomics without schedulers.
5. Run another simplification/review pass before more compute.

Known facts to preserve:

- Fresh-symbol compute, DELL/MPWR/STX/WDC trace-only follow-up, MPWR replay
  follow-up, and post-MPWR Data follow-up are retired from active queue context.
- MPWR and MRVL/MU/SNDK/COHR are passive held evidence, not active compute.
- Non-AMAT model-input/ablation is `hold_no_compute`: only `5` strict
  label-ready rows and `3` strict unique timing-context keys are available
  against `min_examples=8`, with `0` fresh strict unique contexts added outside
  prior AMAT-bridge reuse.
- No immediate data-lane, Engine Research, GPU, replay, or acquisition follow-up
  is justified by the latest artifacts.
- No operator data is needed now. The ADP missing strict early-label bar is only
  a conditional future need.

## Required Work

1. Ask the operator to choose exactly one lane from the list above.
2. Do not edit code, run compute, acquire data, or create new workflow
   scaffolding while waiting for the decision.
3. After the operator chooses a lane, replace this file with one single next
   objective tied to that lane and the relevant engine loop.

## Suggested Commit Message

`Record operator lane decision`

## Completion Report

If the operator has not chosen a lane yet, report that work is paused on the
lane decision and list the five options. If a lane is chosen later, report the
new single objective and any files changed.
