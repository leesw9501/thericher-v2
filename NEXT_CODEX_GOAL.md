# Next Codex Goal

## Objective

Build the first point-in-time KIS-native daily SPY decision source for virtual
paper operation.

Use the existing private KIS daily cache and the proven SPY `AMS` quote / `AMEX`
order mapping. The outcome is a daily `enter` or `abstain` receipt whose input
availability, symbol/venue, and one-submit identity can be checked before it
reaches the existing virtual-paper canary. This is a narrow SPY lane, not a
new universe, model registry, report system, or live-trading feature.

## Standing Authority

- All private `KIS_PAPER_*` data/account reads, virtual submit/modify/cancel,
  reconciliation, sizing, retention on `D:`, and goal-owned schedules are
  authorized. Default to the next correctly scoped action; do not ask for a
  paper capital, profitability, trade-count, report, or per-call approval.
- Never read `KIS_LIVE_*`, create a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets, raw
  market/broker data, or generated artifacts.
- An unavailable input, failed collection, historical marker, prior canary,
  or unqualified result is scoped evidence only. It may produce a no-intent
  result or fresh collection; it must not freeze another ready lane.
- `raw_market_data_retained: false`, a one-shot completion, a blank response,
  or a `safe_to_submit` value is never an approval state. All non-live private
  KIS Paper data and virtual-order work remains authorized; preserve only the
  exact-intent reconciliation and paper-host technical boundaries.
- Retain technical truth only: point-in-time availability, paper-host routing,
  durable intent before a side effect, exact-intent reconciliation, final
  tick-valid price proof, and idempotent submit identity. These are not manual
  approval gates.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only sanitized cache, schedule, runtime, and artifact metadata
   before choosing the daily source. Do not output secrets, account identifiers,
   raw prices, raw broker bodies, or raw order IDs.
5. Ask Claude for a concise falsification-first check before relying on the
   daily point-in-time contract or an eligible daily receipt.

## Role-Owned Work

### Data Agent

1. Reattest the usable SPY KIS daily cache and define a minimal daily input
   manifest that binds provider, symbol, KIS data venue, cadence, source
   adjustment semantics, last consumed session, and the first instant that bar
   was available to a decision.
2. Keep collection independent: stale/missing daily data should request the
   next due KIS cache action or yield a scoped unavailable receipt, never a
   Paper or scheduler hold.

### Engine Research Agent

1. Add one transparent SPY daily baseline that consumes only sessions available
   before its declared decision time. It may emit `enter` or `abstain`; do not
   reuse the retired L2 gate, tune against a later suffix, select a model, or
   claim profitability.
2. Produce an immutable receipt whose input manifest is verified against the
   daily decision's symbol, venue, cadence, availability time, and source hash.
   A same-session close at or before its availability instant must not yield an
   eligible `enter`.
3. Replay eligible synthetic/retained daily decisions through `local_paper`
   with the full receipt identity, preserving `source: local_paper`.

### Execution Agent

1. Bind only an eligible SPY daily receipt to `SPY` / `AMEX`, a one-share
   execution binding, and an independently observed fresh `AMS` final-limit
   proof. Never use a daily close as the execution price proof.
2. Add durable one-submit-per-receipt behavior at the virtual-paper boundary.
   A repeat may reconstruct/reconcile the exact intent but must not submit a
   second virtual order.
3. When an eligible receipt, fresh independent price proof, and an eligible
   paper session coincide, virtual submit/cancel/reconciliation is authorized.
   Otherwise emit only a safe no-intent result and continue independent canary
   and data work.

### Validation Agent

1. Independently kill-test point-in-time leakage: a receipt using session T's
   close with a decision time no later than T's availability instant must not
   become eligible.
2. Prove a wrong symbol/venue/manifest, expired price proof, or repeated
   receipt cannot reach a second KIS Paper submission. Keep offline tests free
   of KIS transport, network, credential, and live access.

## Completion Evidence

- A hash-bound SPY daily input manifest has explicit availability semantics.
- A daily receipt is reproducible and either eligible from prior available data
  or honestly no-intent; no same-close lookahead is possible.
- An eligible receipt replays locally and has one durable virtual-paper submit
  identity tied to an independent price proof.
- A real virtual-paper submit/cancel/reconciliation is performed when its
  bounded inputs are eligible; otherwise its safe no-intent evidence explains
  why without pausing future authorized work.
- No live behavior, secrets, raw market/broker payload, public dashboard, or
  generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add point-in-time daily SPY paper decision`
