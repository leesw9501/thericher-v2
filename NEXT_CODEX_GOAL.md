# Next Codex Goal

## Objective

Build the first minimal local KIS Paper operations console while KIS Paper data
collection, the quote-session canary, and Engine Research continue independently.

The console gives the operator a local view of the current paper account/runtime
state and durable buy/sell pause controls. It is an execution-learning tool, not
a public dashboard, research gate, or substitute for broker reconciliation.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market, account, position, open-order, order,
  modify, cancel, reconciliation, raw-retention, and goal-owned schedule work
  is authorized. Do not add a capital, trade-count, report, profitability, or
  manual-confirmation gate.
- `raw_market_data_retained: false` is a factual result for its own missing
  bytes. It never blocks a fresh KIS Paper collection, account call, distinct
  virtual intent, or schedule.
- The console may expose only sanitized local paper facts and must never read,
  receive, render, log, or persist credentials, account identifiers, raw quote
  values, broker bodies, or private intent state.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`, never Git.
- Do not read `KIS_LIVE_*`, construct a live route, use real capital, buy data,
  accept unclear rights, or expose a public service.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the current web/runtime, Paper canary, emergency-control, and
   sanitized account-snapshot contracts before changing them.
5. Ask Claude for one concise falsification-first drift review before adding
   console control paths. Do not send secrets, account identifiers, raw broker
   responses, or private recovery state.

## Role-Owned Work

### Execution Agent

1. Reuse the existing local web/runtime patterns where possible to show the
   current paper mode, snapshot freshness, position/open-order counts, buying
   power availability, latest canary/recovery status, and latest local-paper
   attribution facts. Missing or stale runtime evidence must display as
   `unknown`, never as zero.
2. Add durable local controls for `pause_buys` and `pause_sells`, plus the
   existing emergency stop/cancel semantics when already supported. Controls
   write a narrow local control state consumed by the executor; they do not
   directly call KIS or submit an order from the web process.
3. Bind the console to local/private use only. Keep KIS credentials and private
   recovery state out of the web container and response payloads. A due
   `kis-paper-session` may continue its authorized virtual canary independently;
   reconcile an exact ambiguous intent before its own replacement only.

### Data Agent

1. Reattest QQQ/SPY intraday cache and inspect the first due head outcome when
   available. Continue bounded authorized collection; an old unretained marker
   is not a stop condition.
2. Record current cache/snapshot freshness through a sanitized projection that
   does not expose raw bars or quote values.

### Engine Research Agent

1. Record the completed fixed LSTM/TCN/attention screen as jointly reported,
   no-winner evidence. Do not retune, select, or ensemble from its five
   comparison sessions.
2. Keep breadth, depth, ensemble, and replication queues current while the GPU
   stays idle until a new frozen prospective KIS data contract makes another
   experiment eligible.

## Completion Evidence

- A local-only Docker-operable console with sanitized current/unknown states and
  durable pause controls.
- Focused tests proving the web process has no KIS credential, broker-submit,
  live-route, raw-data, or private-intent access.
- Browser or HTTP evidence that controls persist and are reflected without
  performing a broker side effect.
- Current scheduler/cache facts integrated when due; not-yet-due work is not a
  blocker.
- No secrets, raw data, generated artifacts, or live behavior in Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add local KIS paper operations console`
