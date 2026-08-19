# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-one-shot-collection-v2`: advance the existing
QQQ/NAS plus SPY/AMS KIS Paper D1 forward-cache path with at most one bounded
existing collector invocation, then reattach only source-safe provenance. This
improves current data coverage; it does not claim availability, finality, a
model input, or a trading result.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, `agents/data.md`, `agents/engine-research.md`,
  `agents/execution.md`, and `agents/orchestration.md`.
- `KIS_PAPER_*` may be read only by the existing
  `kis-paper-daily-pair-forward` Compose service. Never read or route
  `KIS_LIVE_*`, print credentials, account data, raw market rows, or raw broker
  bodies.
- Use the existing network-disabled preflight first. Run the existing
  credentialed Compose collector at most once, and only when that preflight
  says collection is required. Do not manually invoke a Windows Task, create a
  retry loop, alter a scheduler, or start a parallel collector.
- Keep raw cache data under `D:\market_data` and source-safe receipts under
  `D:\thericher-v2\model-artifacts`. Do not write either to Git.
- No broker order, account endpoint, Paper intent, model training, GPU,
  research campaign, or public service is in scope.
- Never infer named clock/session, decision-time availability, or provider
  finality from a newer cache session, file timestamp, task exit, receipt hash,
  or successful collector result. No consumer may treat `latest_session` as
  decision-time availability.

## Required Work

1. Recheck the narrow static consumer boundary: the pair-forward cache must
   have no Research or Execution consumer that promotes a newer
   `latest_session` into availability/finality evidence.
2. Use the existing read-only preflight Compose service. Record its categorical
   outcome only.
3. If and only if collection is required, run the existing
   `kis-paper-daily-pair-forward` Compose collector exactly once. A token-gate
   deferral, no accepted page, unavailable result, or unchanged cache is a
   closed result for this objective, not a reason to retry.
4. Reattach the resulting source-safe receipt and current cache through the
   existing offline reader. If an eligible direct parent receipt exists, write
   one fresh causal-qualification receipt with a new explicit label; keep the
   three runtime conditions `not_observed` unless retained evidence proves
   otherwise.
5. Refresh Data, Engine Research, Execution, orchestration, HANDOFF, and
   RUNBOOK with only the observed categorical result and the no-promotion
   limitation. Record the Claude `supported-with-limits` boundary if it
   materially affects the result.

## Completion Evidence

- One preflight outcome, and zero or one collector outcome, with external
  source-safe receipt pointer(s).
- A focused test or static proof that no pair-forward `latest_session` consumer
  treats data freshness as availability/finality.
- One offline reattachment result, if a usable direct collector receipt exists.
- Required verification passes, then commit, push, and replace this file with
  exactly one next company objective.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
