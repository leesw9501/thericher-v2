# Next Codex Goal

## Objective

Complete the first autonomous KIS Paper operating cycle: let the installed
quote-session and intraday-head schedules run on their next eligible US-session
windows, integrate their sanitized outcomes, and keep the local operations
console truthful and current.

This is execution and data learning, not a profitability, model-promotion, or
manual-approval milestone. The schedules are already installed and invoke their
named Docker profiles with `--build`.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market/account reads, positions, open orders,
  virtual-order submit/modify/cancel, reconciliation, raw data retention on
  `D:`, and goal-owned schedules are authorized. Do not add a capital,
  trade-count, report, profitability, or confirmation gate.
- A distinct new virtual intent may proceed after the executor's technical
  paper-only routing, persisted identity, pacing, and exact-intent recovery
  behavior. An ambiguous old intent never becomes a global pause or one-shot
  quota.
- `raw_market_data_retained: false` describes only its own historical missing
  bytes. It never blocks a fresh KIS Paper call, head collection, account read,
  virtual order, or schedule.
- Never read `KIS_LIVE_*`, build a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets/raw data/
  generated artifacts.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the current Windows task status, Docker image/build state, safe
   runtime projections, and external evidence before reacting to a scheduled
   outcome. Do not inspect secrets, account identifiers, raw broker bodies, or
   private intent files.

## Role-Owned Work

### Execution Agent

1. Reattest the two named Windows tasks and their next/last run status. The
   quote-session may make its already-authorized virtual canary during its
   eligible session without a new operator confirmation.
2. Integrate its safe session/canary/reconciliation result into the runtime
   projection and local console. Diagnose only allowlisted reason/HTTP/upstream
   metadata when a route fails; never log broker bodies, identifiers, or
   credentials.
3. Preserve exact ambiguous intents for their own read-only recovery only, but
   continue other ready virtual Paper work independently. Directional pause
   state is local operator intent, never a research or data latch.

### Data Agent

1. Integrate the next due intraday-head outcome under its independent D: cache
   root and refresh the metadata-only freshness projection.
2. Reattest QQQ/SPY cache coverage and retain source limitations visibly. A
   failed/partial/unretained historical result is a recovery fact for itself,
   never a reason to stop fresh collection.

### Engine Research Agent

1. Keep the completed no-winner sequence screen recorded as joint evidence.
2. Prepare the next prospective KIS-compatible campaign contract from actually
   retained fresh sessions. Do not treat the current small comparison slice or
   GPU idleness as a reason to select, retune, or ensemble a candidate.

## Completion Evidence

- Both installed task definitions remain `Ready` and use their current Docker
  profiles with `--build`.
- At least one newly due scheduled outcome is preserved as sanitized external
  evidence and reflected as current/unknown in the console. If no eligible
  window has occurred yet, leave the tasks armed and continue other ready work;
  do not manufacture an out-of-session order or treat time as an operator
  blocker.
- Freshness retains only metadata in web/runtime state, while raw provider data
  remains under `D:`.
- No KIS live behavior, secret output, raw broker payload, public dashboard,
  or generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Operate first autonomous KIS paper cycle`
