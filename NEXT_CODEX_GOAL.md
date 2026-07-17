# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Inspect the duplicate-aware AMAT bridge ablation output and decide one bounded
independent-evidence follow-up.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by checking whether the AMAT recurrence/path bridge produced
useful model-input evidence, or whether it mostly duplicated one market moment.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary sidecars may run in parallel for scoped review, but do not build a
  durable multi-agent platform, scheduler, daemon, coordinator, notification
  loop, or auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not add a new research job kind.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Avoid promotional model-quality language except when quoting unavoidable
  existing artifact field names.
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

3. Use temporary Codex sidecars for disjoint checks when useful:
   - Engine Research: inspect duplicate-aware bridge ablation metrics and the
     smallest useful follow-up.
   - Data/Infra: verify local data, artifact roots, queue/lock state, and
     Docker readiness after restarts.
   - Review/Execution: verify source labels, broker boundaries, and
     multi-agent drift.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- AMAT recurrence/path bridge:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-amat-recurrence-path-bridge-20260717-r1\metrics.json`
- AMAT bridge ablation:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-path-bridge-ablation-20260717-r1\metrics.json`
- AMAT bridge ablation model artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-path-bridge-ablation-20260717-r1\feature_input_ablation.pt`
- Engine Research Agent run status:
  `D:\thericher-v2\model-artifacts\engine-research-agent\runs\engine-agent-amat-recurrence-path-bridge-ablation-20260717-r1\status.json`
- Exact parity path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-path-attribution\metrics.json`
- Wider holdout depth behavior attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-wider-holdout-depth-attribution-20260717\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Inspect the bridge and ablation artifacts. Summarize:
   - row count,
   - complete unique signal count,
   - row-to-unique-signal ratio,
   - label balance,
   - per-slice concentration,
   - group losses or descriptive metrics already present.
2. Decide whether the current evidence is too duplicate-heavy for more model
   work. Treat `31` rows collapsing to `12` complete unique signals, and the
   repeated AMAT negative market moment, as a serious caveat. Also note that
   AMAT accounts for `20` of `31` bridge rows.
3. If the evidence is too duplicate-heavy, write a compact external
   artifact-only decision under `D:\thericher-v2\model-artifacts` explaining the
   exact independent rows or replay evidence needed next. Do not run Docker/GPU.
4. If a follow-up is justified from existing evidence, run at most one existing
   Engine Research Agent job. Prefer an existing replay or ablation primitive;
   do not add a job kind, worker, scheduler, or broad sweep.
5. Use existing `D:\market_data` first. Acquire additional data only when it is
   no-auth, lawful, license-compatible, and directly needed for the active
   follow-up. Stop acquisition attempts when sources need credentials/payment,
   licensing is unclear, two automated attempts fail for the same source, or the
   new data no longer improves this goal.
6. Preserve source labels:
   - original fills remain `source: local_paper`,
   - diagnostic rows remain `source: diagnostic_overlay`.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Record AMAT bridge ablation`

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
