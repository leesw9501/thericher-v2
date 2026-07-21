# Next Codex Goal

## Objective

Build and run the first paced private KIS Paper daily collector for `QQQ` / `NAS`.

The capacity maps established that KIS can return two daily pages but rejected
an immediate third request. The operator has authorized KIS Paper calls and a
bounded private local cache under `D:\market_data`; this is a small collection
run, not a claim of general archive entitlement.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `agents/data.md`, and `agents/execution.md`.
3. Read the capacity-map implementation, its summaries, and the existing
   market-data client/tests before editing collection code.
4. Ask Claude for a short drift-check before the first real collector run if
   its request/storage contract changes materially from this goal.

## Work Packages

### Data Agent

- Define the canonical private-cache layout under
  `D:\market_data\us_equities\kis_paper_private\daily`.
- Define the manifest fields: source/endpoint, symbol/exchange, requested and
  returned date bounds, page count, row count, raw-file SHA-256, dedupe count,
  source-adjustment mode, code version, and stop outcome. Do not expose a
  credential, cursor, response body, or account fact.
- Treat the observed shared `2026-02-24` daily boundary as a dedupe check, not
  proof of an exact duplicate until raw rows are compared inside the collector.

### Execution Agent

- Add a fresh `kis-paper-private-daily-collector-v1` runner that uses only
  `dailyprice` / `QQQ` / `NAS` / unadjusted `MODP=0`.
- Use one KIS Paper token, at most two pages, and an internal minimum two-second
  page interval. The delay is a service-pacing parameter, not a CLI widening
  knob. Stop on the first response/transport rejection.
- Write an atomic raw daily cache plus its atomic manifest to the named D:
  root. Never write raw rows in Git or `D:\thericher-v2\model-artifacts`.
- Execute it once after tests pass. It needs no regular-session gate, account
  endpoint, order endpoint, live endpoint, or public web route.

### Validation

- Independently verify the external cache location, manifest/raw hashes,
  request count, pacing evidence, deduplication, redaction, and recovery state.
- Confirm that a rejected run is terminal under its objective ID and that no
  raw-minute collection or model/paper promotion was introduced.

## Hard Boundaries

- Private local cache only: no serving, publication, redistribution, or
  third-party dashboard/API exposure.
- Stop and report if an applicable KIS or exchange term is found to prohibit
  retention, or if the projected D: free-space floor would be crossed.
- Do not turn a successful two-page run into a large historical backfill,
  additional symbols, raw-minute collection, a model dataset, or a strategy.
- Do not submit, cancel, or modify an order; do not enable KIS live or change
  capital as part of this objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Add paced KIS daily collector`
