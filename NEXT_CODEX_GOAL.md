# Next Codex Goal

## Objective

Build `kis-paper-m1-historical-reach-probe-v1`.

Resolve the exact, provider-observed historical reach and continuation behavior
of the named KIS Paper M1 endpoint for QQQ/NAS and SPY/AMS. This is a bounded
capability and pacing measurement that prepares a later durable collector; it
does not claim that either target is complete, qualified, point-in-time safe,
decision-time available, predictive, profitable, or ready for Paper execution.

## Hard Boundaries

- `KIS_PAPER_*` may be read only through the named Paper market-data path.
  Never print or persist credentials; never read or route `KIS_LIVE_*`.
- Do not call account, position, quote, order, cancellation, or any live route.
- Do not alter or duplicate the existing QQQ/SPY scheduled collector, its
  cache, cursor, terminal chain, Docker service, or schedule. The probe must
  use a target-isolated external capability root.
- Keep the first actual probe to at most two serial minute-page requests per
  target with one reusable client, no continuation flood, and no foreground
  retry. Record a source-safe `next_due` only if the provider returns a
  categorical retry fact.
- Retain accepted raw pages only below `D:\market_data`; keep source-safe
  receipts under `D:\thericher-v2\model-artifacts`; never commit either.
- Do not create a recurring scheduler, broad backfill, model, research
  campaign, GPU job, dataset qualification, local-Paper intent, broker order,
  public service, or mutable latest-record rule.

## Required Work

1. Run a concise Throughput Review. Confirm that IWM append is complete but
   does not establish historical reach, and that the existing QQQ/SPY task is
   independent and unchanged.
2. Ask Claude CLI for a short falsification-first drift check before changing
   historical reach, continuation, or source-safe pacing semantics. Send no
   raw rows, values, paths, or credentials; do not wait for the result.
3. Inspect any visible shared-worktree generic minute WIP before relying on it.
   Reattest it with focused tests or replace only the bounded probe package;
   unowned provenance alone is never a block.
4. Freeze the probe contract: exact targets, request/page budget, cursor or
   continuation evidence, raw-retention rule, per-target isolated root, pace
   measurement fields, categorical failure/recovery outcomes, and strongest
   target/cursor/duplicate kill test.
5. Implement or reattest the smallest testable target-isolated probe. Add
   focused fake/local tests for target enforcement, serial page budget,
   continuation handling, external-root/link rejection, no credential or
   network path without `--execute`, and source-safe outcome output.
6. Run a CPU-only fake/local smoke. Then make the bounded KIS Paper attempts
   and retain only permitted external data. Reattach the resulting source-safe
   receipt; do not infer provider-wide history from source exhaustion or a
   short probe.
7. Refresh Data and orchestration stateboards with per-target reach, accepted
   pages, categorical failures, measured elapsed-time bucket, remaining scope
   as `unknown` when appropriate, and the next collection or recovery action.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Probe KIS Paper M1 historical reach`
