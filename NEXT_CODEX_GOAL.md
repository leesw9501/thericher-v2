# Next Codex Goal

## Objective

Build `kis-intraday-causal-observation-closure-v1`.

Reattach one terminal result from the existing task-owned QQQ/SPY intraday
head sequence and classify its exact causal availability. This advances the
data-collection and backtest/walk-forward-validation loops by establishing a
source-safe input boundary; it does not select a strategy, claim PnL, or
authorize Paper or live execution.

## Hard Boundaries

- Use only the existing `thericher-kis-paper-intraday-head` task and its
  established route for collection. Do not manually invoke it, Docker, KIS,
  account/order/quote endpoints, or a replacement scheduler.
- Inspect only source-safe task facts, immutable receipts, and existing
  credential-free offline validators. Never print credentials, account values,
  raw market rows, private intents, broker payloads, or identifiers.
- Never read, reference, route, print, log, or persist `KIS_LIVE_*`; do not
  enable live behavior or make a Paper submission from this objective.
- A missing, unavailable, provisional, or unqualified result narrows only its
  exact data input. It cannot become an approval hold or alter the closed
  Paper-canary lifecycle evidence.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Preserve the installed task's owned 2026-08-11 00:29 KST collection and
   06:20 KST terminal opportunities; do not foreground-wait or duplicate it.
2. After the terminal writes evidence, reattach only the matching immutable
   terminal, source-local capture, availability, and optional pair receipts
   through the existing offline reader. Recompute its required hash bindings.
3. Record the categorical result as `qualified_for_prospective_input` or
   scoped `input_unavailable`; never infer provider finality, model validity,
   fills, PnL, or alpha.
4. Refresh the Data, Execution, and orchestration stateboards plus `HANDOFF.md`
   with source-safe facts. Repair only an exact credential-free reader contract
   if validation exposes one; otherwise retain the receipt outcome.
5. Run changed-path focused tests and goal-boundary verification, commit and
   push only owned changes, then replace this file with the next material
   company objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Close KIS Paper canary lifecycle evidence`
