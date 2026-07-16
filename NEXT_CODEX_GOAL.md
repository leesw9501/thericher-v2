# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded source-vs-holdout probability alignment attribution for the
standardized feature branch.

This advances backtest and walk-forward validation plus PnL attribution by
explaining why `feature_standardization` reduced source-side saturation but the
cap-2 holdout replay still produced zero buy opportunities and zero local-paper
fills.

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
- Do not start a broad scheduler, agent framework, promotion gate, dashboard
  expansion, threshold optimizer, preprocessing search, or model search.
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

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Use recent artifacts as context, not as promotion evidence:
   - `bounded-standardized-bar-pressure-feature-normalization-smoke-20260716`
   - `bounded-standardized-bar-pressure-feature-normalization-replay-cap2-20260716`
   - `bounded-standardized-opportunity-attribution-20260716`
   - `bounded-weightdecay-opportunity-attribution-20260716`
3. Inspect the existing probability trace, threshold robustness, and
   opportunity attribution helpers before adding code.
4. Add one small artifact-only alignment helper or entrypoint that consumes
   existing source and holdout probability evidence where possible.
5. Record compact source-vs-holdout evidence outside Git:
   - source probability min/max/mean/range,
   - holdout per-slice probability min/max/mean/range or available trace
     equivalent,
   - buy/sell threshold opportunity counts,
   - zero-fill local-paper source verification,
   - artifact paths used.
6. Keep the result descriptive only. It must not pick thresholds, select a
   model, start a promotion gate, or mutate replay behavior.
7. Add focused tests proving:
   - attribution consumes artifacts only,
   - no broker/network/credential access is needed,
   - zero-fill local-paper evidence remains replayable,
   - generated artifacts are outside Git or mocked in tests,
   - missing zero-fill event files remain tolerated only for zero-fill variants,
   - PyTorch stays confined to Docker `research` and local tests do not import
     torch.
8. Run the attribution against the standardized branch artifacts. Use Docker
   `research` only if an existing trace must be regenerated; otherwise prefer
   local artifact-only execution.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Report any focused tests, artifact-only smoke commands, Docker `research`
commands, GPU availability, and artifact paths used.

## Suggested Commit Message

`Add bounded probability alignment attribution`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- source-vs-holdout alignment findings,
- what was intentionally not built,
- next recommended goal.
