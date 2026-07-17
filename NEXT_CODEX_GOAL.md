# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Data source-context inventory for the non-AMAT evidence deficit.

This advances data collection, feature/model research, and backtest and
walk-forward validation by determining whether the remaining non-AMAT
duplicate-aware evidence shortfall is caused by local data availability,
artifact provenance, or missing local-paper label context.

## Current State

- Non-AMAT independent evidence remains `hold_no_compute`.
- Current independent floor: `5/8` strict label-ready rows and `3/8` strict
  unique timing-context keys.
- Fresh support outside prior AMAT-bridge reuse: `0` strict rows and `0` strict
  unique keys.
- Broader inventory reaches only `13` rows and `6` keys by reusing prior
  AMAT-bridge lineage, so it is not fresh independent support.

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
  Docker/GPU/dependency work, or another review-only pass.
- Do not acquire or download market data in this pass.
- Do not perform a broad recursive scan of `D:\market_data`.
- Do not turn held evidence into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` for external artifacts.

## Allowed Data Scope

- Consume existing named metrics artifacts and stateboard context first.
- Shallow metadata checks under known `D:\market_data` roots are allowed.
- Exact local row availability checks are allowed only for symbols/timestamps
  named by the consumed artifacts.
- Do not copy, mutate, normalize, or acquire market data.

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
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`
   - `D:\thericher-v2\model-artifacts\feature-input-stability\non-amat-independent-evidence-floor-inventory-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\engine-research-planning\non-amat-independent-evidence-question-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-non-amat-label-ready-inventory-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before changing architecture,
   promotion rules, agent governance, helper/job contracts, replay/local-paper
   behavior, daily-report policy, durable worker policy, or any compute/data
   contract.

## Required Work

1. Determine whether the `+3` strict-row and `+5` strict-unique-key shortfall is
   primarily:
   - missing local data availability,
   - artifact/provenance reuse from prior AMAT-bridge lineage,
   - missing local-paper label context,
   - or a mix of those.
2. Keep the pass bounded to existing named artifacts, shallow metadata, and
   exact symbol/timestamp checks only.
3. Produce one compact external artifact under
   `D:\thericher-v2\model-artifacts\data-agent`.
4. The artifact must state:
   - whether any immediate operator data request exists,
   - whether no-auth acquisition would help a later objective,
   - exact symbols/timestamps/date ranges if data is missing,
   - whether the branch should remain `hold_no_compute` because the blocker is
     label/provenance rather than raw market data.
5. Update `HANDOFF.md`, `agents/data.md`, `agents/engine-research.md`, and
   `agents/review.md` only if needed.
6. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

## Suggested Commit Message

`Inventory non-AMAT data source context`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data acquisition, Docker/GPU, or broker behavior was touched,
- produced artifacts,
- raw data versus label/provenance blocker,
- any operator data request,
- what was intentionally not built,
- next recommended goal.
