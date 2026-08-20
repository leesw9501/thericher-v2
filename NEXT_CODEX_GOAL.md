# Next Codex Goal

## Objective

Complete `tiingo-d1-event-mask-coverage-audit-v1`: explain, with
source-safe aggregate evidence only, why the frozen Tiingo D1 trend-pullback
rotation had insufficient validation active decisions, without changing the
frozen rotation rule or its event/discontinuity masks.

## Boundaries

- Reattach only
  `snapshot=20260801T173121Z-tiingo-etf-d1-r1`, the completed rotation
  precommit, and its exact independent validation receipt. Do not download,
  refresh, select, or alter a Tiingo snapshot.
- Do not read credentials, call KIS, a broker, Docker, or a network. Do not use
  GPU, train/load a model, create an ensemble, or modify Execution behavior.
- Do not change the 60-session trend, 5-session pullback, 20-session
  volatility, 61-session purge, 5/10/20-bps cost band, event/discontinuity
  masks, comparators, or minimum active-decision rule.
- Keep generated evidence under `D:\\thericher-v2\\model-artifacts` and raw
  data under `D:\\market_data`. Do not retain rows, dates, prices, values,
  scores, per-decision outputs, credentials, weights, or a raw mask trace in
  Git or artifacts.
- The audit may emit only aggregate counts, deterministic set hashes, bounded
  run-length buckets, and categorical integrity findings. It is diagnostic
  only: never a performance, point-in-time, promotion, KIS, Paper, GPU, or
  live claim.

## Required Work

1. Reattach the frozen rotation precommit, summary, validation receipt, and
   exact pinned snapshot identity before inspecting source data.
2. Add a narrow offline audit that accounts separately for event and
   discontinuity exclusions, their overlap, per-symbol aggregate coverage, and
   bounded exclusion-run buckets. Bind its aggregate decision counts to the
   completed rotation receipt.
3. Add focused tests for source/receipt identity, aggregate-only output,
   tamper rejection, and absence of credential/network/broker paths.
4. Run one CPU-only external audit and independently validate its receipt.
5. If and only if an aggregate semantic contradiction is evidenced, request a
   Claude falsification-first review before proposing any material
   corporate-action, temporal, or masking-policy change. Otherwise close this
   Tiingo rotation lineage without retuning it.
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
