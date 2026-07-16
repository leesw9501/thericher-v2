# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run the first data-quality-visible bounded GPU validation.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by proving the new local Yahoo `source_slices[].data_quality`
summaries appear in external candidate training/evaluation artifacts before the
next replay evidence is interpreted.

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
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
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
2. Prefer existing `D:\market_data` Yahoo intraday snapshots. Do not acquire
   more data unless it is no-auth, lawful, license-compatible, and directly
   useful for this validation.
3. Run one short Docker `research` candidate training/evaluation smoke on local
   Yahoo slices and confirm the resulting external artifacts include compact
   `source_slices[].data_quality` summaries.
4. If the short smoke is sound and the GPU is available, run one bounded longer
   candidate training/evaluation pass using existing job kinds and PyTorch CUDA
   inside Docker `research`.
5. If evaluation evidence is sound, replay through an existing broker-free
   local-paper path. Do not add a new replay job kind unless a focused bug fix
   requires it.
6. Keep both research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
7. Add or adjust focused tests only if code changes are needed. Otherwise keep
   this task to external artifact execution plus concise stateboard/handoff
   updates.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
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

Report the Docker `research` commands used, whether GPU was available, and the
artifact paths that contain `source_slices[].data_quality`.

## Suggested Commit Message

`Run data-quality-visible GPU validation`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- where `source_slices[].data_quality` was observed,
- what was intentionally not built,
- next recommended goal.
