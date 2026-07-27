# Next Codex Goal

## Objective

Recover the current private KIS Paper QQQ head cache and calibrate its
current-head freshness contract from source-safe evidence, then let the
installed virtual-only route use only an eligible current window. This is a
paper-execution data-quality task, not a model promotion, profitability claim,
or live-trading step.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
   `RUNBOOK.md`, and all active stateboards.
3. Inspect the existing QQQ head/session-capture, runtime-window, and terminal
   receipt paths only. Do not scan `D:` broadly or inspect raw price rows.
4. Before changing a runtime freshness limit that can affect Paper eligibility,
   ask Claude for one concise falsification-first challenge. An OAuth failure
   is `review_unavailable`, not a hold on data measurement, tests, or an
   already-authorized virtual-only route.

## Work

1. **Data:** make current-head freshness evidence explicit and source-safe:
   record the completed-window end, route observation time, lag category, and
   selected budget in the relevant receipt or pure projection. Preserve raw
   market data under `D:\market_data`; do not output rows or prices.
2. **Data:** reattach the completed 2026-07-27 QQQ receipt and the current
   generation-20 head index, then obtain up to two additional regular-session
   observations through the existing lane-owned schedule or its bounded route.
   A clean new page may create a persisted `head` snapshot. An unscoped legacy
   or historical retained conflict must remain strict-rejected without another
   quarantine marker. Never foreground-wait for a due time: leave the worker's
   `next_due` owned by that worker and advance any independent ready package.
   A missing, stale, or provider-limited result is scoped evidence, not a
   company hold.
3. **Execution:** centralize the current freshness decision contract and add
   boundary tests for ready, exactly-at-budget, and stale input. Keep the
   existing limit unless measured evidence supports one reversible, paper-only
   adjustment. Do not infer a provider finality rule or silently use incomplete
   bars.
4. **Route:** when the exact current receipt is eligible, invoke only the
   existing virtual-host-pinned QQQ route. It may produce its truthful existing
   canary lifecycle or a scoped no-intent; do not force an intent, duplicate an
   unknown intent, or make a standalone account/order call to manufacture a
   result.
5. **Validation:** independently reattach the terminal receipt and verify the
   selected freshness fact, paper-vs-live isolation, categorical intent state,
   and replay boundary. Keep local replay fills labeled `source: local_paper`.

## Boundaries

- `KIS_PAPER_*`, private KIS Paper market/account calls, and virtual paper
  submit/modify/cancel remain standing-authorized. Do not print credentials,
  account identifiers, raw broker bodies, quotes, prices, or orders.
- Do not read or call `KIS_LIVE_*`, enable live behavior, spend money, expose a
  public service, or use a stale/incomplete window as an order input.
- Do not add a profitability gate, capital gate, manual approval latch, or
  generic latest-wins revision policy. A fresh-head quarantine remains exact,
  immutable, and unavailable to historical collection scope.
- Store generated artifacts under `D:\thericher-v2\model-artifacts`; market
  data stays under `D:\market_data`.

## Completion

- A source-safe current-head recovery/freshness fact and deterministic boundary
  tests establish the runtime contract or a justified paper-only adjustment.
- One terminal QQQ route receipt is independently reattached as a reconciled
  virtual canary lifecycle or truthful scoped no-intent/recovery result.
- No live route, secret output, raw-row disclosure, duplicate exact intent, or
  cross-lane Research promotion occurs.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Calibrate QQQ Paper runtime freshness`
