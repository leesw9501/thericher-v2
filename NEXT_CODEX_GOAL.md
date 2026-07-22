# Next Codex Goal

## Objective

Resolve the first KIS Paper canary submit-result compatibility fact while
continuing the already-authorized independent virtual-paper cycle.

The execution price input is now proven for the exact SPY AMEX path. The next
small target is to classify the KIS virtual buy-limit acknowledgement and its
read-only reconciliation truthfully, then make the resulting per-intent outcome
available to PnL attribution without storing a raw broker response or creating
an approval gate.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market/account reads, positions, open orders,
  virtual-order submit/modify/cancel, reconciliation, raw data retention on
  `D:`, and goal-owned schedules are authorized. Distinct Paper intents and
  routine schedules do not require a capital, trade-count, profitability, or
  confirmation gate.
- Never read `KIS_LIVE_*`, build a live route, use real capital, buy data,
  accept unclear rights, expose a public service, or commit secrets, raw data,
  broker bodies, or generated artifacts.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- An old `raw_market_data_retained: false`, blank probe, failed submission, or
  unresolved intent applies only to that concrete evidence/recovery path. It
  never stops another correctly scoped KIS Paper action, schedule, data job,
  research job, or distinct virtual intent.
- Preserve actual technical truth: virtual-paper routing, durable intent before
  a side effect, no duplicate replacement after an unknown result, and
  reconciliation evidence. These are implementation properties, not operator
  approvals or numeric quotas.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect only sanitized scheduled-task state, console projections, external
   evidence metadata, and cache metadata. Do not output credentials, account
   identifiers, raw order IDs, raw broker bodies, or raw quote values.
5. Ask Claude for a concise falsification-first drift-check before relying on a
   newly discovered submit-response variant or changing reconciliation semantics.

## Role-Owned Work

### Execution Agent

1. Add the smallest category-only submit-response diagnostic or parser needed
   to distinguish documented acknowledgement fields, a KIS rejection, a
   malformed success response, and an unavailable transport. Do not retain raw
   bodies, prices, account data, or order identifiers.
2. Keep the current `AMS` price endpoint / `AMEX` order mapping, virtual host,
   explicit-limit/tick contract, durable identity, pacing, and independent
   Paper schedule intact. A new due Paper session may proceed automatically.
3. Project a sanitized per-intent lifecycle fact suitable for later PnL
   attribution: intent status, reconciliation class, safe result category, and
   replay/evidence identity. It must not become a capital, model, or manual
   approval control.
4. Keep unknown-run recovery read-only. A distinct correct Paper intent remains
   allowed while that exact intent is reconciled.

### Data Agent

1. Keep the prospective KIS intraday head cache collecting under its independent
   root, and run the metadata-only observation preparer after each scheduled
   outcome.
2. Keep execution-price provenance separate from raw market-data cache bytes;
   record only non-secret source/venue/freshness compatibility facts needed by
   the execution adapter.

### Engine Research Agent

1. Keep the fixed no-winner KIS intraday screen unchanged. Continue only ready
   prospective-preparation work; do not retune, select, ensemble, or start a
   GPU depth run from the small historical comparison slice.
2. Define the minimal consumer contract for the new per-intent lifecycle fact
   so later PnL attribution can distinguish model/timing/sizing/execution
   causes without owning broker code.

## Completion Evidence

- The actual KIS submit-response shape is safely classified or explicitly
  rejected with a narrow category; no raw response is stored.
- At least one replayable sanitized per-intent outcome reaches the execution
  attribution boundary, and existing local-paper replay behavior remains
  unchanged.
- The current KIS Paper schedule and independent data/research preparation
  continue without a new approval, quota, or global pause.
- No KIS live behavior, secret output, raw broker payload, public dashboard, or
  generated artifact enters Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Classify KIS paper canary outcomes`
