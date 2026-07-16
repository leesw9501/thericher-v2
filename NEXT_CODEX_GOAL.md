# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Create the first non-GPU Data Agent single-shot worker so multi-agent work
becomes real beyond markdown stateboards.

This advances data collection and feature/model research by giving Data Agent a
bounded executable lane that can run independently from the Engine Research
Agent GPU/Docker research queue.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not acquire market data in this slice unless the active worker smoke
  cannot run without a tiny no-auth, lawful, license-compatible fixture outside
  Git.
- Do not store generated artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Keep PyTorch CUDA confined to the Docker `research` target/profile; the Data
  Agent worker should not require PyTorch, GPU, or Docker.
- Do not turn role agents into a daemon, scheduler, Windows service, dashboard,
  notification system, broad autonomous multi-agent platform, or auto-commit
  path.
- Do not make Execution Agent executable in this slice.
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
   - `src/thericher_v2/research/engine_research_agent.py`
   - `tests/test_engine_research_agent.py`

3. Ask Claude CLI for a short drift-check before adding the new worker/CLI.
   Judge Claude's feedback against `HANDOFF.md`, `ARCHITECTURE.md`,
   `AGENTS.md`, and `DECISIONS.md`.

## Required Work

1. Inspect the existing Engine Research Agent runner pattern and reuse only the
   small parts that fit a non-GPU data lane: external queue, single-job claim,
   run-state artifact, conservative env/path validation, and `run-once`.
2. Add a narrow Data Agent worker, likely `thericher-v2-data-agent`, with:
   - one enqueue command for a closed set of data job kinds,
   - one `run-once` command that claims at most one queued job and exits,
   - external queue/run artifacts under
     `D:\thericher-v2\model-artifacts\data-agent`,
   - no GPU lock, no Docker requirement, no broker authority, no credential
     reads, no network calls, and no shell execution.
3. Implement the first job kind as a bounded market-data inventory or quality
   summary over existing `D:\market_data` content:
   - avoid expensive full recursive scans,
   - prefer configured or explicit roots,
   - record symbol/snapshot/file counts and obvious availability warnings only,
   - write one compact artifact outside Git.
4. Keep Engine Research Agent as the GPU/research worker. Data Agent must not
   mutate Engine Research Agent queue files, model artifacts, or research job
   state.
5. Add focused tests proving:
   - Data Agent artifacts stay outside the Git workspace,
   - no broker/network/credential access is needed,
   - queue claim/run-once is deterministic and single-shot,
   - suspicious KIS/broker/credential/env/artifact-root arguments are rejected,
   - Engine Research Agent and Data Agent use disjoint queue/artifact roots.
6. Run one bounded Data Agent smoke on existing `D:\market_data` if available.
   If useful data is absent, produce a prepared/blocked artifact outside Git
   and record exact operator data needs.
7. Update `HANDOFF.md`, `agents/data.md`, `agents/engine-research.md`,
   `agents/infra.md`, `agents/review.md`, and `RUNBOOK.md` with concise worker
   usage and boundaries.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should inventory existing data, not expand the dataset.
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

Also report any focused tests, Data Agent smoke command, artifact path, and
whether Docker/GPU were intentionally unused.

## Suggested Commit Message

`Add single shot Data Agent worker`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- Data Agent queue behavior,
- Engine Research Agent separation,
- what was intentionally not built,
- next goal.
