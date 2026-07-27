# Next Codex Goal

## Objective

Establish the first bounded prospective QQQ intraday decision-to-KIS-Paper
loop: capture a completed-bar window, make one deterministic baseline decision,
replay it through `local_paper`, and exercise the existing virtual-only Paper
canary when its exact durable intent is technically valid.

This is execution learning, not a profitability or promotion gate. A missing
window or `abstain` is a scoped result, never a hold on another ready lane.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
   `RUNBOOK.md`, and all active stateboards.
3. Reattach the intraday-head index/receipt, current Paper account projection
   if available, and existing canary state. Do not print private data.
4. Ask Claude for one concise falsification-first check of the completed-bar,
   baseline, and virtual-only canary boundary. `review_unavailable` is not a
   hold on authorized private work.

## Work

1. **Data:** use the existing QQQ/NAS session-capture path during the next US
   regular session. Produce either a KIS-compatible 90 completed 1m-bar window
   or an exact no-window/source-quality fact. Derive 5m and 10m only through
   existing resampling; leave 1h and 3h inactive unless completed evidence
   exists.
2. **Engine Research:** freeze one small deterministic
   `enter`/`hold`/`reduce`/`exit`/`abstain` baseline before consuming the
   window. Emit source-safe timestamped evidence, validity, and the explicit
   no-decision path. Do not tune it from the same session, select a model, or
   claim profitability.
3. **Execution:** replay the exact decision through `local_paper`. When an
   exact durable virtual intent is technically valid, use the existing KIS
   Paper canary/executor lifecycle to submit, observe, and reconcile it. An
   unknown outcome pauses only that exact intent.
4. Keep market-session waiting owned by its scheduler. While it is not due,
   advance ready preparation, local simulation, execution verification, and
   independent Validation; never foreground-sleep.
5. Add focused tests for completed-bar input, resampling, baseline/abstain,
   replayability, virtual-paper route confinement, durable intent recovery, and
   no live or secret leakage. Refresh all stateboards with actual evidence.

## Boundaries

- KIS Paper market, account, and virtual order calls are authorized through the
  existing named paths. Never read or route `KIS_LIVE_*` or expose a public
  service.
- Keep data under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts`; never commit either.
- Do not use another provider in this QQQ runtime window or turn the terminal
  fixed NAS daily-history cache into a model, universe, or Paper-order input.
- Do not add a capital, profitability, report, trade-count, or manual approval
  gate. Preserve route isolation, intent persistence, technical validation, and
  unknown-outcome reconciliation.

## Completion

- A source-safe capture shows either a verified 90-bar window or a precise
  source-quality/no-window fact.
- The baseline decision and matching `local_paper` replay are reproducible from
  the same evidence; `abstain` is valid.
- A technically valid virtual intent has a durable, reconciled Paper outcome,
  or a target-local no-intent/recovery fact.
- Independent Validation confirms input completeness, replayability, route
  isolation, source safety, and no live access.

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

`Close daily history recovery`
