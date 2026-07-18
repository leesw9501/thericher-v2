# Next Codex Goal

## Objective

Advance data collection by finding and, only when eligible, capturing one
bounded no-auth US-equity data pilot that improves the next research-data
frontier.

The KIS execution lane remains failed closed and does not block this independent
Data-lane objective.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
the Data, Engine Research, and Execution stateboards, plus the invoked Review
checkpoint.

## Authority And Boundaries

- Do not read `.env`, use `TIINGO_API_TOKEN`, call KIS, or access an account.
- Keep all acquired bytes under `D:\market_data`, never Git. Preserve the 20%
  warning and 15% hard free-space floor on `D:`.
- Consider only sources that are no-auth, no-cost, lawful for this private use,
  and whose current terms and provenance are sufficiently clear. Do not bypass a
  login, paywall, rate limit, or manual agreement.
- A pilot must increase a named coverage or provenance capability; do not
  duplicate existing fixed-ETF bytes merely to make a new artifact.
- Do not mark any new data ranking or sealed-holdout eligible without evidence,
  train a model, use GPU, alter KIS behavior, or add a scheduler, dashboard,
  report/gate family, or broad provider framework.

## Required Work

1. Data performs a targeted metadata inventory of `D:\market_data\pit_sources`
   and the known canonical roots. Avoid an expensive full recursive scan.
2. Assess at most two official/no-auth source candidates against exact coverage,
   adjustment, historical-universe, rights, and storage facts. Engine Research
   states the smallest additional coverage that would unlock a falsifiable next
   data or model question.
3. If one candidate is eligible and materially useful, acquire one narrow,
   immutable pilot outside Git with raw bytes, a concise manifest, and a
   provenance/eligibility result. Otherwise record the bounded reason no pilot
   was acquired and stop pursuing that source after two automated failures.
4. Data and Review independently check source boundaries and simplification.
   Refresh the Data stateboard, `HANDOFF.md`, and this single next goal; verify,
   commit, and push.

Ask Claude for a short drift-check only before a provider-contract or runtime
change. Do not use Claude for credentials, raw market data, or source payloads.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`. Report any focused
inventory or acquisition command separately.

## Suggested Commit Message

`Triage next US equity data source`
