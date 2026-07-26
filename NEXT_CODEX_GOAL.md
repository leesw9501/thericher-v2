# Next Codex Goal

## Objective

Integrate the first due outcome from the installed prospective QQQ intraday-head
dispatcher after 2026-07-28 00:35 KST. Establish, from source-safe metadata,
whether the generation-8 head has progressed toward a verified first-five pair
and whether its isolated offline observer remained correctly scoped.

Do not foreground-wait, install another scheduler, or manually invoke the KIS
collector. Continue any ready independent bounded work while the named task
owns its due time.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read `HANDOFF.md`, `AGENTS.md`, `RUNBOOK.md`, `agents/orchestration.md`,
   `agents/data.md`, `agents/engine-research.md`, and `agents/execution.md`.
3. Reattest the pre-run coverage baseline with:

   ```powershell
   uv run python scripts\inspect_kis_intraday_head_coverage.py
   ```

## Hard Boundaries

- Use only source-safe runtime and metadata evidence: never print or commit raw
  market/broker data, prices, credentials, account identifiers, private intents,
  or KIS response bodies.
- Keep one `thericher-kis-paper-intraday-head` task and one
  `kis-paper-intraday-head` profile. The collector retains its four-page cap,
  source pacing, strict conflict rejection, and exact 390-minute selector.
- Do not read `KIS_LIVE_*`, use a live route, create an intent, submit a Paper
  order, select a candidate, or launch GPU work.
- The base-image observer may only produce its existing credential-free,
  local-paper observation after a verified pair. Its `pending`, `unavailable`,
  or `complete` result never revises collector state or freshness.

## Required Work

1. Reattest the installed task action, four KST triggers, `Ready` state, no
   missed-run anomaly, `IgnoreNew`, `StartWhenAvailable`, and `PT1H30M` limit.
2. After its next due result, compare QQQ coverage to the generation-8 baseline:
   complete-minute counts, offset-based missing ranges, continuation/overlap
   categories, last reason category, and preparation state.
3. Consume the dispatcher's sanitized observer status only. If it is `complete`,
   inspect the existing local-paper receipt without inferring a selected model,
   broker event, fill, or PnL. If it is `pending` or `unavailable`, retain the
   exact Data recovery path without inventing a retry scheduler.
4. Consume the next daily SPY result only through an exact receipt-derived run
   identity and categorical observer/terminal facts. Do not infer fills or PnL
   from a no-intent, missing, or ambiguous observation.
5. Refresh stateboards, verify, commit, push, and replace this file with one
   next objective after bounded completion evidence exists.

## Completion Evidence

- Source-safe before/after QQQ coverage metadata and current recovery class.
- Task evidence proves the one-task/one-profile dispatcher contract remains
  installed and bounded.
- Any observer result remains credential-free and local-paper-only; otherwise
  its categorical unavailability is scoped to the input.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```
