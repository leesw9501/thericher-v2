# Next Codex Goal

## Objective

Turn the first fresh QQQ Paper cycle's exact `account_unavailable` no-intent
into a recoverable, source-safe virtual-account diagnostic. Establish whether
the existing KIS Paper read-only path is currently available, configuration-
limited, or route-limited without reusing the completed QQQ receipt, submitting
an order, or reading any live credential.

This is execution observability, not a broker retry, model promotion,
profitability validation, capital allocation, or live enablement.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
   `RUNBOOK.md`, and all active stateboards.
3. Reattach the completed fresh QQQ schedule receipt, virtual session
   no-intent, and matching offline validator. Do not print account data,
   identifiers, secrets, request bodies, or raw market rows.
4. Retry Claude only before relying on a material execution-route/recovery
   change or interpreting an unexpected account result. An OAuth failure is
   `review_unavailable`, not a hold on safe private work.

## Work

1. **Execution:** run the existing virtual-only read-only bridge once through
   its named Docker path. Record only the allowlisted source-safe availability
   category and redacted recovery evidence. Do not submit, modify, cancel, or
   reconcile an order.
2. **Execution:** if the read-only bridge remains unavailable, trace the exact
   no-order code path with fakes and a source-safe diagnostic. Distinguish
   malformed local configuration, virtual-host/routing rejection, missing
   required account fields, and transient provider response without logging any
   secret or account identifier. Make the smallest reversible fix that improves
   the named virtual read loop.
3. **Validation:** add focused tests proving the diagnostic remains KIS Paper
   host-pinned, read-only, credential-redacting, order-free, and external-
   artifact-only. A diagnostic must never be consumed as a model result, sizing
   input, paper-intent permission, or live route.
4. **Data:** let the installed prospective intraday scheduler continue to own
   its due times. Reattach any later terminal receipt as a new observation, but
   do not wait for it, reuse the completed `account_unavailable` receipt, or
   restart its absent canary.
5. **Engine Research:** keep the falsified daily linear/sequence/tree evidence
   closed. Do not occupy the GPU without a separately frozen causal hypothesis
   and a valid input contract.

## Boundaries

- `KIS_PAPER_*` account reads are authorized. Never read or route
  `KIS_LIVE_*`, enable live behavior, or expose a public service.
- Do not place, modify, cancel, or reconcile a broker order in this objective.
- Keep market data under `D:\market_data` and generated diagnostics under
  `D:\thericher-v2\model-artifacts`; never commit either.
- A provider/account failure closes only the diagnosed read path. It does not
  create an approval gate or stop independent Data and Research work.

## Completion

- One fresh source-safe read-only bridge outcome is persisted outside Git.
- The first fresh QQQ no-intent is linked as historical evidence and is not
  replayed into a broker action.
- Any unavailable outcome has a precise recovery class and focused no-order
  test coverage; any available outcome remains read-only evidence.
- Stateboards, handoff, and decisions distinguish account-read health from
  model quality, order authority, and live behavior.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Diagnose KIS Paper account availability`
