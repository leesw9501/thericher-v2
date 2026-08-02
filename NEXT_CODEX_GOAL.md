# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, and the active stateboards in `agents/` first.
Then continue from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `fresh-paper-baseline-loop-v1`: exercise one narrow, fresh-input engine
loop from the existing prospective SPY baseline through the deterministic KIS
virtual-paper boundary. It is forward execution-learning evidence, not a
profitability claim or a replacement for later model research.

## Boundaries

- `KIS_PAPER_*` private market/account/quote/order/reconciliation use is
  authorized. Never read or route `KIS_LIVE_*`; never enable live behavior.
- Keep the global `THERICHER_MODE` unchanged unless the existing explicitly
  virtual-paper service already requires a scoped override.
- Reuse existing capture, baseline, intent, reconciliation, schedule, and
  credential-free dashboard paths. Do not add a scheduler, workflow, dashboard,
  generic canary route, approval gate, or report family.
- Do not reopen the repeatedly screened static QQQ/SPY panel for historical
  PnL, selection, ensemble, training, or GPU work.
- Keep secrets, account identifiers, raw broker bodies, quotes, and raw rows
  out of output, Git, artifacts, and Claude. Store data on `D:` and artifacts
  outside Git as defined in `AGENTS.md`.
- Broker-free replay fills remain `source: local_paper`; KIS virtual facts must
  remain distinctly `kis_paper` and never be mislabeled as local fills.

## Required Work

1. **Data:** Reattest the prospective SPY capture/input boundary and verify its
   existing owned fresh-session schedule emits a scoped result for missing,
   stale, or incomplete input without mutating historical cache data.
2. **Engine:** Reuse the unchanged `prospective-spy-intraday-baseline-v1` only
   at its fixed causal decision boundary. Bind decision to fresh source/feature
   identity; stale, missing, or abstain evidence must create no Paper intent.
   Run an injected local-paper replay regression when the existing fixture
   permits it. Do not fit, tune, score, compare, or create a model artifact.
3. **Execution:** Reattest the existing virtual host, account-read, fresh-quote,
   durable-intent, cancel, and reconciliation route. Run one bounded read-only
   KIS Paper health observation now when runnable. When a new fresh `enter`
   receipt exists, let the existing owned route make its smallest one-share
   virtual canary and reconcile/cancel it. Never manufacture an order for
   transport testing.
4. **Validation:** Add focused tests for route isolation, fresh binding,
   stale/missing/abstain no-intent behavior, source-safe runtime projection, and
   local-paper versus KIS-paper fact separation. Unit tests need no real KIS,
   network, credential, raw data, or broker order.

Ask Claude for a concise falsification-first check before relying on a material
route, recovery, or schedule-side-effect change. A market-time due belongs to
its owner; it never holds another ready lane.

## Completion Evidence

- focused tests pass and virtual/non-live isolation is reattested;
- one source-safe current read-only KIS Paper health result, or its exact
  technical failure, is recorded;
- the owned fresh-session path is verified without a foreground market wait;
- any virtual canary result uses its existing durable identity and reconciliation.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

Commit and push, replace this file with exactly one next objective, then
continue without waiting for a market session.
