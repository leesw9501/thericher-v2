# Next Codex Goal

## Objective

Advance the existing KIS-compatible QQQ/SPY/IWM daily cache through one bounded
data-only catch-up run, and record its actual throughput and recovery state.

This is the next data foundation step after the frozen six-symbol CPU control.
It uses the existing resumable worker, one KIS Paper market-data client, and the
measured shared request-start gate to create longer source-separated history on
`D:`. It is not a stock-selection run, model campaign, account query, order,
or live action.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Inspect the existing private daily backfill index, source-safe manifests,
   Docker profile, request gate, and recovery path. Do not print raw rows,
   prices, credentials, account facts, or broker payloads.

## Required Work

1. Reconcile the existing `QQQ/NAS`, `SPY/AMS`, and `IWM/AMS` daily backfill
   cursor state from durable external evidence. Record only source-safe counts,
   cursor/date coverage, manifest identities, storage state, and recovery
   classification.
2. Confirm the catch-up path reuses one client/token per bounded invocation and
   applies the measured 1.0-second shared request-start gate. Keep the existing
   finite limit of at most 48 chunks or six hours. Do not introduce an arbitrary
   inter-chunk sleep, parallel request flood, or foreground wait while another
   lane is ready.
3. Run the existing data-only Docker catch-up profile once with
   `KIS_PAPER_APP_KEY` and `KIS_PAPER_APP_SECRET` available only inside its
   private container environment. Retain raw market bytes only under
   `D:\market_data`; retain source-safe run evidence under
   `D:\thericher-v2\model-artifacts` when needed.
4. If the run reaches a documented rate, auth, storage, cursor, or source
   boundary, preserve the exact scoped recovery fact and continue independent
   Research and Execution preparation. Change pacing only after measured output
   or official KIS evidence supports the change.
5. Keep the completed six-symbol CPU control descriptive. Do not retune it,
   rank symbols, train GPU depth models, create an ensemble, or derive a Paper
   decision from new cache rows in this objective.
6. Have temporary Validation verify that the catch-up client cannot reach
   account/order/live endpoints and that all retained data/artifacts stay
   outside Git. Update the Data, Engine Research, Execution, and orchestration
   stateboards with the new bounded facts only.

## Hard Boundaries

- KIS Paper market-data credentials and endpoint calls are authorized for this
  objective. Do not call account, position, order, cancel, modify, or any
  `KIS_LIVE_*` route or value.
- Do not output or persist secrets, account identifiers, raw response payloads,
  raw prices, or broker bodies outside their private D: cache.
- Keep the established single-client, shared-gate ownership. A rate/recovery
  fact constrains only its worker; it never becomes a global hold.
- Do not buy data, install a major runtime, expose a public service, or change
  a model/paper-trading decision from this collection result.

## Completion Evidence

- One bounded source-safe catch-up outcome with chunk counts, target states,
  cursor progress or an exact scoped recovery reason, and storage classification.
- Tests or focused probes proving client reuse, endpoint isolation, external
  artifact/cache containment, and correct no-wait recovery behavior.
- Stateboards that distinguish the extended-cache fact from the frozen
  six-symbol panel and name the next eligible research input without a model or
  profitability claim.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A bounded provider failure, local artifact issue, or
Claude OAuth fault does not stop independent ready work.
