# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Inspect AMAT/AEM trade paths from the explicit-slice depth target before
spending more GPU time.

This advances PnL attribution, feature/model research, and backtest and
walk-forward validation by identifying whether a smaller replay-shape
diagnostic should focus on entry frequency, exit timing, path quality, or a
cap-limited combination.

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
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Do not run new GPU training before the AMAT/AEM trade-path diagnosis is
  complete.
- Do not queue another Engine Research Agent job unless the current artifacts
  are unreadable or incomplete.
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

3. Ask Claude CLI for a short drift-check before any code or architecture
   edits. If the slice stays artifact-only plus stateboard updates, record why a
   drift-check was not needed.

## Required Work

1. Consume the completed attribution artifact:
   `D:\thericher-v2\model-artifacts\candidate-depth-target-attribution\engine-agent-depth-target-explicit-slices-20260717-r1-attribution\metrics.json`.
2. Consume existing event and probability-trace artifacts for AMAT and AEM
   holdout variants from
   `engine-agent-depth-target-explicit-slices-20260717-r1`.
3. Use selected local Yahoo rows from `D:\market_data` only if needed to
   explain entry/exit path context.
4. Reconstruct compact trade-path evidence for:
   - AMAT worst-loss variants,
   - AEM high-fill variants,
   - any AMAT/AEM higher-threshold variants that still lose with fewer fills.
5. Explain whether AMAT/AEM losses appear driven by entry frequency, entry
   timing, exit latency, adverse path movement, or open-position exposure.
6. Produce one compact external diagnostic artifact under
   `D:\thericher-v2\model-artifacts`.
7. Keep all fill evidence labeled and checked as `source: local_paper`.
8. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research sidecar for trade-path interpretation,
   - Execution sidecar for local-paper-only evidence,
   - Review sidecar for v1-sprawl and durable-worker drift.
   These sidecars do not create durable repo workers and do not override the
   main Codex integrator.
9. If artifacts are insufficient, record exact missing paths and stop; do not
   substitute broker, credential, network, dashboard, or scheduler work.
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

Also report any focused artifact-only command used, artifact paths, and
local-paper source evidence.

## Suggested Commit Message

`Attribute AMAT AEM depth trade paths`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- produced diagnostic artifacts,
- local-paper source evidence,
- sub-agents used and what they checked,
- what was intentionally not built,
- next goal.
