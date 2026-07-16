# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run the first bounded parallel-agent research cadence using the existing
single-shot Engine Research Agent and Data Agent workers.

This advances feature/model research and data collection by keeping the GPU
useful again while a disjoint data lane refreshes local evidence. It also tests
the practical agent workflow the operator expects without creating a durable
multi-agent platform.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, notification
  loop, or auto-commit worker.
- Do not add a new executable agent unless a specific engine loop need is
  proven and the user explicitly approves it.
- Do not add a new research job kind unless an existing test proves it removes
  more complexity than it adds.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not call any context, band, threshold, model, slice, or feature group
  selected, passed, promoted, production ready, or live ready.
- Do not convert a diagnostic feature context into an execution filter, order
  intent, replay rule, feature rule, or model-promotion rule.

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
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep the change tightly scoped.

## Required Work

1. Inventory only the relevant external queue and artifact state:
   - `D:\thericher-v2\model-artifacts\engine-research-agent`
   - `D:\thericher-v2\model-artifacts\data-agent`
   - current raw pre-entry contract-smoke artifact
   - current market-data inventory artifact, if present.
2. Start or reuse a Data Agent single-shot `market_data_inventory` job. Keep it
   metadata-only and bounded; no data acquisition unless a no-auth,
   license-compatible source clearly improves the active loop.
3. Start or reuse an Engine Research Agent single-shot GPU job using an existing
   `thericher-v2-research-job` kind. Prefer a short experiment first, then queue
   a longer candidate only if the short result is sound and the GPU lane is
   available. Keep both queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
4. Use Docker `research` with PyTorch CUDA for GPU work. Artifacts must land
   under `D:\thericher-v2\model-artifacts` on the host and
   `/app/model_artifacts` in Docker.
5. While GPU work runs, use Codex runtime sidecars for disjoint read-only
   checks when useful:
   - Engine Research sidecar: experiment shape and artifact interpretation,
   - Data/Infra sidecar: artifact roots, Docker/GPU/data boundaries,
   - Review/Execution sidecar: sprawl and local-paper-only boundaries.
   These sidecars are not repo-owned workers.
6. If a small code/test fix is needed to make the cadence reliable, keep it
   narrow and prove it with focused tests. Otherwise, make only concise
   stateboard and next-goal updates.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active engine loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact artifact names, symbols, markets,
  date ranges, formats, and blocker reasons in `agents/data.md`,
  `agents/execution.md`, and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused tests,
- Data Agent command(s),
- Engine Research Agent command(s),
- Docker `research` or GPU smoke command(s),
- artifact paths written outside Git.

## Suggested Commit Message

`Run bounded parallel research cadence`

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
