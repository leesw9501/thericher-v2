# Next Codex Goal

## Objective

Qualify or reject a **corporate-action event sidecar** for the completed KIS
Paper `QQQ/SPY` daily cache, so a future chronological Research contract can
know which unadjusted price pairs are comparable.

The KIS-only pair is now hash-attested for 4,756 common sessions from
2007-08-21 through 2026-07-17, but its `MODP=0_unadjusted` series cannot supply
daily return labels yet. Claude's 2026-07-25 falsification verdict was
`unsupported`: dividend/split event dates must be source-attested and handled
before a return target, naive return baseline, model, GPU run, ensemble, or
Paper decision is considered.

## Standing Authority

- The operator has authorized private use of `TIINGO_API_TOKEN` for no-cost
  Tiingo standard-EOD data work on `QQQ` and `SPY`. Read it only through a
  strict local loader; never print, log, hash into artifacts, commit, or send
  it to Claude.
- Store event-sidecar bytes only under `D:\market_data`; generated summaries
  remain under `D:\thericher-v2\model-artifacts`. Never store either in Git.
- Do not call KIS, account, position, order, or live endpoints for this goal.
  Do not read `KIS_LIVE_*`, submit broker orders, buy anything, publish
  data/services, or use a GPU.
- The existing 2022-11-22 through 2026-06-22 Tiingo event snapshot is evidence
  to inventory, not proof of the full 2007-2026 coverage required here.

## Role-Owned Work

### Codex Orchestrator

Keep the work limited to one source-contract question. Continue independent
scheduled KIS Data and Paper Execution work, but do not let an event-sidecar
result alter their authority or cadence. Record the Claude `unsupported`
resolution in the relevant stateboards without creating a new approval gate.

### Data Agent

1. Re-attest the completed KIS QQQ/SPY cache offline and inventory the existing
   Tiingo event snapshot's actual coverage before downloading anything.
2. If it lacks the required date range, use the authorized Tiingo standard-EOD
   endpoint in bounded, deduplicated QQQ/SPY requests. Retain only normalized
   event facts needed for the contract: symbol, source date, event kind, and
   event value/factor where present, plus coverage/provenance/hash metadata.
   Do not persist or report Tiingo quote rows/prices.
3. Build a small immutable external event-sidecar snapshot with strict schema,
   source coverage, event-date semantics, KIS-session mapping, and hash
   attestation. Preserve unknown semantics as `unqualified`; do not guess an
   event date, synthesize an adjustment, or silently drop an unmatched event.
4. Produce a metadata-only result that states whether affected daily
   feature/target pairs can be masked deterministically. It must never create
   training labels, a dataset for a model, or a broker input.

### Engine Research Agent

Define only a prospective QQQ/SPY source-contract receipt: chronological
availability, target timing, and the exact event-pair exclusion rule it would
require. It may consume Data's metadata/hash result, but must not train, score,
select, retune, ensemble, run CUDA, or replay a return strategy. If the
sidecar is unqualified, record that scoped outcome and keep the cache
collection-only.

### Execution Agent

Keep Paper routing, scheduled sessions, and reconciliation unchanged. The event
sidecar is not an order, price, sizing, fill, or PnL input.

## Completion Evidence

- The external sidecar is either hash-attested with exact QQQ/SPY coverage and
  deterministic KIS-session mapping, or the precise missing semantic/coverage
  fact is recorded as `unqualified` without retry loops.
- Tests prove token redaction, no KIS/broker/network access in the offline
  matcher, no raw Tiingo quote persistence, no artifact-in-Git behavior, and
  no label/model/Paper path from this objective.
- The current three-ETF baseline stays frozen, and the next Research decision
  remains separate from any event-sidecar result until its own Claude challenge.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Qualify daily corporate-action inputs`
