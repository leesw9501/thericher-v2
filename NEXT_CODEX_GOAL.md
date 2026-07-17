# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Select one bounded fresh Engine Research evidence question for the next
GPU/replay decision.

This advances feature/model research and backtest/walk-forward validation by
choosing the next concrete evidence question before spending GPU or replay time.
The outcome should either justify one small future Engine Research job or keep
compute explicitly held.

Codex should auto-select this lane by rotation. Do not stop for an ordinary
operator lane choice; stop only for a true approval or ambiguity listed below.

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
  data acquisition, or broad recursive `D:\market_data` scans during the
  question-selection step.
- Do not turn held evidence into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` and Docker `/app/model_artifacts`.

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
   - `D:\thericher-v2\model-artifacts\infra\artifact-mount-sanity-20260717-r1\metrics.json`
   - `D:\thericher-v2\model-artifacts\review-simplification\non-amat-held-branch-retirement-20260717-r1\metrics.json`

3. Ask Claude CLI for a short drift-check before architecture-changing edits,
   promotion-rule changes, agent-governance changes, new job/helper contracts,
   replay/local-paper behavior changes, durable worker policy changes, or
   compute/data contract changes. A bounded artifact-only question-selection
   pass does not require Claude unless it proposes such a change.

## Required Work

1. Inspect current Engine Research, Data, Execution, Infra, and Review
   stateboards for held/reusable evidence.
2. Inspect only named recent artifacts needed to avoid duplicate branch reuse.
   Prefer exact known artifacts over directory-wide scans.
3. Select one fresh evidence question that is independent enough to justify a
   future small GPU/replay job, or record `hold_no_compute` with the reason.
4. Keep the result descriptive. Do not choose a winner, promotion, threshold,
   execution rule, or model gate.
5. Write one compact external planning artifact under
   `D:\thericher-v2\model-artifacts\engine-research-planning`.
6. Update `HANDOFF.md`, `agents/engine-research.md`, and other stateboards only
   if needed.
7. Refresh `NEXT_CODEX_GOAL.md` before ending with one single next objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Report any focused artifact-only smoke command used.

## Suggested Commit Message

`Select next engine research evidence question`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- sidecars or executable workers used,
- whether data acquisition, Docker/GPU training, replay, or broker behavior was
  touched,
- produced artifacts,
- selected evidence question or hold reason,
- what was intentionally not built,
- next recommended goal.
