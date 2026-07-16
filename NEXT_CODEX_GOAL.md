# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run the first two-worker cadence with the Engine Research Agent and Data Agent
single-shot workers.

This advances data collection and feature/model research by proving the two
executable lanes can make progress through disjoint queues and artifact roots
without adding an orchestrator.

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

1. Inspect the current external worker roots:
   - `D:\thericher-v2\model-artifacts\engine-research-agent`
   - `D:\thericher-v2\model-artifacts\data-agent`
2. Queue and run one Data Agent inventory refresh using existing
   `D:\market_data` only. Use a unique job id and confirm it claims one job,
   writes one inventory artifact, and exits.
3. Queue and run one Engine Research Agent bounded research job through the
   existing runner. Prefer a research-useful closed job kind over a smoke. A
   good starting point is a small `candidate_feature_branch_replay` using the
   existing first-evaluation depth feature-branch artifact and three existing
   `snapshot=2026-06-18` symbols. Use `gpu_training_smoke` only if the useful
   replay cannot be queued within the boundaries.
4. Confirm the two workers stay disjoint:
   - separate queue directories,
   - separate run directories,
   - separate artifact subtrees,
   - Engine Research Agent may use Docker `research`/GPU,
   - Data Agent must not use Docker/GPU/network/broker/credentials.
5. Record only concise coordination evidence in existing stateboards and
   `HANDOFF.md`. Do not create a new coordination report family.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Run first two worker cadence`

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
- lane separation evidence,
- what was intentionally not built,
- next goal.
