# Next Codex Goal

## Objective

Build `kis-paper-m1-previous-day-scope-probe-v1`.

Measure the exact provider-observed effect of an explicit previous-day initial
M1 request for QQQ/NAS and SPY/AMS, including only any continuation the named
KIS Paper endpoint itself admits. This is a bounded reach and pacing measurement
for a later collector decision; it does not claim complete history, data
qualification, point-in-time safety, decision-time availability, prediction,
profitability, or Paper readiness.

## Hard Boundaries

- `KIS_PAPER_*` may be read only through the named Paper market-data path.
  Never print or persist credentials; never read or route `KIS_LIVE_*`.
- Do not call account, position, quote, order, cancellation, or any live route.
- Do not alter or duplicate the existing QQQ/SPY scheduled collector, its
  cache, cursor, terminal chain, Docker service, or schedule. Use a
  target-isolated external capability root while retaining the existing shared
  evidence-backed request and token gates.
- The first actual probe may make at most two serial minute-page requests per
  target through one reusable client. Its first page must set explicit
  previous-day scope; request a second page only after a recognized provider
  continuation, with no continuation flood or foreground retry. A categorical
  retry fact yields only its target-scoped source-safe `next_due`.
- Retain accepted raw pages only below `D:\market_data`; keep source-safe
  receipts under `D:\thericher-v2\model-artifacts`; never commit either.
- Do not create a recurring scheduler, broad backfill, model, research
  campaign, GPU job, dataset qualification, local-Paper intent, broker order,
  public service, or mutable latest-record rule.

## Required Work

1. Run a concise Throughput Review. Confirm that the completed current-day
   blank-cursor probe was terminal for both targets and that it leaves explicit
   previous-day scope unmeasured.
2. Ask Claude CLI for a short falsification-first drift check before changing
   request scope or interpreting continuation. Send no raw rows, values, paths,
   or credentials; do not wait for the result.
3. Inspect the completed current-day probe package and any visible generic
   minute WIP before relying on it. Reattest or extend only the bounded
   previous-day variant; unowned provenance alone is never a block.
4. Freeze the exact request scope, target order, page budget, cursor rule,
   raw-retention rule, target-isolated root, pacing fields, categorical recovery
   outcomes, and strongest target/cursor/duplicate kill test.
5. Implement or reattest the smallest testable prior-day variant. Add focused
   fake/local tests for explicit scope enforcement, serial page budget,
   continuation and target handling, external-root/link rejection, no
   credential/network path without `--execute`, and source-safe output.
6. Run a CPU-only fake/local smoke. Then make the bounded KIS Paper attempts
   and retain only permitted external data. Reattach source-safe receipts; do
   not infer provider-wide history from a terminal or source-limited result.
7. Refresh Data and orchestration stateboards with per-target scope, accepted
   pages, categorical failures, elapsed-time bucket, remaining scope as
   `unknown` when appropriate, and the next collection or recovery action.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Probe KIS Paper M1 previous-day scope`
