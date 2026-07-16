# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Codify a bounded trade-path attribution helper.

This advances PnL attribution and paper-trading preparation by turning the
manual longer-window trade-path attribution into a small reusable helper that
can inspect future local-paper replay artifacts without creating another broad
report or gate workflow.

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
2. Ask Claude CLI for a short drift-check before code edits, then judge it
   against `HANDOFF.md`, `ARCHITECTURE.md`, and `DECISIONS.md`.
3. Use recent artifacts as behavior context, not as promotion evidence:
   - `bounded-out-of-symbol-disjoint-eval-replay-cap2-240bars-20260716`
   - `bounded-longer-out-of-symbol-disjoint-eval-post-entry-summary-20260716`
   - `bounded-longer-out-of-symbol-disjoint-eval-trade-path-20260716`
4. Add a small pure helper near the existing feature-branch replay attribution
   path that can derive closed trade segments from local-paper event artifacts
   plus selected bars.
5. Keep it artifact-driven and broker-free:
   - parse local-paper fill events,
   - pair buy/sell fills into closed segments,
   - calculate holding duration,
   - calculate gross and fee-aware deltas,
   - calculate simple adverse/favorable movement from provided bars,
   - report local-paper fill-source verification.
6. Avoid adding a new research job kind unless the existing call path cannot
   express the helper. Prefer a direct function with focused tests.
7. Add focused tests proving:
   - local-paper sources are counted and non-local fills are surfaced,
   - fee-aware deltas are deterministic,
   - missing zero-fill event files remain tolerated only for zero-fill cases
     where applicable,
   - no broker, network, credential, or `.env` access is required.
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

Report any focused tests, artifact-only commands, Docker `research` commands,
GPU availability, and artifact paths used.

## Suggested Commit Message

`Add bounded trade path attribution helper`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- trade-path helper behavior,
- what was intentionally not built,
- next recommended goal.
