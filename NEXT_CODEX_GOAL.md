# Next Codex Goal

## Objective

Create the first source-separated KIS Paper QQQ/SPY D1 forward-validation
cache while the broad KIS D1 collector continues independently.

The cache exists to accumulate an untouched out-of-time daily stream for later
research. It is a Data product, not a strategy, model score, ranking, Paper
trade signal, or broker action.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattach the fixed QQQ/SPY daily-source lineage and the existing broad D1
   scheduler state without printing rows, prices, credentials, account facts,
   or broker bodies.
3. Ask Claude for a concise falsification-first drift check before changing a
   collector or installing a schedule. State the source scope, current-session
   exclusion, duplicate/recovery behavior, interaction with the broad worker,
   and the fact that would reverse the design.

## Authority And Boundaries

- `KIS_PAPER_*` may be used only by the owned Data market-data path for this
  exact QQQ/NAS and SPY/AMS daily scope. Do not read or route `KIS_LIVE_*`.
- Do not call account, position, quote, order, modify, cancel, or live routes.
- Store cache bytes only under `D:\market_data`; store source-safe receipts only
  under `D:\thericher-v2\model-artifacts`; do not persist secrets or raw rows
  in Git, logs, stateboards, or Claude prompts.
- Retain only completed daily sessions. Exclude a current/incomplete US session
  from the forward stream rather than substituting another provider or a prior
  history row.
- Preserve a separate forward-cache identity. Do not blend it into the fixed
  historical QQQ/SPY catalog, the NAS forward cache, Norgate data, Tiingo data,
  or the non-PIT broad current-listing panel.
- Keep one owned collector per cache and honor the shared KIS request gate.
  The new forward schedule must neither create a parallel request flood nor
  block the existing broad collector; fresh collection may take its documented
  priority only through the shared dispatcher.
- No model, GPU training, full validation, ensemble, Paper intent, dashboard,
  or performance claim belongs to this objective.

## Work

1. **Data:** inspect the existing forward-cache collector and schedule pattern;
   reuse or narrowly generalize it instead of creating a parallel framework.
2. **Data:** implement a two-target QQQ/NAS + SPY/AMS forward cache with exact
   provenance, deduplication, completed-session filtering, source-safe
   recovery state, and immutable external receipts.
3. **Data:** install one recoverable goal-owned schedule at a measured
   post-session time that does not overlap its own collector. It must safely
   defer when the shared Data dispatcher is occupied and resume at its next due
   time rather than sleeping the foreground orchestrator.
4. **Validation:** add focused tests for route isolation, no credential/account
   access outside the owned collector, current-session exclusion, idempotent
   duplicate handling, source separation, external artifact placement, and
   recovery after a deferred/failed target.
5. **Data:** run an offline/preflight smoke. Run one bounded real KIS Paper
   market-data collection only if the shared dispatcher is free and the
   schedule/input is due; otherwise leave its owned next-due recovery state and
   continue independent work.
6. Refresh stateboards, replace this file with exactly one next objective, then
   continue. A later Research consumer may use only the named forward-cache
   contract after its declared out-of-time depth exists.

## Completion

- A source-separated QQQ/SPY D1 forward-cache contract, cache path, and
  recoverable schedule exist.
- Focused tests prove cache/recovery and route isolation behavior.
- A source-safe preflight or eligible first collection receipt exists outside
  Git; a deferred first collection remains a scoped Data recovery fact.
- No account, order, live, model, GPU, or Paper action occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add QQQ SPY forward daily cache`
