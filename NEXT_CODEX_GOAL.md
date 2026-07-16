# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded longer-window trade-path attribution slice.

This advances PnL attribution and paper-trading preparation by explaining the
closed trade paths from the 240-bar out-of-symbol replay before spending GPU
time on another model-axis or threshold-only branch.

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
- Keep diagnostic overlay outcomes labeled separately, for example
  `source: diagnostic_overlay`.
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
   - `bounded-out-of-symbol-disjoint-eval-replay-cap2-240bars-20260716`
   - `bounded-longer-out-of-symbol-disjoint-eval-opportunity-attribution-20260716`
   - `bounded-longer-out-of-symbol-disjoint-eval-post-entry-summary-20260716`
3. Prefer existing artifacts, probability traces, event files, and selected
   local Yahoo bars. Do not retrain, rerun replay, or run threshold search
   unless existing evidence cannot support the attribution.
4. For fill-bearing variants in the 240-bar replay, attribute each closed trade
   segment with:
   - entry timestamp, price, source, and fee,
   - first sell-threshold signal timing,
   - exit timestamp, price, source, and fee,
   - holding duration,
   - gross and fee-aware deltas,
   - simple adverse/favorable movement from selected bars,
   - local-paper fill-source verification.
5. Write compact trade-path evidence outside Git under
   `D:\thericher-v2\model-artifacts`.
6. Keep the result descriptive only. Do not rank symbols, pick thresholds,
   select a model, or add promotion language.
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

Report any focused tests, artifact-only commands, Docker `research` commands,
GPU availability, and artifact paths used.

## Suggested Commit Message

`Add bounded longer-window trade path target`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- longer-window trade-path findings,
- what was intentionally not built,
- next recommended goal.
