# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first lightweight Engine Research Agent GPU queue runner.

This advances feature/model research and infra by turning the Engine Research
Agent from a stateboard-only lane into one explicit, bounded worker command that
can pick one queued Docker `research` job, run it with PyTorch CUDA, record the
result outside Git, and leave the next job visible for Codex/operator review.

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
- Keep diagnostic overlay outcomes labeled separately from local-paper fills
  with `source: diagnostic_overlay`.
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not create a broad autonomous multi-agent platform, daemon, Windows
  service, web UI, scheduler, notification system, or report family.
- Do not let any agent commit, push, call brokers, read credentials, or mutate
  another lane's files without Codex integration.
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

3. Ask Claude CLI for a short drift-check before code or architecture edits.
   This goal touches agent orchestration, so get the drift-check before
   implementing.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous policy sources.
2. Add the smallest useful Engine Research Agent runner:
   - explicit CLI command, not a background daemon,
   - one queued job per invocation,
   - clear file/lock behavior so the single GPU is not double-booked,
   - queue and run-state artifacts outside Git under
     `D:\thericher-v2\model-artifacts`,
   - Docker `research` execution only for GPU jobs,
   - no broker/network/credential behavior.
3. Seed or document one bounded GPU queue item that uses existing local data and
   current research job kinds. Prefer a short PyTorch CUDA smoke or a bounded
   `candidate_feature_branch`/replay job that is useful for the active research
   loop.
4. Run the agent runner once in a bounded smoke:
   - it should claim at most one job,
   - execute or cleanly prepare/skip with a reason,
   - write a compact external run artifact,
   - preserve local-paper-only fill evidence if replay is involved.
5. Keep other roles lightweight:
   - Data Agent records data needs only,
   - Infra Agent records Docker/GPU runtime notes,
   - Execution Agent stays broker-disabled,
   - Review Agent checks for sprawl.
6. Add focused tests proving:
   - queue claim is deterministic and does not double-claim,
   - queue/run artifacts are outside Git or mocked in tests,
   - no credentials, KIS, broker submit, or `.env` reads are needed,
   - PyTorch remains absent from local/base dependencies.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless the selected smoke job needs a
  no-auth, license-compatible missing slice.
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

Also report any focused test, Docker `research` command, GPU availability, and
artifact paths used.

## Suggested Commit Message

`Add lightweight engine research agent runner`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- validation behavior,
- what was intentionally not built,
- next goal.
