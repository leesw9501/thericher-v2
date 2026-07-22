# Next Codex Goal

## Objective

Connect the scheduled KIS Paper daily SPY session to the receipt-linked
read-only observer it already needs.

When the existing daily session creates or recovers one exact durable receipt
identity, it should trigger observation of that exact identity through the
Paper-only read path. This adds timely execution evidence without turning
observation, a missing receipt, a stale fact, or a historical marker into a
permission latch, one-shot quota, or new order workflow.

## Standing Authority

- All private `KIS_PAPER_*` market/account reads, virtual order submit/modify/
  cancel, reconciliation, sizing, local `D:` retention, and goal-owned
  schedules are authorized. Continue ready Paper work by default.
- Do not read `KIS_LIVE_*`, use a live host/route, real capital, paid data,
  unclear rights, public exposure, Git-hosted raw data/artifacts, or secrets.
- A no-intent daily session, failed observer, unavailable quote, stale receipt,
  missing completion, `raw_market_data_retained: false`, or unknown exact
  outcome is scoped evidence only. It cannot disable a later distinct correct
  Paper action, cache retry, schedule run, or another lane.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the sanitized daily-session, receipt lifecycle, observer, and
   scheduled-task metadata before changing their handoff.
5. Ask Claude for a concise falsification-first drift check before changing the
   scheduled session's external KIS call graph or receipt-observation contract.

## Role-Owned Work

### Data Agent

1. Confirm that daily-input freshness remains a data-quality fact, not a Paper
   permission condition. Keep the current KIS-native SPY source and safe
   provenance contract intact.
2. Identify only the timestamp/identity facts needed to associate a session
   outcome with its exact receipt; do not expose rows, prices, hashes, or raw
   broker data to the session projection.

### Engine Research Agent

1. Define the minimal model-side consumption rule for linked Paper evidence:
   receipt, intended side, observation reference, lifecycle category, and
   `pnl_status`. Missing/ambiguous observation remains excluded from model
   performance claims rather than a negative label.
2. Keep local-paper replay and KIS Paper evidence separate. Do not tune the
   baseline or promote a candidate from a single Paper observation.

### Execution Agent

1. Carry the exact opaque receipt-run identity from a daily session outcome to
   the observer without scanning unrelated state or selecting a "latest" run.
2. Make the existing scheduled daily SPY session invoke or queue only that
   same-run read-only observation after its own durable outcome is known. A
   no-intent, rejected, unavailable, or already-observed result must remain
   replayable and must not change an order result or block a later run.
3. Preserve structural route isolation: the observer has no submit, modify, or
   cancel capability; the handoff must not make a read-only failure retry or
   replace an order.
4. Use the existing daily schedule when possible. Any task/config change must
   be private, idempotent, recoverable, and free of a manual approval, capital,
   profitability, or trade-count gate.

### Validation Agent

1. Independently test exact same-run linkage, session replay, observer failure,
   no-intent behavior, and stale/ambiguous facts with no live KIS dependency.
2. Prove the linked path cannot emit an extra order request or turn a completion
   ID sighting, position category, or daily bar into a fill or PnL assertion.
3. Verify all safe artifacts remain outside Git and do not contain credentials,
   account identifiers, raw order IDs, prices, quantities, or broker payloads.

## Completion Evidence

- A scheduled daily SPY session can cause observation of only its exact durable
  receipt identity, with no global/latest-run scan or side-effectful observer.
- A linked observation is safe under replay, no-intent, stale, missing, and
  ambiguous inputs, and never changes the original Paper order result.
- The current Paper-only schedule remains usable without a new one-shot marker,
  quota, report, or operator checkpoint.
- KIS Paper / local-paper attribution stays truthful and `pnl_status` remains
  `not_observed` unless an official authoritative fact supports more.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Link daily Paper sessions to receipt observation`
