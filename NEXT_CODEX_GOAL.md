# Next Codex Goal

## Objective

Complete `norgate-trial-host-readiness-reconciliation-v1`: turn the prior
source-safe `input_unavailable/local_api_not_ready` Norgate trial receipt into
one bounded, reproducible local-host diagnosis that either establishes a
specific non-secret prerequisite for a later date-indexed capability probe or
closes this host path without polling.

## Boundaries

- Reattach the exact prior Norgate host-readiness receipt before new inspection.
- Use only the existing isolated Norgate host runtime and local installation
  metadata. Do not read raw prices, OHLCV, symbols, listings, membership,
  corporate actions, account values, or secret/config values.
- Do not call a network, KIS, Docker, a broker, or a public service. Do not run
  an updater, purchase anything, change a subscription, start a scheduler, use
  GPU, train/load a model, or change Execution behavior.
- Do not read `.env`, credentials, or `KIS_LIVE_*`. Never persist paths that
  could identify a private database, raw rows, configuration values, or secrets.
- Store only source-safe receipt artifacts under
  `D:\\thericher-v2\\model-artifacts`; do not put artifacts or Norgate data in Git.
- This goal may classify only a fixed safe category such as
  `runtime_import_unavailable`, `local_api_not_ready`,
  `configured_database_not_observed`, `ready_for_date_indexed_probe`, or
  `diagnosis_unavailable`. It cannot itself claim trial rights, data
  availability, point-in-time correctness, ranking, model eligibility, Paper
  eligibility, or live readiness.

## Required Work

1. Reattach the prior receipt with its existing offline reader and freeze the
   allowed local metadata probes before any host invocation.
2. Implement a narrow host diagnostic that reports only categorical runtime,
   package/API, local service/process, and safe root-presence facts. Redact all
   identifiers and values.
3. Add focused tests for receipt binding, categorization, redaction, external
   artifact isolation, and no network/credential/KIS/broker path.
4. Run the new diagnostic once with the isolated host runtime and independently
   verify its receipt.
5. If it is `ready_for_date_indexed_probe`, make the next goal the existing
   bounded Norgate date-indexed capability probe. Otherwise record the precise
   local prerequisite or closed unavailable state and dispatch a different ready
   data/research package without polling.
6. Refresh active stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run required
   verification; commit, push, replace this file with exactly one material next
   objective, and continue.

## Verification

```powershell
.\\scripts\\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
