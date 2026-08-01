# Next Codex Goal

## Objective

Prepare one bounded prospective intraday engine baseline for SPY using only
newly observed completed KIS Paper market data. The baseline must be distinct
from MIM-30: it is a causal engineering and Paper-readiness path, not a source
replication, historical MIM backtest, or profitability claim.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, Execution, and orchestration
   stateboards.
2. Ask Claude for a concise falsification-first drift check before changing a
   Paper execution route, scheduler behavior, or execution/research contract.
   Never include credentials, raw prices, account facts, fills, or labels.

## Boundaries

- `KIS_PAPER_*` is authorized for this private prospective work. Do not read
  `KIS_LIVE_*` or route anything to live.
- Retain raw market data and mutable capture state only under `D:\market_data`.
  Keep source-safe receipts and generated artifacts only under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never store
  them in Git.
- Keep the existing KIS Paper route and deterministic risk boundaries intact.
  A proposed baseline may exercise an already-supported virtual-paper canary
  only after its call-time identity, freshness, durable-intent, reconciliation,
  and cancellation rules pass. It must not reuse an unknown prior intent.
- The baseline may not claim to replicate MIM-30, may not use MIM historical
  results, and may not claim profitability from a prospective observation.

## Work

1. **Data:** define and test one source-safe prospective SPY session record
   from completed 1m bars. It must declare ET/DST/session geometry, its
   source-contract identity, and which 1m/5m/10m/1h/3h views are actually
   complete at each decision cutoff. Missing or early-close segments must
   abstain rather than be filled.
2. **Engine Research:** connect that record to the existing causal
   multi-timeframe sequence contract and one fixed, deterministic baseline
   decision. Freeze its lookbacks, decision cutoff, target state, no-trade
   behavior, cost assumptions, and a naive comparator before observing any
   prospective outcome. Build only pure, testable decision/input plumbing;
   do not train, tune, select, or ensemble a model in this objective.
3. **Execution:** reattest the existing local-paper and KIS Paper boundary for
   this distinct baseline. A local replay must retain `source: local_paper`.
   A KIS Paper canary, if the existing route reaches one during a regular
   session, must retain its own route identity and immutable lifecycle receipt;
   it is not a local-paper fill and is not a model validation result.
4. **Validation:** prove that the prospective record and decision are causal,
   require no broker/network/credential access in unit tests, abstain on stale
   or incomplete data, and cannot create a duplicate Paper intent. Record
   whether the first fresh-session observation was captured or remains
   scheduler-owned without making that external time a company hold.

## Completion

- One source-safe prospective-baseline contract and focused tests are complete.
- The baseline has an explicit no-trade path and cannot consume MIM historical
  evidence or source-window proxy semantics.
- A fresh session may be `not_yet_observed`; then its scheduler remains owned
  by Data/Execution while the next objective proceeds. Do not wait in the
  foreground for market time.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Suggested Commit Message

`Add prospective intraday baseline`
