# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded GPU candidate training job.

This advances feature/model research by moving from GPU smoke execution to a
small, repeatable candidate-training job for the selected walk-forward
candidate. The goal is to keep the single GPU useful with bounded training while
preserving replayable artifacts and avoiding broad agent/process sprawl.

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
- Keep local paper fills labeled with `source: local_paper`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add heavy GPU dependencies to the base engine or local dev/test path.
- Run GPU compute/training through the Docker `research` target/profile.
- Do not create a second next-goal document or a large agent framework.
- Do not start an unbounded or overnight training run yet.

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

1. Treat the current `agents/*.md` files as lane stateboards, not autonomous
   workers. Do not create new agent stateboards unless a durable new lane is
   needed.
2. Reuse the lightweight research job runner instead of adding a separate
   orchestration layer.
3. Add a bounded candidate-training job that consumes selected candidate
   metadata and deterministic local/sample bars or an explicit local market-data
   snapshot.
4. Train only a tiny PyTorch model with strict epoch/step limits in Docker
   `research`; this is a candidate-training proof, not a production model.
5. Store generated job, metrics, and model artifacts outside Git under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
6. Keep repo-side state concise: update `agents/engine-research.md` and
   `agents/infra.md` with the queue/result state, but do not generate many
   reports or gates.
7. Add focused tests proving:
   - job artifacts are outside Git,
   - candidate training does not read credentials or call broker/KIS paths,
   - PyTorch remains research-container-only,
   - missing GPU/backend records a non-fatal prepared state,
   - model artifacts are written outside Git.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active validation loop.
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

Report any focused candidate-training command, job-runner command, GPU training
smoke, compute smoke, runtime smoke, candidate artifact command, or Docker
research command used.

## Suggested Commit Message

`Add bounded GPU candidate training`

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
