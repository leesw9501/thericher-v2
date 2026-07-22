# Next Codex Goal

## Objective

Run the first fixed multi-architecture KIS intraday sequence screen while the
installed KIS Paper quote-session and intraday-head jobs continue independently.

This extends the frozen QQQ 20-session input with LSTM, TCN, and compact
attention evidence beside the completed GRU smoke. It is descriptive research
and runtime integration, not model selection, a profitability claim, or a
reason to pause KIS Paper work.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` data, account, order, modify, cancel,
  reconciliation, raw-retention, and goal-owned schedule work is authorized.
- `raw_market_data_retained: false` describes only an old missing snapshot; it
  never blocks a fresh correctly scoped collection, schedule, account query, or
  virtual order.
- Keep raw data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`, never Git.
- Do not output credentials, account identifiers, raw quote/broker bodies, or
  private intent state.
- Do not read `KIS_LIVE_*`, call a live host/route, use real capital, buy data,
  accept unclear rights, or expose a public service.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the frozen CPU/CUDA summaries, KIS intraday indexes, and scheduled
   task state before changing a contract or interpreting an outcome.
5. Ask Claude for one concise falsification-first review before implementing
   the multi-architecture comparison. Do not send secrets, raw rows, broker
   output, or a claimed best model.

## Role-Owned Work

### Data Agent

1. Reattest the QQQ/SPY intraday cache and inspect the next due head outcome.
   Continue bounded KIS collection whenever it is due; an old unretained marker
   is not a stop condition.
2. Preserve the current QQQ 20-session input unchanged for this screen. Record
   any new complete session as prospective data for a later contract.

### Engine Research Agent

1. Build one small common PyTorch sequence harness using the existing 90x3
   development-only input. Fix LSTM, causal TCN, and compact-attention model
   shapes, seeds, epochs, costs, and decision threshold before running.
2. Train each model on the 10 development sessions in the network-disabled
   Docker research profile, then replay its fixed outputs on the 5 comparison
   sessions through `source: local_paper`. Keep the final four sessions
   untouched. Do not tune, select, promote, or ensemble from those results.
3. Write replayable sanitized artifacts outside Git and refresh breadth, depth,
   ensemble, and replication queues. Ensemble work still requires independent
   out-of-fold predictions.

### Execution Agent

1. Keep both installed Windows tasks enabled and inspect their first due
   results. A due Paper session may submit/cancel within its existing virtual
   canary behavior; reconcile any exact ambiguous intent before retrying it.
2. Fix only concrete virtual-route, calendar, pacing, reconciliation, or safe
   projection defects. Do not add a live route or make strategy decisions.

## Completion Evidence

- External artifacts for the fixed LSTM, TCN, and compact-attention runs, or a
  precise reproducible runtime cause for each unavailable backend.
- Local-paper replay evidence for every completed comparison run, with no
  model-selection or Paper-authorization claim.
- Fresh KIS cache/head and quote-session recovery facts when their schedules
  have run; a not-yet-due task is not a blocker.
- No secrets, raw data, generated artifacts, or live behavior in Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add intraday sequence architecture screen`
