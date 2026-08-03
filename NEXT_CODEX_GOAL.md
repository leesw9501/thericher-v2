# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-broad-d1-adjustment-semantics-probe-v1`: determine, with one small
KIS Paper daily-price capability probe, whether the existing current-listing
broad-D1 source can expose a separate adjusted daily representation for a fixed
sample of already-audited range events.

This is source provenance work only. It must not reopen the completed broad
collector, replace retained raw data, repair prices, train a model, make a PnL
claim, or change Paper/live execution behavior.

## Boundaries

- Before relying on a changed daily-adjustment interpretation, ask Claude for
  one concise falsification-first challenge of the source/temporal semantics.
- `KIS_PAPER_*` is authorized only for the KIS Paper US daily-price endpoint
  and its in-memory token path. Do not call account, position, quote, order,
  modify, cancel, or live endpoints; never read `KIS_LIVE_*`.
- Use one bounded, serial client and reuse its valid in-memory token. Record
  source-safe request/accepted/error counts and measured pace only; do not
  create a new global throttle or a foreground wait.
- Derive at most three fixed witnesses from the completed selected-panel audit
  in memory. Do not output witness symbols, dates, raw rows, prices, values,
  credentials, account data, or broker payloads to Git, logs, stateboards, or
  artifacts.
- Store raw KIS material only below `D:\market_data`; store aggregate receipts
  only under `D:\thericher-v2\model-artifacts`. Keep Docker artifacts under
  `/app/model_artifacts`; reject symlinked or Git-resident artifact paths.
- The probe may report only categorical adjustment semantics such as
  `unchanged`, `changed`, `unsupported`, `unavailable`, or `inconsistent` plus
  aggregate counts/hashes. It cannot qualify the source as PIT, corporate-action
  complete, model-ready, ranking-ready, Paper-ready, or live-ready.
- No new broad-D1 model, ensemble, local-paper replay, GPU appointment, or
  CUDA work is eligible in this objective.

## Required Work

1. Data: implement a bounded read-only witness selector from the immutable
   selected-panel lineage and a KIS daily adjustment-mode capability probe.
   Freeze its event selector, endpoint parameters, comparison semantics, retry
   class, external artifact root, and stop rule before the first request.
2. Data: run the actual-source probe once when the input/endpoint is eligible.
   If it is unavailable or unsupported, write one source-safe categorical
   receipt and close only this probe; do not loop or substitute another source.
3. Engine Research: record that the two completed broad-D1 logistic lineages
   remain closed. It may consume only the categorical source result and must not
   open a model or GPU campaign.
4. Add focused tests for fixed witness selection, token reuse boundaries,
   no account/order/live route, source-safe receipts, external-only artifacts,
   and categorical unavailable containment. Refresh Data, Engine Research,
   Research Steward, orchestration, and handoff stateboards.

## Completion Evidence

- one fixed, source-safe adjustment capability contract;
- one actual KIS Paper daily-price receipt or scoped categorical unavailable
  receipt;
- focused tests, clean-root full parallel verification, Ruff, both Compose
  configurations, commit, and push.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
