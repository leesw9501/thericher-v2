# Next Codex Goal

## Objective

Complete `tiingo-prospective-eod-refresh-v1`: create or reattest exactly one
current-date Tiingo Standard EOD prospective snapshot for fixed SPY, QQQ, and
IWM. This advances an independent forward data lineage while the KIS D1 cache
remains target-local quarantined.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards.
- `TIINGO_API_TOKEN` use through the existing local loader is standing-approved
  for this private, no-cost fixed three-symbol acquisition. Never print or
  persist the token, request headers, raw market rows, or raw response bodies.
- Use only `scripts/acquire_tiingo_prospective_eod.py` and its existing fixed
  SPY/QQQ/IWM, three-request, redirect-denying, atomic external-storage path.
  If the current dated immutable snapshot already exists, reattest it offline
  instead of fetching again. Do not add symbols, historical backfill, retries,
  schedules, paid sources, or a new provider.
- Retain raw data only below `D:\market_data\us_equities\fixed_etf_prospective_lineage`.
  Keep generated receipts under `D:\thericher-v2\model-artifacts`; nothing
  derived from the snapshot belongs in Git.
- This snapshot remains `prospective_lineage_only`. It is not point-in-time,
  model, training, campaign, ranking, order, GPU, KIS-recovery, Execution, or
  Paper evidence. Do not change those eligibility flags or use it to clear a
  KIS quarantine.

## Required Work

1. Verify the existing destination and storage policy without reading secrets.
2. Create one current dated snapshot only when absent, otherwise reattest the
   matching immutable snapshot using the existing offline loader.
3. Record only source-safe dataset/manifest identity, request-count category,
   source-as-of boundary, and lineage limitation in `HANDOFF.md` and active
   stateboards.
4. Run required verification, commit, push, replace this file with exactly one
   material next objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
