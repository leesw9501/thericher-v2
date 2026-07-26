# Next Codex Goal

## Objective

Calibrate and accelerate private KIS Paper market-data ingress.

Establish the maximum reliable, source-correct pace for the existing KIS Paper
daily and intraday collectors, then use the resulting evidence to make finite
progress on a ready cursor. This advances data collection for the trading
engine. It is not a broker-order, account-management, model-promotion, or live
behavior objective.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, DECISIONS.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Inspect current daily and intraday catalog/index metadata and the shared
   timing state. Do not scan raw market files ad hoc or print raw rows.

## Required Work

1. Ask Claude CLI for a concise falsification-first review before changing a
   persistent KIS request pace, collector concurrency, or schedule. State the
   present `EGW00201` evidence, current request/cooldown/token controls, the
   one-client measurement plan, stop condition, and the fact that would retain
   or replace a setting. An expired CLI session is scoped tooling evidence, not
   a hold on private non-live Data work.
2. Inventory the ready KIS Paper daily and intraday cursors from their
   manifests/indexes and identify the active backlog in source-safe terms. Keep
   raw data under `D:\market_data`; do not output rows, credentials, or account
   facts.
3. Review the existing test-backed, data-only bounded calibration path and its
   latest source-safe result before adding another probe. The QQQ 1.0-second
   candidate accepted two full terminal-head pages through one in-memory client
   and token with zero categorical errors. It is not a route-wide ceiling or a
   historical-continuation claim.
4. Before adopting the clean 1.0-second candidate, inventory and align every
   effective pacing layer: shared gate, client, collector, and scheduler. Change
   only the supported end-to-end setting and add focused tests that prove a
   longer local delay cannot silently defeat it. Retain the 60-second
   `429`/`EGW00201` cooldown. The five-minute cross-process token-start guard
   applies only to a new token request: it must not turn into a five-minute
   foreground sleep or block an existing in-memory client.
5. If the aligned bounded setting is clean and a cursor is ready, run the existing
   finite daily catch-up or intraday session-capture worker using the proven
   setting. Retain collected raw market data, manifests, provenance, and
   recovery state only under `D:\market_data`. A rate limit, invalid page, or
   source limit stops only that worker and produces a recoverable scoped fact.
6. Keep Engine Research and Execution moving on their independent ready queues.
   Do not turn the data calibration into a model-selection, ensemble,
   profitability, KIS-order, or account-read prerequisite.
7. Add focused tests for calibration bounds, single-client/single-collector
   behavior, token-start versus request-start timing, sanitized evidence,
   rate-limit recovery, and unchanged local/kis/live route separation.

## Hard Boundaries

- Use `KIS_PAPER_*` only through the owned Paper market-data path. Do not call
  account, position, order, cancel, or modify endpoints in this goal.
- Never read or route `KIS_LIVE_*`; do not enable live behavior.
- Do not print, log, commit, or send credentials, account identifiers, raw
  provider payloads, raw prices, or sealed holdout labels to Claude.
- Keep data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- Do not use an unbounded retry loop, a parallel request flood, a second active
  collector against the same cache, or a scheduler that outruns a measured
  source constraint.

## Completion Evidence

- A test-backed bounded calibration path with only source-safe evidence and no
  secret, account, order, or live surface.
- An effective, recorded measured pace or a precise recoverable reason it cannot
  yet be changed, including the fact that will recalibrate it. A lower shared
  gate alone is insufficient when another pacing layer remains longer.
- When a ready cursor exists, one finite collector run that preserves the
  existing cache/provenance/recovery contract under `D:`.
- Updated role stateboards showing current Data evidence and independent lane
  readiness without a global wait.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A KIS cooldown, token deferral, source limit, GPU
fault, or lane-local test failure does not stop another ready lane.
