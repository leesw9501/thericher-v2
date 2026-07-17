# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded artifact-only non-AMAT independent evidence inventory.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by answering the selected duplicate-aware row/key deficit
question before opening GPU, replay, training, or ablation work.

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
- Do not read market-data rows for this inventory unless a future objective
  explicitly opens a data-collection task.
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
   - `D:\thericher-v2\model-artifacts\engine-research-planning\non-amat-independent-evidence-question-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-non-amat-bridge-feasibility-decision-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-non-amat-label-ready-inventory-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, daily-report policy, durable worker policy, or any compute/data
   contract.

## Required Work

1. Consume the planning artifact and existing named metrics artifacts only.
2. Answer this selected question:
   using only existing non-AMAT feasibility, label-ready, and queue-hygiene
   summaries, does non-AMAT evidence outside AMAT-bridge lineage meet the
   duplicate-aware floor for a later model-input pass; if not, what exact
   row/key deficit remains?
3. Keep duplicate-aware counting explicit:
   - count strict label-ready rows,
   - count unique timing-context keys after collapsing threshold variants,
   - separate rows reused from prior AMAT-bridge lineage from fresh independent
     non-AMAT support,
   - preserve referenced local-paper source context as evidence linkage only.
4. Produce one compact external artifact under
   `D:\thericher-v2\model-artifacts\feature-input-stability`.
5. The artifact must decide only one of these:
   - open one later bounded GPU/replay/model-input objective if the floor is
     met with independent evidence, or
   - keep `hold_no_compute` and rotate lanes if the floor is not met.
6. Update `HANDOFF.md`, `agents/engine-research.md`, `agents/data.md`, and
   `agents/review.md` only if needed.
7. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Evidence Floor

- Minimum strict label-ready rows: `8`.
- Preferred strict unique timing-context keys: `8`.
- Evidence must span multiple symbols and must not depend on prior AMAT-bridge
  reuse as fresh independent support.
- Referenced fills must remain `source: local_paper`; diagnostic rows must not
  become fills or broker outcomes.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Inventory non-AMAT independent evidence floor`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data, Docker/GPU, or broker behavior was touched,
- produced artifacts,
- the row/key deficit or the bounded compute objective opened,
- what was intentionally not built,
- next recommended goal.
