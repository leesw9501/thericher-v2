# Next Codex Goal

## Objective

Materialize and qualify the first source-local broad KIS Paper D1 development
panel from the active `daily-nas-broad/v1` cache.

This is a field-compatibility and dataset-contract objective, not a historical
universe, ranking, corporate-action, profitability, model-selection, or Paper
trading claim. The active broad collector continues independently.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the broad registry/index identity and inspect only source-safe
   aggregate coverage facts. Do not print raw symbols, rows, prices, volumes,
   tokens, account identifiers, or provider response bodies.
3. Ask Claude for a concise falsification-first drift check before freezing a
   research split, target, or consumer contract. Include current-listing
   survivorship, adjustment/corporate-action limitations, feature timestamps,
   and the strongest leakage kill test.

## Authority And Boundaries

- The installed broad collector owns its KIS Paper data schedule. This objective
  must not issue an extra KIS request, alter its index, or compete for its lock.
- Read only committed, reverified broad-cache snapshots. A changing index,
  snapshot hash mismatch, or active-write race is scoped `retry/reconcile`
  evidence, never a company hold.
- Keep all raw data under `D:\market_data` and all generated artifacts under
  `D:\thericher-v2\model-artifacts`; write neither to Git.
- Keep the registry's `current_listing_only`, `non_pit`, and `non_ranking`
  fields attached to every derived artifact. Do not blend Norgate, Tiingo,
  ETF, legacy KIS, or other provider rows into this panel.
- No account, position, quote, order, KIS live, dashboard, model promotion, or
  GPU training route belongs to this objective.
- Respect the 20 percent storage warning and 15 percent free-space floor.

## Work

1. **Data:** implement a read-only broad-cache catalog/materializer that
   reattests registry, index, manifests, raw hashes, target cursors, and source
   scope before consuming a committed snapshot.
2. **Data:** build one bounded external panel manifest from whatever stable
   target/session coverage exists now. Preserve per-target coverage and missing
   facts; do not demand full 2,119-target backfill before making useful local
   progress.
3. **Validation:** add focused tests for active-write/index drift, cache/raw
   hash mismatch, source-scope propagation, external-only outputs, and absence
   of network/credential/broker access.
4. **Engine Research:** if the panel meets an explicitly frozen minimal shape,
   prepare a CPU-only naive baseline contract. Do not train, rank, ensemble, or
   open a target until its own data/split/cost contract and Claude review exist.
5. Refresh the Data and Engine Research stateboards with only the current
   source-safe coverage and handoff facts.

## Completion

- A reattestable external broad D1 panel manifest or a precise scoped
  `input_unavailable/reconcile` artifact exists.
- Derived artifacts preserve KIS-only and current-listing/non-PIT/non-ranking
  limitations.
- Focused tests prove the materializer is read-only and independent from the
  active collector.
- Refresh affected stateboards, replace this file with exactly one next
  objective, then continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Materialize broad KIS D1 panel`
