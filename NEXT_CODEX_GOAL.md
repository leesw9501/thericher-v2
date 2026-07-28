# Next Codex Goal

## Objective

Build one bounded prospective NAS D1 shadow-observation loop for the frozen
volatility-conditioned trend candidate package.

This converts neither the sealed r5 result nor any candidate into a winner. It
prepares independent, newly observed evidence from the local cache while the
existing Data schedule continues to own KIS collection.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattest the frozen NAS D1 panel, r2 CPU/CUDA artifacts, and the completed
   r5 sealed receipt before writing any prospective receipt.
3. Ask Claude for a concise falsification-first review of the prospective
   observation boundary. If OAuth remains expired, record `review_unavailable`
   and continue this private, non-promoting package.

## Contract

- The observer consumes only local `D:\market_data` input and external frozen
  artifacts under `D:\thericher-v2\model-artifacts`; it makes no KIS,
  provider, broker, or credential call itself.
- Freeze the post-r5 freshness boundary, causal feature timing, candidate
  identities, local-paper costs, non-overlapping target timing, and source-safe
  receipt schema before opening any newly observed target.
- It may emit `input_unavailable` when no eligible post-boundary local session
  exists. That is a completed scoped outcome, not a scheduler, Research, or
  Paper-trading hold.
- When eligible sessions exist, replay every frozen candidate independently
  through in-memory `source: local_paper` fills. Retain only source-safe
  aggregate evidence outside Git; never retain raw bars, target values,
  predictions, per-fill rows, account identifiers, or checkpoint copies.
- Do not rank, select, tune, ensemble, promote, or route a candidate to KIS
  Paper. A prospective observation is evidence only.

## Work

1. **Data:** expose a reattested local freshness boundary and exact eligible
   post-boundary session contract without fetching, mutating caches, or making
   a point-in-time universe claim.
2. **Engine Research:** implement the frozen-candidate prospective observer,
   immutable precommit/summary receipts, and one network-disabled Docker smoke.
3. **Validation:** prove freshness-boundary isolation, local-paper-only replay,
   artifact containment, no network/credential/broker route, and source-safe
   unavailable/completed receipts.
4. **Execution:** remain independent. Do not create an intent, query KIS, or
   submit, modify, or cancel a broker order for this observer.

## Boundaries

- No KIS call, `.env` or credential read, provider download, paid asset, public
  service, account/quote/order route, broker submission, or live behavior.
- Do not use r5 outcomes to choose candidate coverage, threshold, sizing,
  aggregation, or a KIS Paper action.
- Do not create report/gate scaffolding. A missing fresh session closes only the
  observer's current receipt and cannot block the independent Data scheduler or
  another ready lane.

## Completion

- An immutable source-safe precommit and either an eligible prospective summary
  or scoped `input_unavailable` receipt are written outside Git.
- Frozen lineage, freshness isolation, local-paper replay, terminal-flat
  accounting, artifact containment, and offline route boundaries have focused
  tests.
- Refresh stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add prospective NAS shadow observer`
