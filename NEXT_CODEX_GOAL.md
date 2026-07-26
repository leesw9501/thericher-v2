# Next Codex Goal

## Objective

Run one frozen QQQ/SPY KIS-private-daily CPU L2 logistic control campaign.

Use the existing hash-attested, completed-bar daily pair to produce one
reproducible descriptive validation result and its matched local-paper naive
comparators. This advances feature/model research, backtest validation, and
PnL attribution. It does not select a model, tune a result, create an
ensemble, submit a broker order, or enable live behavior.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Read the frozen daily sequence campaign contract and the L2 control module
   and tests before executing the campaign. Inspect only source-safe catalog
   metadata and hashes; do not print raw rows.

## Required Work

1. Review and integrate the fixed CPU L2 logistic control implementation. It
   must use the exact QQQ/SPY daily catalog hashes, 20 completed-bar features,
   the chronological `3,783 / 22 / 951` geometry, development-only fitting,
   fixed threshold and hyperparameters, and a unique immutable run label.
2. Run the one offline CPU campaign against the attested local cache using
   `D:\thericher-v2\model-artifacts` as the artifact root. Write precommit,
   model parameters, replay evidence, and summary only outside Git. Do not
   write raw market data to the artifact root.
3. Replay the frozen validation exactly once for the L2 control and the fixed
   `flat`, `always_long`, and `previous_bar_direction` comparators. Every fill
   must stay `source: local_paper`.
4. Inspect only the source-safe summary, hashes, replay counts, costs, and PnL
   attribution. Do not tune, rerun with a changed parameter, choose a winner,
   build an ensemble, or materialize a sealed holdout. If the result is
   unexpectedly stronger than the naive comparators, ask Claude for the
   required falsification-first challenge before relying on that interpretation;
   an expired CLI session is a scoped reviewer-tool fault, not a promotion.
5. Keep the Data worker and Execution lane independent. Do not make a future
   data capture, KIS API response, GPU job, or local-paper result a prerequisite
   for this bounded CPU control.
6. Update the Engine Research and orchestration stateboards with only the
   campaign contract, external evidence pointer, result scope, and next
   falsification action. Preserve the existing corporate-action limitation.

## Hard Boundaries

- This is offline research: do not read `.env`, credentials, account facts, or
  `KIS_LIVE_*`, and do not make KIS, broker, or public-network calls.
- Do not submit, modify, cancel, or reconcile a broker order. Do not create a
  KIS Paper intent from this campaign.
- Keep market-data bytes under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- No GPU training, parameter sweep, retraining, ensemble, selection,
  promotion, dashboard change, or scheduler is in scope.
- Do not print or send raw bars, credentials, account identifiers, model
  weights, or sealed labels to Claude.

## Completion Evidence

- A test-backed deterministic control implementation that rejects repository
  artifact paths and requires the frozen pair contract.
- One external immutable CPU run with a precommit written before fitting and
  validation replay.
- Two model replay cells and six naive replay cells, all `local_paper`, with
  source-safe after-cost PnL attribution.
- Updated stateboards that state plainly that the result is descriptive only
  and name its next falsification step.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A weak/negative result, existing data limitation, GPU
idle period, or lane-local failure does not stop another ready lane.
