# Next Codex Goal

## Objective

Build one immutable Tiingo raw-D1 comparison snapshot for SPY, QQQ, and IWM
from the existing Tiingo Standard EOD raw responses, bound to the fixed-ETF r2
sessions.

This advances data collection and a development-only data-source robustness
check for the existing unsupported campaign. It does not select a model.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
the Data, Engine Research, and Execution stateboards, plus the invoked Review
checkpoint.

## Authority And Boundaries

- Do not read `.env`, credentials, account identifiers, or `KIS_LIVE_*`; do not
  make a Tiingo or KIS network request, access an account, or change
  `THERICHER_MODE`.
- Use only the existing immutable Tiingo source snapshot under
  `D:\market_data\us_equities\fixed_etf_corporate_actions\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-corporate-actions-r1`.
  Store new derived bytes under `D:\market_data` and run artifacts under
  `D:\thericher-v2\model-artifacts`, never Git. Preserve the 20% warning and
  15% hard free-space floor on `D:`.
- The result is development-only. Do not open ranking or sealed evidence, train
  a model, use GPU, select a candidate, make a profitability claim, or alter
  broker/execution behavior.
- Use the existing catalog/manifest and Tiingo corporate-action patterns. Do
  not add a broad provider framework, worker, scheduler, dashboard, or
  report/gate family.

## Required Work

1. Ask Claude for a short drift-check before changing the Tiingo parser or
   source contract. Share no credentials, raw responses, or unnecessary
   row-level data.
2. Extend only the smallest existing Tiingo path needed to normalize raw D1
   OHLCV plus `divCash` and `splitFactor` from the three exact source files for
   the 896 r2 sessions. Fail closed on missing/extra sessions, unclear raw-field
   semantics, source tampering, bad lineage, or an existing destination.
3. Derive one dated external snapshot with hashes, source lineage, schema,
   raw-versus-adjusted policy, and development-only eligibility in the existing
   manifest/catalog shape. Do not copy or overwrite the source snapshot.
4. Data and Engine Research confirm the snapshot is only a frozen input for one
   future no-retraining source-sensitivity replay. Review checks scope and
   simplification. Refresh stateboards, `HANDOFF.md`, and this next goal;
   verify, commit, and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`. Report the focused
derivation command and only safe artifact/data paths and hashes.

## Suggested Commit Message

`Add Tiingo raw D1 comparison snapshot`
