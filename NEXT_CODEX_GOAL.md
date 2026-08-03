# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-spy-completed-bar-decision-timing-probe-v1`: one bounded,
source-safe measurement of the existing KIS Paper `SPY/AMS/1m`
intraday-head collection's schedule relation, collection lag, and
post-collection 15:30-prefix availability.

The outcome quantifies the current path for a later schedule proposal. It must
not claim that a post-collection cache was available at the 15:30 decision
time, or that the route is feasible before expiry. It is not a strategy result,
profitability claim, schedule change, model tuning, or Paper trade.

## Boundaries

- `KIS_PAPER_*` may be used only by the existing Data-owned market-data client
  and collector path. Do not read or route `KIS_LIVE_*`.
- Do not call a KIS account, position, quote, order, submit, modify, cancel,
  or reconciliation endpoint. Do not create an intent or local-paper fill.
- Reuse the existing intraday-head collector and cache. Do not run a parallel
  collector, create a duplicate cache, or retain raw provider rows outside
  `D:\market_data`.
- Record only source-safe raw timing endpoints with explicit America/New_York
  offset, category, count, and identity facts outside Git. Never record
  credentials, account identifiers, request URLs, raw bars, prices, or broker
  payloads.
- Preserve the frozen prospective-SPY baseline and existing `00:31`, `02:31`,
  `04:31`, and `06:20` KST schedule. Do not change cadence, TTL, baseline,
  size, or Paper route based on a single unreviewed observation.
- The next market-session due time belongs to the owned Data worker or
  scheduler. Build and test all offline pieces now, then yield only that
  worker rather than foreground-waiting.

## Required Work

1. **Data:** add one independent external timing-probe receipt at the existing
   collector/cycle seam. It must identify raw schedule/collector/probe timing
   endpoints, ET offset, schedule relation, post-collection completed-prefix
   availability category, and counts from the existing kind-tagged collector
   payload. It must not enter the existing terminal schedule receipt or affect
   its exit code, open another KIS client, or start another collector.
2. **Engine Research:** specify the causal interpretation of each probe
   category for the frozen 15:30 decision and exclusive `valid_until`. It must
   not alter the model, examine outcomes, or create a research campaign.
3. **Execution:** prove the timing-probe route cannot load Paper configuration
   or reach account, quote, order, or canary code. Keep the existing virtual
   canary unchanged.
4. **Integration:** run fixture and Docker smoke evidence now. The probe
   container must be network-disabled and receive no `KIS_*` environment
   values. At the next eligible regular-session invocation, let the existing
   owned Data path produce one real source-safe probe receipt. A missing or
   late source result is a valid measurement, not an approval wait.
5. Ask Claude for a short falsification-first challenge before interpreting a
   real probe result as grounds to change schedule timing, receipt validity, or
   availability semantics. A timeout is `review_unavailable`, not agreement or
   a block.

## Completion Evidence

- focused tests prove one collector/client path, redaction, no Execution
  surface, and idempotent external receipt behavior;
- host and Docker fixture smoke receipts succeed without KIS account/order
  access;
- one live KIS market-data-only timing receipt, or a durable scheduler-owned
  `next_due` plus all offline implementation evidence if the next session has
  not occurred; the receipt must distinguish a post-collection observation
  from decision-time availability and must contain no feasibility verdict;
- refreshed Data, Engine Research, Execution, Research Steward,
  orchestration, and handoff stateboards; required verification, commit, and
  push.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
```
