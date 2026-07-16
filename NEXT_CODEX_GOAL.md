# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first bounded diagnostic exit-latency composite overlay.

This advances PnL attribution and backtest/walk-forward validation by using the
conditional exit-overlay contrast to compute one descriptive composite scenario:
segments matching `latency_ge_5_at_2_bar` use the fixed 2-bar
`diagnostic_overlay` mark, while all other segments keep their existing
`source: local_paper` exit evidence. This must not mutate local-paper fills,
rerun replay, or apply an exit policy to the simulator.

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
- Do not start a broad scheduler, agent framework, promotion gate, dashboard
  expansion, threshold optimizer, preprocessing search, regularization sweep,
  or model search.
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

3. Ask Claude CLI for a short drift-check before code edits. If the composite
   can run artifact-only with existing code, no Claude check is needed.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts as context:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-conditional-exit-overlay-contrast-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-diagnostic-exit-overlay-helper-smoke-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-exit-timing-overlay-20260716\metrics.json`
3. Build one compact artifact-only composite diagnostic that:
   - uses `latency_ge_5_at_2_bar` as the only condition under inspection,
   - substitutes the fixed 2-bar diagnostic overlay outcome only for matching
     segments,
   - keeps existing local-paper exit evidence for all other segments,
   - labels substituted outcomes with `source: diagnostic_overlay`,
   - preserves retained outcomes with `source: local_paper`,
   - summarizes gross-delta and source evidence by loss-bearing versus
     non-negative segment groups.
4. Write one compact composite artifact outside Git, for example:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-exit-latency-composite-overlay-20260716\metrics.json`
5. Do not add a CLI, research job kind, dashboard, scheduler, model feature,
   training path, replay rerun, threshold search, policy selection, simulator
   exit rule, or broker behavior.
6. Only edit code if the composite exposes a helper bug; if code changes are
   needed, ask Claude CLI first and keep the fix focused.
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

Also report any focused test, artifact-only composite command, Docker
`research` command, GPU availability, and artifact paths used.

## Suggested Commit Message

`Add exit latency composite overlay diagnostic`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- composite diagnostic behavior,
- what was intentionally not built,
- next goal.
