# Next Codex Goal

## Objective

Build one bounded, offline intraday multi-timeframe local-paper baseline from
the existing canonical 1-minute CVS/FCX/KO evidence.

This advances backtest and walk-forward validation plus paper-trading readiness
by proving that one completed-bar decision path can consume deterministic
`1m`, `5m`, `10m`, `1h`, and `3h` bars and remain fully replayable through the
local paper simulator. It is a pipeline smoke, not a strategy-selection,
execution-quality, or profitability result.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, and Execution stateboards. Ask Claude for a
short scope-drift check before changing a shared validation or execution
contract, then invoke the Review checkpoint.

## Boundaries

- Use only existing local market-data evidence, starting with the small
  CVS/FCX/KO 1-minute snapshot. Re-attest it through the Data-owned loader; do
  not read `.env`, credentials, or raw files through an unverified path.
- Do not call a network API, acquire data, call KIS, submit broker orders, or
  query a broker account. Every generated fill must remain `source: local_paper`.
- Do not train a model, use GPU, create model artifacts, run a campaign, rank
  a candidate, open a holdout, or make a performance/profitability claim.
- Keep the change to the smallest shared Data/Research/Execution contract that
  actually enables the smoke. Do not add a scheduler, provider framework,
  report family, dashboard, or a second validation system.

## Required Work

1. Re-attest the exact existing 1-minute input and inventory its usable
   completed-bar spans without exposing raw rows in durable output.
2. Reuse or minimally complete deterministic resampling for `1m`, `5m`, `10m`,
   `1h`, and `3h`, preserving incomplete-bucket omission and per-symbol/timeframe
   isolation.
3. Add one small deterministic completed-bar baseline that produces a decision,
   eligible `OrderIntent`, and replayable local-paper fill path for each usable
   timeframe. Flatten or explicitly account for any final position.
4. Run a CPU smoke on deterministic sample bars first, then one read-only local
   data smoke if the attested window supports it. Record only concise counts,
   data limitations, and local-paper replay facts outside Git when recovery
   evidence is genuinely needed.
5. Add focused tests proving resampling boundaries, offline/credential-free
   execution, local-paper-only fills, replayability, and artifact placement
   outside Git when an artifact is written.
6. Update the Data, Engine Research, and Execution stateboards, `HANDOFF.md`,
   and this next goal before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add intraday multi-timeframe local paper baseline`
