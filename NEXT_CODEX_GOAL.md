# Next Codex Goal

## Objective

Attach the existing KIS Paper terminal-field observation to an exact
acknowledged daily SPY receipt, without turning its incomplete source semantics
into a Paper-trading gate or a terminal/PnL claim.

The current standalone probe has established that KIS's documented
`VTTS3035R` fields are useful structural evidence but insufficient to call a
fill, cancellation, or realized PnL. Future acknowledged receipt states now
carry a write-once submission timestamp; use that state only to collect the
same safe field-presence evidence automatically after the existing daily
receipt observer. A legacy state without the timestamp remains a scoped
`submission_time_missing` fact, not a reason to pause another Paper action.

## Standing Authority

- All private `KIS_PAPER_*` reads, virtual submit/modify/cancel,
  reconciliation, routine sizing, `D:` retention, and goal-owned schedules
  are authorized. Continue ready Paper work by default.
- Do not read `KIS_LIVE_*`, use a live host/route, real capital, paid data,
  unclear-rights assets, public exposure, Git-hosted raw data/artifacts, or
  secrets.
- A missing, blank, stale, ambiguous, or unretained fact applies only to that
  receipt or invocation. It cannot block a distinct Paper intent, another due
  session, cache collection, research campaign, or schedule run.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
   `DECISIONS.md`, and `RUNBOOK.md`.
3. Read `agents/README.md`, `agents/data.md`, `agents/engine-research.md`,
   and `agents/execution.md`.
4. Inspect only sanitized daily-session, receipt-observer, terminal-probe,
   runtime, and task metadata before choosing a recovery action.
5. Ask Claude for a concise falsification-first check before wiring the
   terminal-field result into the scheduled daily receipt path.

## Role-Owned Work

### Data Agent

1. Reconfirm the narrow virtual `VTTS3035R` source contract for SPY/AMEX:
   acknowledged-submission ET date, bounded pagination, direct/original order
   identity, and field-presence-only provenance.
2. Ensure this observation does not consume raw market data, alter cache
   cursors, or reinterpret `raw_market_data_retained` as execution authority.

### Engine Research Agent

1. Preserve `performance_label = None` and `pnl_status: not_observed` for all
   terminal-field observations under the current source contract.
2. Add no model feature, candidate ranking, ensemble input, or PnL attribution
   from field presence, acknowledgement, aggregate positions, or an absent
   history row.

### Execution Agent

1. After an existing daily session has verified its exact receipt/run mapping,
   invoke the existing terminal-field probe only for that same durable state.
   Do not create a second scheduler, latest-run scan, submit/modify/cancel
   path, or a new credential-bearing service.
2. Embed only the probe's existing categorical safe payload and opaque artifact
   reference in the daily outcome. Preserve the canary and receipt-observer
   outcomes even when the probe is unavailable.
3. Keep terminal state unqualified and PnL not observed. A probe result may
   improve source coverage but cannot alter the order lifecycle, cause a retry,
   or suppress later distinct Paper work.

### Validation Agent

1. Independently test exact receipt/run binding, acknowledged-submission date
   use, legacy/missing timestamp behavior, redaction, replay, and artifact
   placement.
2. Test that no extra order action, live route, raw response persistence,
   terminal lifecycle promotion, or model/PnL label can result from the
   integration.

## Completion Evidence

- A future acknowledged daily receipt can automatically emit only the existing
  categorical terminal-field observation; legacy or unavailable states remain
  scoped no-observation facts.
- The daily path remains Paper-only, replayable, secret-free, and does not add
  a scheduler, a quota, a permission latch, or a second order path.
- Field presence does not become a fill/cancel result, realized PnL, model
  label, or Paper-work decision.
- Raw broker facts and generated artifacts remain outside Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Attach Paper terminal observation to daily receipt`
