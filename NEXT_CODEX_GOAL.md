# Next Codex Goal

## Objective

Qualify the first exact KIS Paper terminal-fact contract for receipt-linked SPY
orders.

The daily SPY session already creates a Paper-only order path and automatically
records a same-receipt read-only observation. This objective determines whether
official KIS Paper facts can truthfully distinguish a terminal fill or cancel
and, only if enough exact facts exist, support receipt-attributed realized PnL.
An insufficient response is a useful `not_observed` finding, never a Paper
permission latch or a reason to stop other work.

## Standing Authority

- All private `KIS_PAPER_*` market/account/order reads, virtual order submit/
  modify/cancel, reconciliation, sizing, local `D:` retention, and goal-owned
  schedules are authorized. Continue ready Paper work by default.
- Do not read `KIS_LIVE_*`, use a live host/route, real capital, paid data,
  unclear rights, public exposure, Git-hosted raw data/artifacts, or secrets.
- Missing, blank, stale, ambiguous, or unretained facts describe only that
  invocation or receipt. They cannot block a distinct Paper intent, another
  due session, cache collection, research campaign, or schedule run.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
   `DECISIONS.md`, and `RUNBOOK.md`.
3. Read `agents/README.md`, `agents/data.md`, `agents/engine-research.md`,
   and `agents/execution.md`.
4. Inspect only sanitized daily-session, canary, observer, runtime, and task
   metadata before choosing a recovery or probe action.
5. Ask Claude for a concise falsification-first check before relying on any KIS
   completion/position field as a terminal lifecycle or PnL fact.

## Role-Owned Work

### Data Agent

1. Inventory the official KIS Paper completion/history field contract for the
   exact SPY/AMEX scope: endpoint, transaction ID, pagination, field presence,
   timestamp semantics, and provenance. Use bounded private reads only; retain
   no raw response, order ID, price, quantity, account value, or credential.
2. Publish only categorical field-support and freshness evidence. Keep the
   current daily source/provenance and `raw_market_data_retained` semantics
   separate from order-terminal interpretation.

### Engine Research Agent

1. Define the exact receipt-attribution threshold: full digest identity,
   categorical terminal state, authoritative realized amount/cost basis if
   available, and `performance_label = None` for every incomplete fact.
2. Keep `open`, same-day ID sighting, aggregate position, and daily bars out of
   model scoring, labels, selection, and PnL claims. Preserve local-paper replay
   as separate evidence.

### Execution Agent

1. Add or verify only the smallest read-only KIS Paper parser/probe needed to
   determine whether exact terminal facts are present. It must have no submit,
   modify, cancel, latest-run scan, or live-route capability.
2. Promote `filled`, `cancelled`, or realized PnL only when an official exact
   per-order fact supplies the required fields and identity. Otherwise preserve
   `outcome_unknown` / `unavailable` and `pnl_status: not_observed`.
3. Integrate a supported terminal fact into the existing exact receipt observer
   and scheduled daily session only after offline, fake-transport, redaction,
   replay, and route-isolation tests pass. Do not add a second approval system
   or schedule unless it directly improves this engine loop.

### Validation Agent

1. Independently test that ambiguous, absent, stale, cross-receipt, and
   aggregate facts cannot become a terminal state, realized PnL, model label,
   or order side effect.
2. Test exact identity, redaction, pagination bounds, Paper/live isolation,
   replay, and artifact placement without network, credentials, or KIS.

## Completion Evidence

- The project has an evidence-backed exact terminal-field contract or an
  explicit bounded result that the current KIS Paper source is insufficient.
- Any newly supported terminal state or PnL is tied to the full receipt digest
  and official exact facts, never to an absence, daily bar, position aggregate,
  acknowledgement, or local estimate.
- Current daily Paper and observer paths stay private, Paper-only, replayable,
  and free of new approval latches, quotas, or report sprawl.
- Raw broker facts, secrets, data, and generated artifacts remain outside Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Link daily Paper sessions to receipt observation`
