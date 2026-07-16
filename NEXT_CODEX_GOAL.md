# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add a bounded attribution-informed threshold band rerun.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by using the zero-fill attribution artifact to try one small
exploratory threshold band inside the observed probability range. The output is
descriptive replay evidence for local paper only, not a production winner,
promotion rule, scheduler framework, or dashboard.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Keep simulated fills labeled with `source: local_paper`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, or model best, recommended, passed,
  promoted, or production ready.

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

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Inventory only the current useful external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-threshold-attribution\bounded-candidate-threshold-attribution-mini-smoke\metrics.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-threshold-attribution-mini-smoke.json`
   - the referenced threshold rerun, robustness, source calibration, and
     probability trace artifacts.
3. Reuse existing local Yahoo subsets under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Avoid expensive full recursive scans and do not acquire new data unless the
   active replay cannot proceed without it.
4. Add a small helper or research job path that:
   - consumes the threshold attribution artifact and its source rerun lineage,
   - derives a capped exploratory threshold band from observed probability
     range and source calibration evidence,
   - keeps the derivation deterministic and descriptive, with no ranking,
     optimization, or promotion semantics,
   - replays the band only through the existing broker-free local-paper path,
   - prefers existing probability traces and local Yahoo snapshots over model
     inference,
   - records fills, PnL, drawdown, opportunity counts, and local-paper
     verification,
   - records the output as research-only descriptive replay evidence.
5. Keep the two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Add focused tests proving:
   - attribution and rerun lineage artifacts are read from outside Git,
   - the derived band is deterministic, bounded, and non-promotional,
   - replay uses local paper only and preserves `source: local_paper`,
   - generated artifacts remain outside Git or mocked in tests,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing attribution/rerun/trace artifacts are non-fatal prepared states.
7. Run a CPU/injected smoke first. If Docker `research` dispatch is added, run
   a bounded Docker smoke using the existing external artifacts.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from existing `D:\market_data` and external model artifacts.
- Prefer existing Yahoo intraday snapshots and existing probability traces.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active replay target.
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

Report any focused attribution, local-paper replay, Docker research, or GPU
command used.

## Suggested Commit Message

`Add attribution-informed threshold band rerun`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- what was intentionally not built,
- next recommended goal.
