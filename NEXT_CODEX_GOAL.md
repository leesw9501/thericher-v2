# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Queue and run the first research-useful Engine Research Agent job beyond GPU
smoke.

This advances feature/model research and infra by making the new single-shot
Engine Research Agent runner useful for existing bounded Docker `research` job
kinds, not only for a tiny CUDA smoke.

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
- Do not turn the runner into a daemon, scheduler, Windows service, dashboard,
  notification system, broad autonomous multi-agent platform, or auto-commit
  path.
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
   This goal touches agent orchestration and research-job queue semantics, so
   get the drift-check before implementing.

## Required Work

1. Inspect the external runner state under
   `D:\thericher-v2\model-artifacts\engine-research-agent`. Keep the first
   failed smoke as diagnostic history; do not silently delete run-state.
2. Add only the smallest enqueue path needed for existing
   `thericher-v2-research-job` kinds:
   - explicit CLI command, not a background loop,
   - one queued job per enqueue command,
   - strict job id and argument validation,
   - reject `--artifact-root` in queued args because the runner owns
     `/app/model_artifacts`,
   - queue artifacts outside Git only,
   - no stateboard-as-input behavior.
3. Queue one bounded research-useful job through the runner. Prefer a current
   `candidate_feature_branch` or `candidate_feature_branch_replay` job that
   advances the entry-adverse/depth research loop using existing
   `D:\market_data` and existing external model artifacts.
4. Run the agent runner once:
   - it should claim at most one job,
   - execute or cleanly prepare/skip with a reason,
   - write compact external run-state,
   - if replay is involved, preserve local-paper-only fill evidence.
5. Keep two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Keep other roles lightweight:
   - Data Agent records data needs only,
   - Infra Agent records Docker/GPU runtime notes,
   - Execution Agent stays broker-disabled,
   - Review Agent checks for sprawl.
7. Add focused tests proving:
   - enqueue validation is deterministic and external-only,
   - queued args cannot override artifact root or request obvious
     credential/broker/KIS behavior,
   - runner still claims at most one job,
   - no `.env`, credential, broker, or network access is needed,
   - PyTorch remains absent from local/base dependencies.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless the queued research job needs a
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

`Queue first research-useful engine agent job`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- runner queue behavior,
- validation behavior,
- what was intentionally not built,
- next goal.
