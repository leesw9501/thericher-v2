# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-overlap-reconciliation-v1`: turn the v5
`incoming_merge` failure into a bounded, revision-preserving forward-cache
merge policy. It must preserve already retained observations, distinguish exact
duplicates from conflicting historical overlaps, and still allow strictly newer
sessions to append later. This advances Data mechanics only; it does not
qualify causal input, strategy, model, execution, Paper trading, or live
behavior.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first check before changing overlap/revision semantics. A
  missing response is `review_unavailable`, not agreement or a hold.
- Treat v5 receipt
  `sha256:a10e42f5a44753c67bf483414005d98b5171341998926b10a2a5f9dc85100910`
  as a source-region fact only. `incoming_merge` is not a row-level cause;
  source inspection names duplicate conflict only as a candidate.
- This is source/fixture-only. Do not read credentials, call KIS, run Docker,
  mutate the external cache, create a scheduler, submit an order, or read or
  route `KIS_LIVE_*`. Do not print or retain raw market rows, values, tokens,
  account identifiers, or dynamic exception details.
- Reuse the existing cache contract. A conflicting overlap must never overwrite
  an earlier retained row, relax its provenance/finality status, or silently
  become a new model input. Exact duplicate rows remain idempotent; strictly
  newer rows may append only under a tested, explicit rule.
- Keep any emitted diagnostics aggregate and source-safe: target category,
  count, and deterministic hash are allowed; raw dates, OHLCV values, or row
  payloads are not. Do not make a new external collector call in this objective.

## Required Work

1. Map the exact `incoming_merge` exception-producing paths and define the
   smallest fixed overlap outcome taxonomy.
2. Add synthetic fixtures for exact duplicate, conflicting overlap, and newer
   append. Prove existing retained rows are never overwritten and all dynamic
   details stay out of source-safe results.
3. Implement the narrow revision-preserving merge behavior and a source-safe
   aggregate diagnostic only if the fixtures show it is needed.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with the result.
   Preserve the v5 receipt and all causal/provider-finality conclusions.
5. Run verification, commit, push, replace this file with exactly one next
   objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
