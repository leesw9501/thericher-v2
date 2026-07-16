# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Attribute the AMAT/AMZN fill-bearing paths from the bounded replay contrast
before any longer GPU training block.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by checking whether the existing fill-bearing evidence is
path-quality useful or only threshold-hit evidence.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, notification
  loop, or auto-commit worker.
- Do not add a new executable agent unless a specific engine loop need is
  proven and the user explicitly approves it.
- Do not add a new research job kind.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not call any context, band, threshold, model, slice, or feature group
  selected, passed, promoted, production ready, or live ready.
- Do not convert a diagnostic context into an execution filter, order intent,
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

- Fill-bearing contrast artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-zero-vs-fill-bearing-contrast-20260717-r1\metrics.json`
- Fill-bearing replay artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717\metrics.json`
- Fill-bearing robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717-robustness\metrics.json`
- Zero-buy opportunity-gap artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-opportunity-gap-20260717-r1\metrics.json`

## Required Work

1. Consume existing AMAT and AMZN event artifacts, probability traces, and
   local `snapshot=2026-06-18` bars only. Do not rerun replay unless existing
   event evidence is missing for nonzero-fill variants.
2. Produce one compact artifact-only path-quality attribution outside Git.
   Prefer existing pure helpers such as trade-path attribution before writing
   one-off parsing logic.
3. The attribution must report counts, not decisions:
   - fill-bearing variants and local-paper fill counts,
   - closed/open trade paths,
   - fee-aware and gross deltas,
   - max adverse and favorable movement,
   - entry probability margins versus buy thresholds,
   - sell-threshold timing after entry,
   - local-paper source verification,
   - diagnostic-overlay source separation,
   - missing evidence counts.
4. Compare AMAT and AMZN path evidence to the zero-buy contrast only as counts
   and descriptive context. Do not introduce a new threshold, feature rule, or
   replay behavior.
5. Do not queue longer candidate training in this task. The output should say
   which evidence is still missing before depth training.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless a no-auth, lawful,
  license-compatible source clearly improves the active attribution.
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
- any Engine Research Agent command,
- Docker `research` or GPU command if used,
- artifact paths written outside Git.

## Suggested Commit Message

`Attribute fill-bearing replay paths`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used and where artifacts were written,
- produced diagnostic or research artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- sub-agents used and what they checked,
- what was intentionally not built,
- next goal.
