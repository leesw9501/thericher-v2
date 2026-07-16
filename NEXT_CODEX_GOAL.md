# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Attribute the first runner-queued research replay zero-fill behavior.

This advances feature/model research, backtest validation, and PnL attribution
by explaining the completed Engine Research Agent
`candidate_feature_branch_replay` job on AXP, AZN, and BA before adding another
feature, model, or threshold axis.

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
   If the work stays artifact-only with no code or policy change, record why a
   drift-check was not needed.

## Required Work

1. Inspect these existing external artifacts:
   - `D:\thericher-v2\model-artifacts\engine-research-agent\runs\engine-agent-feature-replay-firsteval-depth-axp-azn-ba-20260717-r2\status.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-firsteval-depth-axp-azn-ba-20260717-r2\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-firsteval-depth-axp-azn-ba-20260717-r2-robustness\metrics.json`
   - any linked probability trace artifacts under the same robustness tree.
2. Attribute why the queued AXP/AZN/BA replay produced zero fills:
   - threshold gaps,
   - observed probability ranges,
   - slice/symbol distribution,
   - missing or delayed sell/buy signal windows,
   - any local-paper evidence shape.
3. Prefer artifact-only work. Add code only if a tiny reusable helper removes
   repeated manual parsing and directly improves the research loop.
4. If writing an attribution artifact, write exactly one compact artifact under
   `D:\thericher-v2\model-artifacts`; do not create repo reports or gates.
5. Keep two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Keep other roles lightweight:
   - Data Agent records data needs only,
   - Infra Agent records Docker/GPU runtime notes,
   - Execution Agent stays broker-disabled,
   - Review Agent checks for sprawl.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless the attribution truly needs a
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

Also report any focused test, artifact-only smoke command, Docker `research`
command, GPU availability, and artifact paths used.

## Suggested Commit Message

`Attribute runner queued zero fill replay`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- runner queue behavior,
- zero-fill attribution behavior,
- what was intentionally not built,
- next goal.
