# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-stage-discrimination-v1`: make the existing
QQQ/SPY KIS Paper D1 collector's source-safe `unavailable` outcome distinguish
fixed failure stages, then use one networkless in-container readiness check to
decide whether one new collector call is justified. This repairs data-collection
diagnostics, not a strategy, causal-input, or trading path.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active Data, Engine Research, Execution,
  and orchestration stateboards.
- Never read or route `KIS_LIVE_*`, print a secret/config-variable name,
  account data, raw market rows, raw broker bodies, or exception text.
- Keep the existing QQQ/SPY pair-forward routes, artifact policy, cache format,
  token gate, rate gate, schedule, and consumer boundary. Do not create a new
  provider, endpoint, queue, worker, scheduler, or research/execution consumer.
- The only permitted credential read is the existing pair-forward Compose
  service's in-container readiness check or collector. The readiness check makes
  no network/KIS request and no cache write.
- Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw cache
  data stays under `D:\market_data`; neither enters Git.
- No KIS account/order endpoint, Paper intent, model training, GPU, public
  service, or live behavior is in scope.

## Required Work

1. Refactor only the existing collector path so its fixed, source-safe failure
   stage is one of `control_gate`, `environment`, `collection`, or `commit`.
   The category must not reveal exception text, HTTP/response detail, target,
   credential/config-variable identity, or raw data.
2. Add a networkless in-container readiness mode that validates only control
   gate state and aggregate environment availability. It must write a canonical
   source-safe receipt, make no cache write, and expose no secret/config name.
3. Add focused synthetic tests for every fixed stage, readiness isolation, route
   isolation, immutable external receipts, and compatibility of the existing
   collector behavior. Strongest kill test: if any synthetic stage is not
   discriminated exactly, do not invoke a new collector.
4. After focused tests pass, run the readiness mode once. Run the existing
   credentialed collector at most once only if readiness is aggregate-ready,
   the token start is due, and the rate gate is not deferred. A non-ready or
   deferred readiness result closes this objective without a collector call.
5. If a collector call occurs, preserve only its source-safe categorical result.
   Do not infer data availability/finality, retry automatically, or treat a
   cache write as a model/Execution input.
6. Refresh stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run verification,
   commit, push, replace this file with exactly one next objective, and
   continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
