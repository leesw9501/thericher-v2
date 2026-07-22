# Next Codex Goal

## Objective

Build a quote-derived KIS Paper canary and a small recurring regular-session
execution path. Keep private virtual-paper learning moving without one-shot,
per-call, capital-envelope, or per-goal approval latches.

The prior durable canary intents `canary-20260721T225034Z`,
`canary-20260721T232137Z`, and `canary-20260721T233837Z` remain immutable
recovery evidence. Do not reuse or mutate those exact intents. That restriction
prevents duplicate side effects for those intents only; it is never a quota or
block on a distinct new KIS Paper intent, due Paper schedule, Data work, or
Engine Research work.

All private `KIS_PAPER_*` credential reads, data/account/order calls,
submit/modify/cancel, routine sizing, raw-data retention, and recurring
goal-owned schedules are authorized. `KIS_LIVE_*`, live hosts/routes, and
real-money behavior remain forbidden. Do not print or commit secrets, account
identifiers, raw quote/broker bodies, private intent state, or raw order IDs.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and active
   stateboards in `agents/`.
3. Read before edits or an execution schedule:
   - `src/thericher_v2/execution/kis_paper_canary.py`
   - `src/thericher_v2/execution/kis_readonly.py`
   - `src/thericher_v2/execution/paper_canary_runtime.py`
   - `tests/test_kis_paper_canary.py`
   - `docker-compose.yml`
4. Recheck the official KIS sample for the virtual US buy route and overseas
   quote endpoint. Do not copy its credential/configuration layer.
5. Ask Claude for one concise falsification-first drift check before the first
   recurring scheduled submit path is enabled. State that quote data remains
   transient/private, Paper-only routing and cancellation behavior are unchanged,
   prior run IDs remain untouched, and an ambiguous intent is never resubmitted.
   Do not send credentials, account data, raw KIS output, private state, or
   order IDs.

## Required Work

### Execution Agent

1. Add one allowlisted virtual KIS quote request for `SPY` using the official
   overseas-price route, `HHDFS00000300`, `EXCD=NAS`, and `SYMB=SPY`. Parse only
   positive `last` and valid `zdiv`; keep quote values out of runtime, evidence,
   Git, and console output.
2. Derive an explicit whole-share buy-limit price from the transient quote with
   deterministic decimal rounding and a documented nonmarket discount. Persist
   only the existing private intent; public projections keep the price redacted.
   Invalid or unavailable quotes must create a safe no-submit outcome.
3. Add a narrowly owned recurring KIS Paper session worker or local automation,
   not a generic agent platform. It may create distinct fresh intents during
   eligible US regular sessions without operator approval. It must retain
   paper-only routing, source pacing, bounded concurrency, durable intent state,
   reconciliation for an ambiguous matching intent, and sanitized external
   evidence. Session/cadence behavior is an implementation choice, not a
   one-shot reservation or numerical trade quota.
4. Add focused tests for virtual-only quote validation, deterministic price
   rounding, raw-quote suppression, repeated due-session behavior, concurrency,
   and preservation/recovery of prior unknown intents. Keep the no-order-route
   recovery proof.
5. Run focused tests, Claude's check, and rebuild `kis-paper-canary`. Exercise
   the resulting due-session path when it becomes eligible. Do not artificially
   stop after one independent Paper run; continue within the worker's technical
   contract while the company objective remains active.
6. Record only phase, closed reason, optional validated KIS code, reconciliation
   counts/status, schedule outcome, and external artifact path. An ambiguous
   run is reconciled before replacement of that run; a later distinct intent may
   continue without an operator question.

### Data And Research

- Keep collection and eligible research work independent of the execution path.
- `raw_market_data_retained: false` is historical provenance only. It never
  suppresses a correctly scoped later collection. Preserve local simulation
  fills as `source: local_paper`.
- Replace stale "operator-approved GPU backend" diagnostics with factual
  compatible-backend availability diagnostics; PyTorch CUDA research remains
  authorized when an eligible campaign contract and compatible runtime exist.

## Completion Evidence

- Focused quote, rounding, safe-projection, recurring-session, and recovery
  regression proof.
- A verified recurring Paper job or automation recorded outside Git, plus its
  first due-session outcome when the market/session is eligible.
- No KIS Live access, raw quote/broker body, credential, account identifier, or
  raw order identifier in Git, logs, dashboard, or artifact.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add recurring quote-derived KIS paper canary`
