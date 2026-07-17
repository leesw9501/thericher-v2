# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Engine Research follow-up from the AMAT recurrence scan, while
answering the operator's role-agent expectation without creating platform
sprawl.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by expanding or closing the current AMAT negative-shape evidence
loop with existing workers and artifacts.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- The repo does not yet run many durable autonomous agents in parallel. Codex
  may spawn temporary sidecars during a task, but a new repo-owned worker should
  be added only for a named engine-loop benefit.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not add a new executable role worker in this goal unless the latest
  operator message explicitly names the role and behavior to make executable.
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
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- AMAT negative-shape recurrence scan:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-shape-recurrence-scan-20260717-r1\metrics.json`
- AMAT negative-path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-path-attribution-20260717-r1\metrics.json`
- Exact parity path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-path-attribution\metrics.json`
- Exact parity replay:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1\metrics.json`
- Data Agent cadence inventory:
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-multiagent-cadence-20260717-r1\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Use temporary Codex sidecars for disjoint checks when useful:
   - Engine Research: decide whether the recurrence scan supports one existing
     Docker `research` replay or a smaller artifact-only diagnostic.
   - Data/Infra: verify data/artifact roots, queue/lock state, Docker research
     readiness, and GPU visibility if a Docker job is considered.
   - Review/Execution: verify no broker, credential, source-label, role-agent,
     or diagnostic-to-execution drift.
2. Prefer one existing Engine Research Agent Docker `research` job that expands
   independent closed-segment evidence from existing `D:\market_data` rows, if
   a bounded symbol batch can answer the recurrence question.
3. If the evidence does not support a GPU-backed replay, do not force one.
   Instead, run one small artifact-only compatibility diagnostic and record why
   the AMAT recurrence schema still cannot feed the existing
   `feature_input_ablation` primitive directly.
4. Run Data Agent inventory only if it materially helps the follow-up; otherwise
   reuse the latest inventory and explain why no acquisition is needed.
5. Keep the operator-facing role-agent answer concise:
   - state which repo-owned executable workers exist now,
   - state which roles are only stateboards/sidecars,
   - recommend the first safe additional executable role, if any, without
     building it unless explicitly named by the operator.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- Do not acquire data unless a no-auth, lawful, license-compatible source
  clearly improves the active follow-up.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact artifact names, symbols, markets,
  date ranges, formats, and blocker reasons in `agents/data.md`, the handoff,
  and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused test or artifact-only smoke command,
- any Engine Research Agent or Data Agent command,
- any Docker `research` or GPU command,
- artifact paths written outside Git.

## Suggested Commit Message

`Record bounded multi-agent cadence`

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
