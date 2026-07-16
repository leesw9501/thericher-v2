# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded feature-branch replay threshold derivation guard.

This advances PnL attribution, backtest and walk-forward validation, and
feature/model research by making the existing feature-branch replay path more
useful when model-axis branches produce saturated max probabilities and the
current max-anchored threshold derivation yields zero or too few fills.

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
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, feature set, or model best,
  recommended, passed, promoted, or production ready.

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

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Use recent artifacts as context, not as promotion evidence:
   - `bounded-hidden16-bar-pressure-model-axis-smoke-20260716`
   - `bounded-hidden16-bar-pressure-model-axis-replay-cap2-20260716`
   - `bounded-hidden4-bar-pressure-contrast-smoke-20260716`
   - `bounded-hidden4-bar-pressure-contrast-replay-cap2-20260716`
3. Inspect `derive_feature_branch_replay_threshold_pairs` and add one bounded
   guard or attribution for saturated max-probability outputs. Prefer improving
   the existing helper over adding a new job family.
4. Keep the result descriptive. The guard may improve replay coverage, but it
   must not select a best threshold or promote a model.
5. Add focused tests proving the guard:
   - preserves existing non-saturated behavior,
   - avoids returning fewer pairs solely because max probability rounds to the
     ceiling,
   - remains bounded by `threshold_pair_cap`,
   - keeps replay local-paper only.
6. Run Docker `research` feature-branch replay on at least one existing
   hidden-units artifact if the code change is sound.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
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

Report any focused tests, Docker `research` commands, GPU availability, and
artifact paths used.

## Suggested Commit Message

`Bound feature branch replay threshold derivation`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- derivation guard findings,
- what was intentionally not built,
- next recommended goal.
