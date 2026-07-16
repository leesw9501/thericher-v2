# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Docker `research` feature-input ablation using the completed
cross-slice stability evidence.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by checking whether a very small feature branch can separate
early adverse/no-lift candidate entries without changing local-paper replay.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not acquire market data in this slice unless a tiny no-auth,
  lawful, license-compatible external fixture is absolutely required.
- Do not store generated artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root mounted as
  `/app/model_artifacts` in Docker.
- Use Docker `research` with PyTorch CUDA for any GPU/model run.
- Do not add PyTorch to the base/local runtime.
- Do not run a broad hyperparameter sweep.
- Do not mutate existing local-paper event artifacts or replay outputs.
- Keep original fills labeled and checked as `source: local_paper`.
- Label any diagnostic rows or outcomes as `source: diagnostic_overlay`; do not
  count them as local-paper fills.
- Do not make Execution, Infra, or Review durable executable workers in this
  slice.
- Do not add a daemon, scheduler, Windows service, dashboard, notification
  system, broad autonomous multi-agent platform, coordinator, or auto-commit
  path.
- Do not call any threshold, candidate, feature set, preprocessing branch, or
  model best, recommended, passed, promoted, or production ready.

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

3. Ask Claude CLI for a short drift-check before code, architecture, or policy
   edits. Judge the result against `HANDOFF.md`, `ARCHITECTURE.md`, and
   `DECISIONS.md`.

## Required Work

1. Consume the completed cross-slice stability artifact:
   `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`.
2. Keep the ablation narrow and explicit. Compare at most three input groups:
   - existing baseline feature shape,
   - raw pre-entry features only,
   - raw pre-entry features plus probability-derived meta features.
3. Treat probability-derived fields separately from raw market features in the
   artifact output so the result is interpretable.
4. Use existing explicit-slice data and the existing
   `snapshot=2026-06-18` Yahoo rows only unless a blocker is recorded.
5. Run a CPU smoke or deterministic dry-run first if the code path changes.
6. If the smoke is sound, run one bounded Docker `research` PyTorch CUDA
   experiment with tight caps. Write all artifacts outside Git.
7. Preserve local-paper replay behavior. Any replay used for comparison must go
   through the existing broker-free local-paper simulator and preserve
   `source: local_paper`.
8. Add or update focused tests proving:
   - no broker, KIS, network, or credential access is needed,
   - model/GPU artifacts resolve outside the Git workspace,
   - probability-derived and raw feature groups are distinguishable in the
     ablation output,
   - local-paper fill source evidence remains replayable and separate from
     diagnostics.
9. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research sidecar for ablation interpretation,
   - Infra sidecar for Docker/artifact mount assumptions,
   - Execution sidecar for source separation,
   - Review sidecar for sprawl and promotion-language checks.
10. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing data, not expand the dataset.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active validation loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact symbols, markets, date ranges,
  formats, and blocker reasons in `agents/data.md` and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report any focused CPU smoke, Docker `research`, or GPU command used,
artifact paths, local-paper source evidence, and diagnostic-overlay evidence.

## Suggested Commit Message

`Add bounded feature input ablation`

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
