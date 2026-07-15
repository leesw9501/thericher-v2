# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Choose and add the first research-only GPU compute backend, then run a tiny
bounded GPU training smoke for the selected candidate.

This advances feature/model research and reproducible GPU experimentation by
moving from runtime/compute readiness into the smallest useful model-training
loop, while keeping the base engine free of heavy GPU dependencies.

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
- Do not add heavy GPU dependencies to the base engine test path.
- Run GPU compute/training through the Docker `research` target/profile.
- If adding PyTorch/CUDA or another heavy framework requires a package choice,
  check current official guidance first and keep it research-only.

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

1. Confirm or ask for the compute backend choice before adding any heavy
   framework. Prefer PyTorch CUDA in the Docker `research` target unless the
   operator chooses otherwise.
2. Keep the base `engine` and `web` images free of GPU/ML framework
   dependencies.
3. Update the Docker `research` target/profile so it can run the selected
   backend and still writes model artifacts only to `/app/model_artifacts`.
4. Add a tiny bounded training smoke that:
   - consumes the selected walk-forward candidate metadata,
   - uses deterministic local/sample or explicit local market data only,
   - runs a very small model/tensor training step on GPU if available,
   - writes a concise result outside Git,
   - records `prepared_not_trained` with the reason if the backend or GPU is not
     available.
5. Do not start long training yet. This goal proves the research training path
   only.
6. Update `agents/engine-research.md` and `agents/infra.md` so the short
   experiment queue and longer candidate queue remain visible.
7. Add focused tests proving:
   - training-smoke artifact paths are outside Git,
   - no broker/network/credential access is needed,
   - base engine tests do not require GPU packages,
   - missing GPU/backend records a non-fatal prepared state.
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

Report any focused GPU training smoke, compute smoke, runtime smoke, candidate
artifact command, or Docker research command used.

## Suggested Commit Message

`Add research GPU training smoke`

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
