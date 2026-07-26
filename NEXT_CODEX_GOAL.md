# Next Codex Goal

## Objective

Establish a six-symbol NAS-only KIS Paper daily-universe capability cache.

Use one existing official current-listing directory snapshot only to choose a
small, deterministic prospective NASDAQ common-stock probe set, then test the
existing KIS Paper daily collector against that set. This advances the data
foundation for future stock-selection research. It does not construct a
historical point-in-time universe, train a model, select a strategy, submit an
order, or enable live behavior.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Inspect only source-safe metadata for the official symbol-directory snapshot
   and existing KIS daily cache/control state. Do not scan or print raw price
   rows, credentials, or account facts.

## Required Work

1. Ask Claude CLI for a concise falsification-first review before adding the
   new immutable symbol registry and probe cache. State that the official
   directory is current-listing evidence only, the fixed six-symbol NAS-only
   scope, KIS's unproven general-symbol historical reach, source separation,
   stop rule, and the fact that would prevent broader collection. An expired
   CLI session is scoped reviewer-tool evidence, not a hold on private
   non-live Data work.
2. Implement a deterministic parser for the existing official directory
   snapshot and a probe-owned immutable NASDAQ common-stock symbol/exchange
   registry. Pin the exact source manifest/hash. Exclude nonstandard/test/ETF
   entries by explicit documented rules. Do not widen the existing global KIS
   daily allowlist or reuse the QQQ/SPY research catalog as a universe.
3. Add a separate cache and manifest contract below
   `D:\market_data\us_equities\kis_paper_private\daily-universe-probe\v1`.
   It must preserve source identity, registry hash, target identity, request
   counts, strict `tr_cont` cursor progress, accepted/source-limited/
   unsupported/invalid classification, and recovery state without printing raw
   rows.
4. Run one finite capability worker: exactly six NAS targets, one Paper client,
   concurrency one, the installed 1.0-second request gate, and at most two
   daily pages per target (twelve page requests maximum). Store raw daily bytes
   only in the probe cache under `D:`; write only source-safe evidence under
   the external artifact root.
5. Keep current-listing and price-provider facts separate. A successful probe
   is not a historical PIT universe, a corporate-action qualification, a
   training dataset, a model result, or a paper-trading prerequisite. A weak or
   partial source result completes this objective with a scoped classification;
   do not silently substitute another provider or expand the target set.
6. Add focused tests for deterministic registry selection, manifest/hash
   binding, six-target/page caps, cursor and classification behavior, external
   storage, no account/order/live route, and unchanged local-paper isolation.
7. Keep Engine Research and Execution independent. Update Data and
   orchestration stateboards with only the new source contract, finite result,
   limitations, recovery fact, and next ready action.

## Hard Boundaries

- Use `KIS_PAPER_*` only through the owned Paper **daily market-data** route.
  Do not call account, position, order, cancel, modify, or any `KIS_LIVE_*`
  endpoint.
- Do not read `.env` beyond the owned Paper market-data configuration path, and
  never print, log, commit, or send credentials, account identifiers, raw
  provider payloads, or raw prices to Claude.
- NAS only: do not add NYS/AMS exchange mapping, a scheduler, a broad backfill,
  a parallel request flood, or more than the six fixed targets in this goal.
- Keep market-data bytes under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- Do not create a stock-selection model, ranking, PnL result, dashboard,
  ensemble, paper intent, or live behavior from this capability probe.

## Completion Evidence

- A hash-pinned current-listing source contract and deterministic six-target
  NAS-only registry, explicitly marked prospective-only.
- A separate, recoverable KIS daily probe cache with one final classification
  for each target and no modification of the QQQ/SPY research catalog.
- One finite single-client collection result or a precise source-limited fact,
  with no account/order/live route and no raw data in Git or artifacts.
- Updated Data and orchestration stateboards that name the exact limitation
  preventing or permitting a future stock-selection campaign.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A rate cooldown, unsupported symbol, incomplete page,
weak source coverage, or lane-local failure does not stop another ready lane.
