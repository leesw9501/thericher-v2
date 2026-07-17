# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first bounded bridge from AMAT recurrence/path evidence into the
existing feature-input stability contract, without creating a new research job
kind or durable agent platform.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by making the latest AMAT evidence consumable by existing
diagnostic/model-input primitives only if enough independent rows can be
reconstructed.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Do not build additional repo-owned executable role workers in this goal unless
  the latest operator message explicitly names the role and behavior to make
  executable.

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

- Feature-input compatibility diagnostic:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-feature-input-compatibility-20260717-r1\compatibility_diagnostic.json`
- Compatibility smoke metrics:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-feature-input-compatibility-20260717-r1\metrics.json`
- AMAT negative-shape recurrence scan:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-shape-recurrence-scan-20260717-r1\metrics.json`
- AMAT negative-path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-path-attribution-20260717-r1\metrics.json`
- Exact parity path attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-path-attribution\metrics.json`
- Data Agent cadence inventory:
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-multiagent-cadence-20260717-r1\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Use temporary Codex sidecars for disjoint checks when useful:
   - Engine Research: inspect whether the bridge can produce enough independent
     diagnostic rows for existing feature-input ablation.
   - Data/Infra: verify needed local rows, artifact roots, queue/lock state,
     and whether Docker/GPU should remain idle until the bridge fits.
   - Review/Execution: verify source-label, broker, credential, and
     durable-agent-platform boundaries.
2. Build the smallest useful bridge as artifact-only work or a focused helper
   if code is needed. It must output a feature-input stability-shaped artifact
   only when the existing evidence can supply the required contract:
   `selected_candidate_entry_rows` or `consumed_slices` plus
   `metrics.added_source_variant_meta`.
3. The bridge must preserve:
   - diagnostic rows as `source: diagnostic_overlay`,
   - original fills as `source: local_paper`,
   - exact symbol/variant/timestamp/offset/probability/threshold context,
   - explicit missing-evidence counts.
4. If the bridge produces at least `8` labeled diagnostic rows, run the existing
   `candidate_feature_input_ablation` primitive against that artifact. Prefer
   Docker `research` only if the input contract is satisfied and GPU work is
   actually reached.
5. If fewer than `8` rows can be reconstructed, do not force a GPU job. Write a
   compact external artifact explaining the row shortfall and the exact replay
   or data evidence needed next.
6. Do not acquire data unless an explicit no-auth, lawful, license-compatible
   source materially improves this bridge. Existing `D:\market_data` should be
   enough for the first pass.
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

`Record AMAT recurrence compatibility`

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
