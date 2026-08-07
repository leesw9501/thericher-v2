# Next Codex Goal

## Objective

Build `source-local-qqq-donchian-local-paper-pnl-attribution-v1`.

Attribute the already-fixed session-reset QQQ/NAS M1 Donchian 20/10 replay over
the existing frozen 20 complete regular sessions through the local paper FIFO
accounting seam. This is a bounded retrospective baseline only. It must not
select a strategy, predict returns, claim decision-time validity, allocate GPU,
or authorize KIS Paper behavior.

## Hard Boundaries

- Use only the existing hash-bound source-local QQQ/NAS catalog and fixed
  Donchian mechanics contract. Do not collect, alter, or qualify market data.
- Do not call KIS, read credentials or `.env`, invoke a task, or change Docker
  services, schedulers, cache roots, cursors, or source receipts.
- All fills must remain `source: local_paper`; do not create a Paper intent,
  broker order, account route, or live route.
- Freeze the 20/10 rule, session order, completed-bar rule, timing, cost model,
  and terminal-flat policy before inspecting PnL. No parameter sweep, ensemble,
  model comparison, candidate selection, GPU job, or public output.
- Keep any generated summary under `D:\thericher-v2\model-artifacts`, never
  Git. Do not retain raw prices, fills, credentials, or paths in Git evidence.
- Preserve the prior EMA baseline and all task-owned KIS evidence unchanged.

## Required Work

1. Run a concise Throughput Review. Confirm the task-owned QQQ/SPY recovery is
   externally due while the fixed Donchian attribution package is ready and
   resource-independent.
2. Reattest the exact Donchian mechanics parent and source-local catalog before
   use. Freeze one attribution contract with parent identities, selected-session
   rule, local paper fill semantics, FIFO cost model, aggregate metrics, and a
   strongest replay-parity kill test.
3. Build the smallest reusable local attribution harness or extend the existing
   local replay path. It must consume completed Bars, replay only the fixed
   long/flat Donchian state, and emit only deterministic local-paper fills.
4. Write one immutable external, source-safe aggregate result. Bind it to the
   mechanics parent and exact replay digest; preserve terminal-flat and local
   paper provenance. A missing or mismatched parent must fail closed.
5. Add focused tests for deterministic replay, no KIS/credential/broker access,
   local-paper-only fills, cost/PnL parity, terminal flattening, parent mismatch,
   and artifact-root exclusion from Git.
6. Run a CPU-only smoke using the existing local catalog. Refresh Engine,
   Execution, Data, and orchestration stateboards with the exact result scope
   and remaining input limitation.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Attribute local Donchian paper PnL`
