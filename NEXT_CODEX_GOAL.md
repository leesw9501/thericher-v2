# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded first-evaluation source-context depth contrast.

This advances feature/model research, backtest validation, and PnL attribution
by checking whether a deeper bounded PyTorch CUDA run changes the completed
first-evaluation source-context evidence. Keep the feature set, model shape,
regularization, preprocessing, source symbols, and evaluation symbols fixed.

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
  hidden-units sweep, source-context search, feature-set search, or model
  search.
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
   Existing Docker `research` jobs and artifact-only comparison scripts do not
   need a Claude check.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts as the short-run reference:
   - First-evaluation source-context feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
   - First-evaluation source-context replay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-firsteval-source-context-second-holdout-replay-20260716\metrics.json`
   - First-evaluation source-context attribution:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-second-holdout-20260716\metrics.json`
   - AMD entry-filter overlay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-amd-entry-filter-overlay-20260716\metrics.json`
   - Cross-sample entry-filter overlay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-cross-sample-entry-filter-overlay-20260716\metrics.json`
3. Run one Docker `research` PyTorch CUDA feature-branch job with the same
   settings as the short reference except bounded training caps:
   - feature set: `core_plus_entry_adverse_v1`
   - hidden units: `4`
   - weight decay: `0.001`
   - feature preprocessing: `feature_standardization`
   - max bars: `240`
   - max epochs: `16`
   - max steps: `512`
   - source slices: ANET, APH, APO, APP, ASML, AVGO from
     `snapshot=2026-06-18`
   - evaluation/replay slices: AAPL, ABBV, ABNB, ABT, ACN, AMD from
     `snapshot=2026-06-18`
4. Replay the deeper artifact through the existing
   `candidate_feature_branch_replay` path with cap-2 thresholds and the same
   evaluation/replay slices. Keep every generated fill verified as
   `source: local_paper`.
5. Run artifact-only attribution comparing the short and deeper source-context
   evidence:
   - probability range and threshold band,
   - buy/sell opportunity counts,
   - local-paper fill count and fill-source verification,
   - PnL and max drawdown range,
   - AMD segment count and fee-aware delta behavior if fills appear,
   - whether the completed entry-filter overlays argue against encoding an
     entry filter.
6. Do not change feature set, hidden units, regularization, preprocessing,
   source symbols, evaluation symbols, thresholds by search, simulator exits,
   broker behavior, dashboard, scheduler, or agent framework.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data; it should reuse the existing
  `snapshot=2026-06-18` Yahoo 1m file.
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

`Run firsteval source-context depth contrast`

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
