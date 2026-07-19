# Next Codex Goal

## Objective

Run one bounded, local-only Data inventory to determine whether existing
`D:\market_data` contains a fresh, unspent daily-source candidate for a future
engineering contract. This is a data-decision task, not model work.

## Context

- The r4 source-separated contract and CPU-only batch are closed. Its 3,420-row
  validation slice is spent and cannot be reused.
- The first r4 CUDA MLP stopped before prediction/checkpoint creation because
  deterministic CUDA workspace configuration was missing. The corrected Docker
  setting passed a synthetic-only smoke but does not reopen r4.
- Norgate trial daily history is limited to its known 483-session window.
  Tiingo r2 and broad Yahoo evidence have separate non-PIT, static-universe,
  adjustment, or source-right limitations.

## Required First Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
   `DECISIONS.md`, `RUNBOOK.md`, `agents\README.md`, `agents\data.md`, and
   `agents\engine-research.md`.
3. Ask Claude for a short falsification-first drift check before relying on any
   new source, date partition, universe, or eligibility conclusion.

## Data-Owned Work

1. Inspect only known local snapshot manifests, directory metadata, and narrow
   bounded samples. Do not recursively scan all of `D:\market_data` or read
   `.env`, credentials, provider tokens, or broker data.
2. Compare the known Norgate, Tiingo r2, broad Yahoo, and intraday candidates
   against r4's consumed decision/validation window. Identify any candidate
   that is both locally available and not already used as r4 validation.
3. For every plausible candidate, record its source, symbols, date range,
   granularity, lineage/rights, overlap with r4, point-in-time and adjustment
   limitations, and whether it can support only future engineering preparation
   or nothing at all.
4. Write one compact, external-only Data evidence artifact under
   `D:\thericher-v2\model-artifacts\data-agent`; do not put data bytes,
   artifacts, or model output in Git.
5. Conclude exactly one of:
   - a named fresh candidate can proceed to a new, still non-promotional
     contract preflight; or
   - no local candidate is suitable, with an exact operator data request and
     free/paid alternatives.
6. Keep Engine Research idle on real market training. It may only retain the
   corrected synthetic CUDA bootstrap evidence; it must not rerun r4, launch a
   new model, compare candidates, or create an ensemble.

## Hard Boundaries

- No provider download, network call, KIS access, paper/local-paper execution,
  order, live behavior, credential read, or paid action.
- No model training, GPU market-data job, r4 retry, tree/TCN/seed sweep,
  ranking, promotion, PnL, ensemble, holdout, or profitability claim.
- Do not treat absence of a local candidate as a reason to weaken data policy.

## Completion

Refresh stateboards, `HANDOFF.md`, `DECISIONS.md`, and this next goal. Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Commit, push, and report the artifact path/hash, the chosen conclusion, any
operator data request, and the next recommended objective.
