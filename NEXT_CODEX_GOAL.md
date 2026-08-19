# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-stage-aware-one-shot-collection-v1`: use the
now-attested shared QQQ/SPY D1 pair-forward runtime for exactly one fresh KIS
Paper market-data collection outcome. This is a bounded Data recovery action,
not a causal-input, strategy, model, execution, or trading objective.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first recheck before the collection because the earlier runtime
  image mismatch was unexplained.
- Use only the existing shared-tag `kis-paper-daily-pair-forward` Compose
  service. It may read `KIS_PAPER_*` only inside that service and may use only
  its KIS Paper market-data route and external pair cache.
- Never read or route `KIS_LIVE_*`, print secret/config-variable names, account
  data, raw market rows, raw broker bodies, private cache values, or exception
  text. Do not call an account, position, quote, or order endpoint.
- Reattach the exact matching credential-free preflight contract before the
  collector. Do not run readiness, build a second image, add a provider,
  endpoint, queue, worker, scheduler, or Research/Execution consumer.
- Run the collector at most once. Do not retry automatically, infer data
  availability/finality, or treat a cache write as model/Execution input.
- Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw cache
  data stays under `D:\market_data`; neither enters Git.

## Required Work

1. Reattach the hash-matching `collection_required` preflight and recheck that
   no Research/Execution consumer treats this forward cache as a decision-time
   or finality input.
2. After the Claude recheck and focused tests, invoke the existing shared-tag
   collector exactly once. Its own token/rate checks determine whether it
   collects or safely defers.
3. Recompute the external receipt SHA-256 and reattach only its categorical
   status, optional fixed `failure_stage`, contract hash match, safe aggregates,
   route isolation, and artifact-policy facts. A missing stage on a new
   shared-contract receipt is a scoped runtime-provenance fault, never a reason
   to retry.
4. If the cache changed, record that fact only; defer causal qualification to a
   separate objective. If it did not, close the exact outcome without a loop.
5. Refresh stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run verification,
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
