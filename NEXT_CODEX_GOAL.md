# Next Codex Goal

## Objective

Build `intraday-qqq-offline-validation-reliability-v1`: make the existing
scheduled intraday QQQ no-intent path produce one deterministic, source-safe
offline validation result or a precise local recovery category, rather than
an opaque `validation unavailable` terminal outcome.

`intraday-head-capture-receipt-binding-v1` is implemented and the normal
collector image was rebuilt. A new task-owned run now requires its same-run
capture receipt binding; historical terminal receipts remain
`legacy_unbound`. The existing task alone owns 2026-08-07 06:20 KST.

## Hard Boundaries

- Do not manually call KIS, invoke or duplicate any task, submit/modify/cancel
  a Paper order, or read `KIS_LIVE_*`.
- Preserve installed task identity, timing, `IgnoreNew`, broker routes, and
  raw-data retention.
- Do not expose raw bars, prices, provider payloads, credentials, accounts,
  intents, order IDs, or secret-like values in Git, logs, artifacts, or
  review prompts.
- Do not turn a missing or malformed session record into a validated result,
  model claim, coverage qualification, Paper permission, or GPU campaign.

## Required Work

1. Inspect the exact source-safe 04:24 terminal/session/validation evidence
   and the offline code path to classify why the valid QQQ `no_intent` session
   produced `prospective_validation_payload_unavailable`. Do not infer from
   raw cache contents or select a latest session.
2. Make the existing explicit-session validator and scheduler integration
   emit exactly one deterministic source-safe outcome for a valid matching
   `no_intent` session. Preserve a distinct recovery result for absent,
   malformed, mismatched, stale, or unsafe evidence.
3. Keep validation offline and side-effect-free: no credential, network, KIS,
   broker, order, or local-Paper mutation path. Reuse the existing task and
   services; do not add a scheduler or public surface.
4. Add focused tests for the identified failure mode, exact-session identity,
   source-safe output, route isolation, and the no-false-success recovery
   path. Rebuild only the existing affected image if source changes require it.
5. If the existing 06:20 KST task runs while this objective is active,
   reattach only its exact source-safe terminal evidence, including the new
   bound/unbound status. Otherwise retain `next_due` and continue ready work.

## Verification

Run focused validation/schedule tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Harden intraday QQQ offline validation`
