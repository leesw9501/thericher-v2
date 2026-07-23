# Next Codex Goal

## Objective

Observe and classify the next due autonomous KIS Paper daily SPY session.

The installed daily head task runs at 22:15 KST and the daily session runs at
23:50 KST, Tuesday through Saturday. They are already authorized private
Paper work. Let the next due run produce its normal safe evidence, then inspect
only the sanitized output and fix a demonstrated deterministic fault if one
exists. A valid `no_intent`, unavailable source fact, or an acknowledged Paper
receipt are all useful outcomes; none is a permission latch for another due
session, data run, or research task.

## Standing Authority

- All private `KIS_PAPER_*` reads, virtual submit/modify/cancel,
  reconciliation, routine sizing, `D:` retention, and goal-owned schedules
  are authorized. Continue due Paper work by default.
- Do not read `KIS_LIVE_*`, use a live host/route, real capital, paid data,
  unclear-rights assets, public exposure, Git-hosted raw data/artifacts, or
  secrets.
- Historical `raw_market_data_retained: false`, one-shot completion, missing
  receipt, ambiguous result, or a failed probe is evidence only. It cannot
  block a distinct correctly scoped Paper action.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
   `DECISIONS.md`, and `RUNBOOK.md`.
3. Read `agents/README.md`, `agents/data.md`, `agents/engine-research.md`,
   and `agents/execution.md`.
4. Inspect only sanitized scheduled-task, head-index, daily-session,
   receipt-observer, terminal-probe, runtime, and task metadata.
5. Ask Claude only if an actual outcome would change terminal/PnL semantics,
   route isolation, a major runtime, or recovery policy.

## Role-Owned Work

### Data Agent

1. Reattest the next daily-head input and report only source freshness,
   provenance, and categorical cache availability for the SPY/AMS session.
2. Keep raw retention and any source gap separate from Paper order authority.

### Engine Research Agent

1. Treat daily receipt, receipt-observer, and terminal-field facts as
   execution coverage only. Keep `performance_label = None`,
   `pnl_status: not_observed`, and no candidate/ensemble update.
2. Continue ready CPU data/feature preparation that does not depend on this
   session; GPU work remains limited to an eligible frozen campaign.

### Execution Agent

1. Let the installed head and daily-session tasks execute at their normal due
   times. Do not add a duplicate task, manual capital gate, or alternate route.
2. Inspect the one safe daily outcome. If it has an acknowledged receipt,
   verify the receipt observer and terminal-field payload share its exact run
   identity and remain Paper-only. If it is no-intent or unavailable, preserve
   the factual reason and fix only an evidenced technical defect.

### Validation Agent

1. Verify any fix retains virtual-host-only routing, secret redaction,
   replayability, no fabricated terminal/PnL conclusion, and no extra order
   side effect.

## Completion Evidence

- One next due head/session outcome is available as sanitized external
  evidence, or a concrete host/scheduler fault is fixed and verified.
- The result is correctly classified without a report gate, paper quota, or
  manual approval request.
- Any automatic terminal-field observation remains categorical,
  `unqualified`, and outside Research labels/PnL.
- Artifacts and raw data remain on `D:` and outside Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Record autonomous daily Paper session`
