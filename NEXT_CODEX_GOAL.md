# Next Codex Goal

## Objective

Consume the immutable Tiingo raw-D1 comparison snapshot in one frozen,
no-retraining local-paper source-sensitivity replay of the existing unsupported
fixed-ETF campaign.

This advances backtest and walk-forward validation. The result is not
independent validation because the Tiingo representation is bound to r2's fixed
session calendar; it cannot select a model or support a profitability claim.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, and Execution stateboards. Invoke the Review
checkpoint.

## Authority And Boundaries

- Do not read `.env`, credentials, account identifiers, or `KIS_LIVE_*`; do not
  make a network request, access an account, change `THERICHER_MODE`, or alter
  broker behavior.
- Use only the immutable inputs under `D:\market_data`: r2, the Tiingo
  corporate-action snapshot, and
  `fixed_etf_daily\canonical\tiingo_raw_d1\snapshot=2026-07-18-tiingo-raw-d1-r1`.
  Keep run artifacts under `D:\thericher-v2\model-artifacts`, never Git.
- No GPU training, retraining, model search, new candidate, ranking, promotion,
  sealed-holdout access, or profitability claim. Every fill remains
  `source: local_paper`.
- Do not add a provider framework, scheduler, worker, dashboard, report family,
  or a second replay CLI. Extend the existing campaign path only as far as this
  one frozen replay needs.

## Required Work

1. Ask Claude for a brief drift-check before changing the daily campaign input
   contract. Share no raw rows, credentials, or artifacts containing them.
2. Use the existing offline Tiingo raw-D1 loader; do not weaken its r2,
   parent-raw, exact-896-session, canonical-byte, or raw-OHLCV attestation.
   Extend the daily campaign input contract only enough to separate the frozen
   r2 checkpoint source from an attested replay bar input.
3. Reuse the frozen checkpoints, candidate definitions, timing, costs, explicit
   corporate-action input, and local-paper path for exactly one 36-cell,
   no-retraining replay. Keep the parent `unsupported` verdict sticky regardless
   of the comparison result.
4. Write one bounded external summary with input hashes and an explicit
   development-only, non-independent scope. Update Data and Engine stateboards,
   `HANDOFF.md`, and this next goal; verify, commit, and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`. Report any focused
loader/replay command and only safe paths and hashes.

## Suggested Commit Message

`Replay frozen campaign on Tiingo raw D1`
