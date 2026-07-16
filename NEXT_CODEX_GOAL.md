# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded multi-agent research cadence using the existing executable
workers and temporary Codex sidecars.

This advances feature/model research, data collection, backtest validation, and
PnL attribution by turning the latest AMAT negative-path evidence into one
focused follow-up while making the current role-agent reality explicit.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are currently stateboards plus temporary Codex
  sidecar roles, not repo-owned executable workers.
- Do not build a durable agent platform just to satisfy the label "agent".
  Create another executable role worker only when it improves a named engine
  loop and the operator explicitly approves that worker.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not add a new executable agent unless a specific engine-loop need is
  proven and the operator explicitly approves it.
- Do not add a new research job kind.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not label any context, band, threshold, model, slice, or feature group as
  selected, passed, promoted, winner, best, production ready, or live ready.
- Do not convert diagnostic context into an execution filter, order intent,
  replay rule, feature rule, or model-promotion rule.

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

3. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep the change tightly scoped.

## Current Evidence To Consume

- AMAT negative-path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-path-attribution-20260717-r1\metrics.json`
- Exact parity path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-path-attribution\metrics.json`
- Exact parity replay:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1\metrics.json`
- Exact parity robustness/event artifacts:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-robustness\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Use temporary Codex sidecars for distinct lane checks:
   - Engine Research: propose one bounded follow-up from the AMAT
     negative-path evidence.
   - Data/Infra: verify local data roots, artifact roots, Docker/GPU readiness,
     and queue/lock state.
   - Review/Execution: verify no broker, credential, source-label, or
     agent-platform drift.
2. Run the Data Agent single-shot inventory only if it materially helps this
   cadence; otherwise state why existing data evidence is sufficient.
3. Keep the GPU useful with at most one bounded Engine Research Agent Docker
   `research` job if the evidence supports a clear question. Prefer existing
   job kinds and existing data/artifacts.
4. If the AMAT negative-path feature context can be evaluated through an
   existing research primitive, use that. If not, run a small existing replay or
   artifact-only diagnostic and record the exact compatibility gap.
5. Keep a concise capability note in `agents/README.md` or `HANDOFF.md` if the
   current executable-worker gap needs clarification. Do not add a new worker
   in this goal unless the operator explicitly confirms which role should become
   executable.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless a no-auth, lawful,
  license-compatible source clearly improves the active cadence.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact artifact names, symbols, markets,
  date ranges, formats, and blocker reasons in `agents/data.md`,
  `agents/execution.md`, and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused tests,
- any artifact-only smoke command,
- any Engine Research Agent or Data Agent command,
- any Docker `research` or GPU command,
- artifact paths written outside Git.

## Suggested Commit Message

`Run bounded multi-agent research cadence`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used and where artifacts were written,
- produced diagnostic or research artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
