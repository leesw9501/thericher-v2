# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Data Agent lane-rotation inventory for the next independent
evidence batch.

This advances data collection and feature/model research by using existing
`D:\market_data` rows plus external artifact provenance to decide what, if
anything, should be investigated after the held MRVL/MU/SNDK/COHR fresh-symbol
branch.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, actually use temporary Codex sidecars in parallel when useful:
  - Data: verify inventory scope and whether existing local data is enough.
  - Engine Research: identify which inventory result could become a bounded
    future research question.
  - Execution/Review: verify no source-separation, broker, gate, or process
    sprawl drift.
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
- Do not run model training, ablation, trace recomputation, replay reruns,
  threshold search, exit-policy simulation, or broker/local-paper execution.
- Do not download market data into the Git workspace.
- Do not acquire new market data unless it is no-auth, lawful,
  license-compatible, narrowly useful for this inventory, and stored outside
  Git under `D:\market_data`.
- Stop acquisition attempts when sources require credentials/payment/manual
  access, licensing is unclear, two automated attempts fail for the same
  source, or more data no longer improves this objective.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep inventory rows and provenance summaries labeled as
  `source: diagnostic_overlay`.
- Do not turn the inventory into a replay trigger, execution threshold,
  order-intent generator, risk rule, broker policy, feature rule, gate, or
  model-promotion rule.

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
   job kind, dispatch path, agent governance, artifact contract, or acquisition
   contract. If the inventory can be done with the existing Data Agent runner
   or a direct artifact script, prefer that over adding code.

## Evidence To Consume

- Path-shape comparison artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-simplification\engine-agent-fresh-symbol-replay-path-shape-comparison-20260717-r1\metrics.json`
- Duplicate-aware simplification artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-replay-selection-duplicate-aware-decision-20260717-r1\metrics.json`
- Data Agent trace/data availability artifact:
  `D:\thericher-v2\model-artifacts\data-agent\fresh-symbol-trace-data-availability-20260717-r1\metrics.json`
- Known local Yahoo snapshot:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known facts to confirm:

- The MRVL/MU/SNDK/COHR branch is held for replay/training.
- The path-shape comparison recommends no model, replay, or exit-timing
  follow-up for that branch.
- Earlier data inventory listed trace-missing clean candidates including DELL,
  MPWR, STX, APP, and WDC, plus any remaining clean candidates not yet consumed.

## Required Work

1. Confirm the held branch facts above and exclude MRVL/MU/SNDK/COHR from any
   compute recommendation.
2. Inventory a useful, bounded subset of existing local data and artifact
   provenance for the next independent evidence batch. Avoid expensive full
   recursive scans unless the known artifacts are insufficient.
3. Prefer the existing Data Agent runner if it fits; otherwise use a direct
   artifact-only script. Do not add a new worker or job kind.
4. Summarize candidate rows by symbol with:
   - local data availability,
   - first-`240` bar cleanliness if already available cheaply,
   - compatible trace availability,
   - prior branch/exclusion reason,
   - whether a future trace-only GPU question is justified.
5. Produce at most one compact external inventory artifact recording:
   - consumed artifact paths,
   - market-data roots inspected,
   - acquisition attempts and stop reason, if any,
   - candidate list and exclusions,
   - recommendation for the next engine lane,
   - no promotion/gate/execution-rule semantics.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If enough independent clean candidates exist, the next goal may be a
     small trace-only Engine Research question.
   - If not, rotate to execution/paper readiness or review/simplification
     instead of forcing compute.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the inventory command or focused smoke used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact path, if any,
- whether future GPU trace/replay/model work is justified.

## Suggested Commit Message

`Compare fresh-symbol path shapes`

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
- local-paper source evidence carried forward,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
