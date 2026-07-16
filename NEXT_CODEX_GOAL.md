# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded feature/model branch target after threshold loop closure.

This advances feature/model research and backtest validation by moving away
from threshold-only reruns. The current candidate can generate local-paper
fills again under an inside-range band, but the evidence is mixed and the
probability distribution remains compressed. The next target should test
whether a small feature/model branch improves probability separation before
another replay sweep.

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
- Keep simulated fills labeled with `source: local_paper` if any replay is
  reused.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, or model best, recommended, passed,
  promoted, or production ready.
- Do not add another threshold-only rerun unless the new feature/model branch
  changes probability-distribution evidence first.

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
   - `D:\thericher-v2\model-artifacts\candidate-threshold-band-rerun\bounded-candidate-threshold-band-rerun-mini-smoke\metrics.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-threshold-band-rerun-mini-smoke.json`
   - the referenced attribution, threshold rerun, calibration, robustness,
     probability trace, and local Yahoo snapshot lineage.
3. Reuse existing local Yahoo subsets under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Avoid expensive full recursive scans and do not acquire new data unless the
   active feature/model branch cannot proceed without it.
4. Add one small feature/model branch target that:
   - consumes the band rerun evidence as context, not as a gate,
   - records that the threshold-only loop is closed for the current candidate
     until a feature/model branch changes probability evidence,
   - introduces the smallest useful feature or candidate-family variation that
     can be trained/evaluated under existing caps,
   - writes all generated artifacts outside Git,
   - records probability distribution and evaluation evidence descriptively,
   - does not select a production winner, promotion threshold, or pass/fail
     result.
5. Keep the two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Add focused tests proving:
   - the feature/model branch consumes external context without reading
     credentials or network resources,
   - PyTorch remains research-container-only and lazy,
   - generated artifacts remain outside Git or mocked in tests,
   - any reused local-paper replay keeps `source: local_paper`,
   - missing context artifacts are non-fatal prepared states,
   - the output stays descriptive and non-promotional.
7. Run a CPU/injected smoke first. If Docker `research` dispatch is added, run
   a bounded Docker smoke using existing local data and external artifacts.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from existing `D:\market_data` and external model artifacts.
- Prefer existing Yahoo intraday snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active feature/model branch.
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

Report any focused feature/model, local-paper replay, Docker research, or GPU
command used.

## Suggested Commit Message

`Add bounded feature model branch target`

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
