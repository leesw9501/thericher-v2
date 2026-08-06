# Next Codex Goal

## Objective

Build `intraday-head-duplicate-conflict-provenance-v1`: preserve the source-safe
cause and retained-head disposition of an intraday `minute_duplicate_conflict`
in each future immutable session-capture receipt, then expose it only through
the existing exact bound-receipt recovery reader.

This is a Data recovery contract. It must not reinterpret the completed 06:20
KST result, inspect raw market rows, or make a data-quality, model, Paper,
fill, PnL, or alpha claim.

## Hard Boundaries

- Do not call KIS, invoke or alter any task, submit/modify/cancel a Paper
  order, or read any credential or `KIS_LIVE_*` value.
- Do not inspect, emit, or commit raw bars, prices, provider payloads, paths,
  hashes, credentials, accounts, intents, or order identifiers.
- Do not read mutable `index.json` as an integrity root in the recovery
  projection, mutate historical immutable receipts, or infer provenance absent
  from an older receipt.
- Do not create a scheduler, provider, route, data qualification, model claim,
  GPU campaign, or Paper permission.

## Required Work

1. Before changing the capture/result contract, ask Claude CLI for a concise
   falsification-first drift check. If unavailable, record only
   `review_unavailable` and continue with local evidence.
2. Extend the collector result and future immutable session-capture target
   contract with allowlisted categorical fields for conflict origin
   (`candidate_batch` or `retained_cache` when applicable) and retained-head
   disposition (`not_applicable`, `preserved`, or `quarantined`). Keep every
   non-conflict result explicit and source-safe.
3. Make the exact recovery projection carry those categories only after its
   existing pointer, terminal, run, time, hash, and coverage binding checks
   pass. A historical receipt that lacks the new fields must remain
   `not_recorded_legacy`; it must never be reconstructed from mutable cache.
4. Add synthetic focused tests for candidate-batch conflict, retained-cache
   conflict with and without eligible head quarantine, and cursor-backed
   historical conflict. The strongest kill test is that cursor-backed history
   is neither quarantined nor described as quarantined. Prove a later eligible
   synthetic head can recover only after the recorded quarantine path.
5. Preserve the projection's offline/no-credential/no-network and source-safe
   output guarantees. Refresh the Data and orchestration stateboards with the
   next task-owned due fact.

## Verification

Run focused collector/capture/projection tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Record intraday conflict provenance`
