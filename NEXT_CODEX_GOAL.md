# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first research-profile GPU runtime smoke for the selected bounded
candidate.

This advances feature/model research and reproducible GPU experimentation by
checking the GPU path in the research lane only, while keeping the base engine
free of heavy GPU dependencies.

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

1. Inspect the selected candidate artifact under
   `D:\thericher-v2\model-artifacts\experiments`.
2. Inspect the Docker research service and current dependency layout.
3. Add a minimal research-profile GPU runtime smoke that can:
   - detect the GPU,
   - write a concise JSON result outside Git,
   - avoid any broker, credential, dashboard, or KIS surface,
   - avoid adding heavy GPU dependencies to base engine tests.
4. Prefer an existing runtime capability such as `nvidia-smi`. Add PyTorch,
   CUDA, or other heavy ML dependencies only inside the research profile and
   only if doing so is bounded and clearly useful for the smoke.
5. If a real GPU compute smoke is not available without dependency creep, record
   a `prepared_not_trained` or `runtime_ready_only` artifact with the reason.
6. Update `agents/engine-research.md` and `agents/infra.md` so the short
   experiment queue and longer candidate queue remain visible.
7. Add focused tests proving:
   - smoke artifact paths are outside Git,
   - no broker/network/credential access is needed,
   - base engine tests do not require GPU packages,
   - missing GPU/runtime support records a non-fatal prepared state.
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

Report any focused GPU runtime smoke, candidate artifact command, or Docker
research command used.

## Suggested Commit Message

`Add research GPU runtime smoke`

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
