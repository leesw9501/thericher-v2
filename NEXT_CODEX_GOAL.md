# Next Codex Goal

## Objective

Build the first receipt-linked KIS Paper SPY position lifecycle: a bounded
daily entry/exit path with deterministic sizing, reconciliation, and sanitized
PnL attribution.

The completed daily SPY head/receipt path remains the only decision source for
this objective. Turn its current cancellation-oriented canary into a minimal
replayable Paper position loop without adding a universe, report system, live
route, or model-selection program.

## Standing Authority

- All private `KIS_PAPER_*` market/account reads, virtual submit/modify/cancel,
  reconciliation, sizing, data retention on `D:`, and goal-owned schedules are
  authorized. Default to the next correctly scoped action.
- Do not read `KIS_LIVE_*`, create a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets, raw
  market/broker data, or generated artifacts.
- A stale receipt, missing head, blank quote, cancellation, unfilled order, or
  prior unknown intent is scoped evidence only. It must not block a distinct
  correctly scoped Paper action or another ready lane.
- Preserve technical truth only: virtual-host routing, durable identity before
  every side effect, exact-intent reconciliation, position/account facts from
  KIS rather than local inference, and safe redaction. These are not manual
  approval gates.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only sanitized schedule, cache, artifact, runtime, and account
   metadata before selecting the first position action.
5. Ask Claude for a concise falsification-first check before relying on a new
   sell-side Paper route, position reconstruction rule, or realized-PnL claim.

## Role-Owned Work

### Data Agent

1. Keep the daily SPY head collection resumable and separate from historical
   cache work. Reattest only one complete source per receipt and retain its
   point-in-time availability semantics.
2. Publish only safe freshness/coverage facts needed by the position session;
   never expose raw prices or provider rows to the dashboard or Git.

### Engine Research Agent

1. Extend the fixed daily baseline into an explicit target-position proposal:
   `enter`, `hold`, `reduce`, `exit`, or `abstain` must have deterministic
   input/status semantics. Do not tune parameters against the burned historical
   suffix or claim a return result.
2. Keep local-paper replay and receipt identity exact for each target-state
   transition. Define the evidence needed to distinguish model, timing, sizing,
   and execution causes in later PnL attribution.

### Execution Agent

1. Add a narrow virtual-paper sell-side adapter for the fixed `SPY` / `AMEX`
   route only after an eligible receipt and fresh independent price proof. It
   must persist a separate durable identity and reconcile its exact outcome.
2. Implement a minimal bounded position session that reads sanitized KIS Paper
   account/open-order facts, applies deterministic one-share target deltas, and
   does not submit a duplicate entry or exit for the same receipt.
3. Publish a replayable sanitized lifecycle/PnL attribution fact. It may state
   `pending`, `cancelled`, `unfilled`, or `unavailable`; it must not invent a
   fill, cash value, realized PnL, or local-paper source for KIS evidence.
4. Update the scheduled daily session only after the offline tests and direct
   Docker exercise show that entry and exit routes remain virtual-only and
   idempotent.

### Validation Agent

1. Independently prove that a receipt cannot cause both an entry and an exit,
   a changed quote cannot replace a durable order, and a stale account snapshot
   cannot fabricate a position/PnL conclusion.
2. Prove offline tests need no broker, network, credential, or live access,
   while synthetic lifecycle facts remain replayable and safely redacted.

## Completion Evidence

- A complete daily receipt can deterministically express a target state and
  replay it through `local_paper`.
- Each virtual SPY entry/exit action is receipt-linked, idempotent, and
  reconciled from KIS Paper facts.
- A safe lifecycle attribution record distinguishes no-intent, open, cancelled,
  unfilled, unknown, and reconciled states without leaking data or secrets.
- The scheduled session remains private KIS Paper only; no live code/path,
  public dashboard action, raw data, or generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add receipt-linked paper position lifecycle`
