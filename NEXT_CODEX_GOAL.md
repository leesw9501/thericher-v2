# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Close the AMAT/AMZN/BA `240`-bar threshold-pair parity gap before any longer
GPU training block.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by checking the same AMAT/AMZN/BA `240`-bar path behavior with
the same three threshold pairs used by the `120`-bar cadence evidence.

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

- Same-window AMAT/AMZN consolidation:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\same-window-amat-amzn-path-quality-consolidation-20260717-r1\metrics.json`
- Current AMAT/AMZN `120`-bar path-quality artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-cadence-depth-amat-amzn-path-quality-20260717-r1\metrics.json`
- Existing AMAT/AMZN/BA `120`-bar replay artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717\metrics.json`
- Wider-holdout depth behavior attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-wider-holdout-depth-attribution-20260717\metrics.json`
- Depth feature-branch artifact referenced by the wider-holdout replay:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-depth-validation-20260716\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. First check whether an exact AMAT/AMZN/BA `240`-bar replay already exists
   with threshold pairs:
   - `0.594/0.476`
   - `0.595/0.476`
   - `0.596/0.476`
2. If exact evidence already exists, consume it and produce one compact
   artifact-only attribution outside Git.
3. If exact evidence is missing, queue at most one existing
   `candidate_feature_branch_replay` job through the Engine Research Agent
   runner with:
   - `max-bars 240`
   - symbols AMAT, AMZN, and BA from `snapshot=2026-06-18`
   - threshold pairs `0.594/0.476`, `0.595/0.476`, and `0.596/0.476`
   - the existing depth feature-branch artifact above
4. After the replay, attribute the result using existing event, trace, and
   local-bar evidence. Do not add a new job kind.
5. Report counts, not decisions:
   - AMAT/AMZN/BA fill-bearing variants and local-paper fill counts,
   - closed/open trade paths,
   - fee-aware and gross deltas,
   - negative versus non-negative fee-aware path counts,
   - entry probability margins,
   - sell-threshold timing after entry,
   - max adverse and favorable movement,
   - local-paper source verification,
   - diagnostic-overlay source separation,
   - missing evidence counts,
   - comparison against the prior `120`-bar and reused `240`-bar evidence.
6. Do not queue longer candidate training in this task. End with the evidence
   still missing, if any, before another depth-training block.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless a no-auth, lawful,
  license-compatible source clearly improves the active parity check.
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

`Check AMAT AMZN threshold parity`

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
