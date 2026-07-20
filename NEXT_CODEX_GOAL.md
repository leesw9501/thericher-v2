# Next Codex Goal

## Objective

Capture one bounded KIS virtual-paper **market-data capability observation**
for the already declared `QQQ` / `NAS` raw-`1m` path during a verified U.S.
regular market session. This advances the data-collection and paper-trading
readiness loops by testing whether the future 90-bar local baseline can ever
be supplied from KIS-compatible inputs. It is not an account-bridge retry.

## Required Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `ARCHITECTURE.md`, `agents/data.md`, and `agents/execution.md`.
3. Read the current one-shot KIS minute capability and qualification code and
   its focused tests before changing anything.
4. Ask Claude for one short falsification-first drift check before the external
   observation. Do not share credentials, account identifiers, raw response
   bodies, or row-level price data.

## Work Packages

### Execution Agent: One External Observation

- Confirm the U.S. regular session is currently open for the declared NASDAQ
  window before OAuth or a market-data request. If it is not, make no KIS call;
  record no failure as a broker/data fact and refresh this goal for the next
  verified session.
- Use only the operator-authorized `KIS_PAPER_*` values in the isolated typed
  KIS capability path. Do not read `KIS_LIVE_*`.
- Make at most the predeclared first-page plus one continuation observation for
  `QQQ` / `NAS` raw `1m`; no symbol expansion, pagination loop, retry, or
  historical backfill.
- Persist only sanitized typed evidence needed to establish request outcome,
  page counts, timestamp bounds, field-presence booleans, continuation shape,
  and no-overlap adjacency. Do not retain or print raw bars, prices, volumes,
  tokens, account identifiers, or broker payloads.

### Data Agent: Interpretation Only

- Review the sanitized evidence for timestamp-label ambiguity, page adjacency,
  completed-bar semantics, freshness, and persistent-storage rights.
- Classify it only as `observed`, `rejected`, or `unavailable`. Do not create a
  `Bar`, cache, dataset, model input, campaign input, or qualified capability.
- State exactly which independently falsifiable fact would be needed before
  `1m`, `5m`, `10m`, `1h`, or `3h` can enter the active paper graph.

## Hard Boundaries

- Keep `THERICHER_MODE=off`.
- No KIS account, balance, position, orderability, open-order, submit, modify,
  cancel, or live endpoint call. This goal is intentionally different from the
  terminal `balance_rejected` account bridge result.
- No paper capital proposal, capital envelope, order canary, local/live broker
  order, public service, GPU run, model training, or data promotion.
- Do not download or persist raw market data in the Git workspace. Any external
  evidence belongs under `D:\thericher-v2\model-artifacts`, not Git.
- A rejected or unavailable result ends this objective. Do not retry it.

## Completion Evidence

- One of `observed`, `rejected`, `unavailable`, or no-call/session-closed,
  with an external sanitized evidence path and SHA-256 when a call occurred.
- Focused tests showing no broker/order, live credential, raw-payload, or
  model-promotion path was added.
- Updated Data and Execution stateboards, `HANDOFF.md`, and this next goal.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Observe bounded KIS minute capability`
