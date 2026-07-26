# Next Codex Goal

## Objective

Build a frozen, source-separated six-symbol KIS Paper daily panel contract from
the completed NAS-only capability cache.

This turns the accepted current fixed basket into a typed chronological daily
panel that future local-paper Research can consume. It does not claim a
historical point-in-time universe, corporate-action completeness, a stock
ranking result, model performance, a Paper order, or live behavior.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Inspect only the source-safe manifest and evidence for the completed
   `daily-universe-probe/v1` run. Do not print raw rows, credentials, account
   facts, or prices.

## Required Work

1. Ask Claude CLI for a concise falsification-first check before introducing
   the new panel contract. State the fixed current six-symbol registry, exact
   cache/evidence hashes, current-listing/PIT limitation, alignment rule,
   intended local-paper-only consumer, and the fact that would prevent a
   Research handoff. Expired OAuth is scoped reviewer-tool evidence, not a
   hold on private offline Data work.
2. Implement a typed read-only loader that accepts only the exact completed
   six-symbol KIS Paper probe cache and its hash-pinned registry. It must
   verify raw-file hashes, cache/evidence linkage, `MODP=0_unadjusted`, the
   ordered `AAPL/AMZN/GOOGL/META/MSFT/NVDA` NAS scope, chronological rows, and
   no duplicate or conflicting sessions.
3. Derive one immutable D:-resident common-session panel manifest with explicit
   source hashes, six-symbol identity, shared session count, chronological
   bounds, rows excluded by alignment, and the current-listing/corporate-action
   limitations. Keep raw data under `D:\market_data`; write only source-safe
   panel evidence under `D:\thericher-v2\model-artifacts`.
4. Add a narrow adapter that exposes completed-bar daily inputs to the existing
   offline/local-paper validation boundary. It may expose typed data and timing
   metadata only; it must not train a model, rank stocks, create a decision,
   invoke KIS, read credentials, submit an intent, or change broker routing.
5. Add focused tests for source/hash binding, raw-file integrity, alignment,
   cache/evidence containment, no source blending, local-paper route isolation,
   and rejection of noncanonical or corrupted inputs.
6. Update the Data, Engine Research, and orchestration stateboards with the
   exact panel fact or limitation. Keep the Norgate and ETF datasets separate;
   do not use their memberships or rows to repair this KIS panel.

## Hard Boundaries

- Offline only: do not call KIS, read `.env`, access account/order endpoints,
  create a schedule, or use any `KIS_LIVE_*` value.
- Do not expand the six symbols, KIS exchange scope, page range, cache, or
  official-directory snapshot in this goal.
- Do not relabel the current registry as historical PIT, survivorship-free,
  corporate-action-qualified, ranking-eligible, or paper-trading-eligible.
- Do not blend KIS rows with Norgate, Tiingo, Yahoo, ETFs, or any other source.
- Keep data and artifacts outside Git; do not create a model, dashboard,
  ensemble, Paper intent, order, or live behavior.

## Completion Evidence

- One immutable, hash-bound six-symbol common-session panel manifest under D:,
  plus linked source-safe external evidence.
- A typed completed-bar adapter with no credential/network/broker capability.
- Tests showing corrupted or noncanonical data cannot become the panel or a
  local-paper validation input.
- Stateboards that name the panel's exact limits before any Research campaign.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A source-local cache issue or Claude OAuth fault does
not stop independent ready work.
