# Next Codex Goal

## Objective

Build the first narrow model-decision bridge from existing KIS-native `Bar`
research into a paper-ready decision receipt.

The goal is not to claim a profitable model or wait for a larger GPU dataset.
Use one fixed, transparent baseline to produce an explicit `enter` or `abstain`
receipt, replay that same receipt through `local_paper`, and make an eligible
receipt consumable by the existing virtual-paper intent boundary. The already
working independent KIS Paper canary and scheduled data collection continue in
parallel.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market/account reads, positions, open orders,
  virtual-order submit/modify/cancel, reconciliation, raw data retention on
  `D:`, and goal-owned schedules are authorized. A correctly scoped Paper
  action does not need a capital, trade-count, profitability, or per-call
  confirmation.
- Never read `KIS_LIVE_*`, create a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets, raw data,
  broker bodies, or generated artifacts.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- An old `raw_market_data_retained: false`, prior canary result, blank source
  field, failed collection, or unresolved intent applies only to its own
  evidence/recovery path. It never freezes a distinct KIS Paper action,
  scheduler, collection, or research lane.
- Preserve only technical truth: virtual-paper route isolation, durable intent
  before a side effect, no replacement of the exact unknown intent before
  reconciliation, point-in-time input identity, and final limit-tick validity.
  These are implementation properties, not operator approvals or numeric
  quotas.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only sanitized schedule/runtime state plus cache/artifact metadata
   before choosing an active input. Do not output credentials, account
   identifiers, raw prices, raw broker bodies, or raw order IDs.
5. Ask Claude for a concise falsification-first drift-check before relying on a
   new point-in-time model-to-Paper mapping or treating a result as more than a
   baseline/replay fact.

## Role-Owned Work

### Data Agent

1. Inventory the latest usable KIS-native daily and intraday cache coverage for
   `QQQ`, `SPY`, and `IWM` with metadata-first inspection. Identify which
   existing stream can support one current fixed baseline receipt without
   source mixing.
2. Keep prospective intraday-head collection and the daily cache independent.
   A missing/stale window yields a visible input status for that receipt, not a
   global collection, Paper, or research hold.

### Engine Research Agent

1. Select one already-defined fixed baseline whose source, timing, and limits
   are explicit. Do not reuse the retired L2 gate, tune against the burned
   historical suffix, select an architecture, form an ensemble, or start GPU
   depth work from the small historical comparison slice.
2. Define a small immutable decision receipt with opaque campaign/model/input
   references, `enter`/`abstain`, validity, and reason class. It must not carry
   raw feature vectors, scores, prices, quantities, account values, or broker
   fields.
3. Replay it through the existing local-paper harness and link its decision ID
   to the corresponding local-paper attribution without confusing
   `source: local_paper` with `kis_paper`.

### Execution Agent

1. Add the smallest adapter from an eligible research receipt to the existing
   KIS Paper decision/intent contract. Execution retains final price, tick,
   sizing, persistence, route, reconciliation, and cancellation ownership.
2. A receipt with `abstain`, stale/unavailable input, unsupported symbol/venue,
   or no current price contract must emit a safe no-intent result for that
   receipt. It must not pause the independent canary or force an entry.
3. If a distinct eligible receipt reaches the existing Paper executor during an
   eligible session, virtual submission/cancellation is authorized. Otherwise
   validate the adapter offline with fake transport and local-paper replay; do
   not create a new approval step.
4. Extend the sanitized lifecycle fact only if needed to distinguish model,
   timing, sizing, and execution causes without exposing raw broker data.

### Validation Agent

1. Independently verify that the selected receipt has no future-bar or
   cross-provider dependency, that the local replay remains deterministic, and
   that a Paper adapter cannot reach live/network/credential code in offline
   tests.

## Completion Evidence

- One immutable baseline receipt is reproducible from an identified KIS-native
  input or honestly reports its current unavailable/stale status.
- The same receipt is replayable through `local_paper`, preserving
  `source: local_paper` and an attribution link.
- The execution adapter accepts only eligible `enter` receipts and produces
  only a sanitized no-intent fact for every other state.
- Existing independent KIS Paper canary, data schedules, and broad/depth
  research queues continue without a new approval, quota, or global pause.
- No KIS live behavior, secret output, raw data/broker payload, public
  dashboard, or generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Bridge baseline decisions to paper intents`
