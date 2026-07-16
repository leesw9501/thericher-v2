# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run the first longer Engine Research Agent GPU/depth job through the
single-shot runner, with Data Agent as a companion inventory lane.

This advances feature/model research, backtest and walk-forward validation, and
data collection by putting the GPU research lane back to work while keeping the
new Data Agent lane useful and separate.

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
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Keep Data Agent non-GPU and non-Docker in this slice.
- Do not make Execution, Infra, or Review executable workers in this slice.
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

1. Queue and run one Data Agent inventory refresh against existing
   `D:\market_data` before the Engine Research Agent job.
2. Select one bounded longer Engine Research Agent job from the existing closed
   research-job kind set. Prefer a GPU/depth or training-oriented job over a
   replay-only smoke, using existing `D:\market_data` slices and existing
   external artifacts.
3. Queue the selected job through `thericher-v2-engine-research-agent
   enqueue-research-job`, then execute exactly one `run-once`.
4. Keep the job bounded:
   - use existing source/evaluation slice caps,
   - use explicit max epochs/steps/bars,
   - write artifacts only under `D:\thericher-v2\model-artifacts`,
   - do not mutate Data Agent queue/artifacts.
5. If the Engine Research Agent job completes, inspect the compact metrics and
   record:
   - Docker `research` command,
   - GPU availability,
   - produced artifacts,
   - local-paper source verification if replay/fills are present,
   - whether the job adds useful next evidence for short breadth or longer
     depth queues.
6. If the Engine Research Agent job cannot run within boundaries, record the
   blocker and do not substitute broker, credential, network, or dashboard work.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Also report any worker commands, focused tests, Docker `research` command
observed through the Engine Research Agent status, GPU availability, and
artifact paths used.

## Suggested Commit Message

`Run first runner queued depth job`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- Data Agent queue behavior,
- Engine Research Agent queue behavior,
- produced artifacts,
- local-paper source evidence if applicable,
- what was intentionally not built,
- next goal.
