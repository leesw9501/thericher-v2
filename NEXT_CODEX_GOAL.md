# Next Codex Goal

## Objective

Build `kis-paper-iwm-m1-current-head-ingestion-v1`.

Advance the market-data collection loop by turning the already observed
IWM/AMS one-page KIS Paper M1 capability into one bounded, target-isolated
current-head cache. It must leave the existing task-owned QQQ/NAS and SPY/AMS
collector, cache, cursor, terminal chain, and schedule unchanged. This is a
source-local data-expansion result, never a data qualification, model, PnL,
Paper, or broker claim.

## Hard Boundaries

- Do not read `KIS_LIVE_*`, enable live behavior, call account/order routes, or
  submit, modify, or cancel any broker order.
- KIS Paper market-data access is standing-authorized only through the named
  Data-owned client path. Any actual probe is at most one client, one IWM/AMS
  current-page request, with raw output retained only under `D:\market_data`.
  Never print or persist credentials, tokens, raw rows, prices, provider
  payloads, or cache paths in Git or source-safe artifacts.
- Do not invoke, alter, duplicate, or replace the existing QQQ/SPY scheduled
  task. Do not add or register a scheduler in this objective.
- Do not broaden IWM to historical pagination, another symbol, a model input,
  a strategy, local-Paper intent, performance/PnL claim, GPU campaign, or
  public service.
- Keep generated evidence under `D:\thericher-v2\model-artifacts` and raw
  market data under `D:\market_data`; never commit either.

## Required Work

1. Run a concise Throughput Review and inspect only the existing source-safe
   IWM capability receipt, target validation, cache contracts, and free-space
   fact. Confirm the QQQ/SPY task is independent and remains owned by its next
   scheduled invocation.
2. Before changing target, cache, or provider-recovery semantics, ask Claude
   CLI for a concise falsification-first drift check. Do not send it secrets,
   raw rows, prices, or cache paths, and do not wait on it.
3. Freeze one ingestion contract: IWM/AMS identity, exactly one current page,
   isolated cache root, no continuation request, source-safe result fields,
   strongest isolation kill test, and the fact that would permit a later
   historical or scheduled expansion.
4. Implement the smallest reusable collection entry point or target parameter
   needed to use the existing client without changing the QQQ/SPY default path.
   Reject a non-IWM/AMS target, continuation request, unsafe cache root, or
   cross-target state mutation before any provider call.
5. Add focused fake-client tests proving target isolation, one-page request
   shape, no QQQ/SPY cache/cursor mutation, source-safe receipt shape,
   external-only raw storage, and no account/order/live/credential route.
6. Run a CPU smoke with the fake client. If it passes and the external route is
   ready, make at most one owned IWM/AMS current-page call and record only
   accepted/error category, one-page count, pace bucket, and next recovery
   fact. Otherwise record why no probe was issued. Refresh Data and
   orchestration stateboards.

## Verification

Run focused tests and any source-safe probe used, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add isolated IWM M1 head ingestion`
