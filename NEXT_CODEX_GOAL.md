# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build bounded saturated feature-branch replay opportunity attribution.

This advances PnL attribution, backtest and walk-forward validation, and
feature/model research by explaining why the guarded hidden-units feature-branch
replay restored its threshold-pair cap but still produced zero local-paper
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
   - `bounded-hidden4-bar-pressure-contrast-smoke-20260716`
   - `bounded-hidden4-bar-pressure-contrast-replay-cap2-20260716`
   - `bounded-hidden4-derivation-guard-replay-cap2-20260716`
   - `bounded-hidden16-bar-pressure-model-axis-replay-cap2-20260716`
3. Inspect existing probability trace, threshold robustness, and threshold
   attribution helpers before adding code. Prefer reusing or extending a small
   existing attribution helper over adding a new job family.
4. Add one bounded attribution path that explains, per slice and threshold pair,
   whether the guarded `0.998/0.447` and `0.999/0.447` variants had buy
   opportunities, sell opportunities, local-paper fills, PnL, and drawdown.
5. Keep the result descriptive. It must not choose a threshold, rank a model, or
   promote a candidate.
6. Add focused tests proving the attribution:
   - consumes existing local artifacts without broker/network/credential access,
   - handles zero-fill variants with missing event files,
   - keeps local-paper source evidence separate from disabled broker evidence,
   - writes generated artifacts outside Git or mocks artifact writes in tests.
7. Run a bounded Docker `research` or local artifact-only smoke command against
   the guarded hidden4 replay if the code change is sound.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Attribute saturated feature branch replay opportunities`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- opportunity attribution findings,
- what was intentionally not built,
- next recommended goal.
